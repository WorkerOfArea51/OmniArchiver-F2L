import asyncio
from logging import getLogger
from quart import Blueprint, Response, request, render_template, redirect, jsonify
from math import ceil
from re import match as re_match
from .error import abort
from bot.clients import get_worker_client, TelegramBot, mark_worker_cooldown
from bot.config import Telegram, Server
from bot.database import db
from bot.database.files import get_file, add_bandwidth_bytes
from bot.modules.telegram import get_message, get_file_properties
from bot.modules.static import get_human_size
from bot.modules.memory import flush_ram, check_memory_circuit_breaker

try:
    from hydrogram.errors import FloodWait
except ImportError:
    try:
        from pyrogram.errors import FloodWait
    except ImportError:
        FloodWait = Exception

logger = getLogger('server')

bp = Blueprint('main', __name__)

@bp.route('/')
async def home():
    username = getattr(TelegramBot.me, 'username', None) or Telegram.BOT_USERNAME
    if username and username.lower() != 'botfather':
        return redirect(f'https://t.me/{username}')
    return "OmniArchiver-F2L Streaming Server is Online", 200

@bp.route('/ping')
@bp.route('/health')
async def health_check():
    return "OK", 200

# Malicious vulnerability scanners and abusive scrapers to block immediately
BLOCKED_AGENTS = (
    'sqlmap', 'nikto', 'masscan', 'nmap', 'dirbuster', 'gobuster',
    'zgrab', 'wpscan', 'acunetix', 'nessus', 'havij', 'openvas',
    'scrapy', 'censys', 'shodan'
)

@bp.before_request
async def security_and_bot_check():
    # Always allow health checks, pings, and home redirect
    if request.path in ('/ping', '/health', '/'):
        return None

    user_agent = (request.headers.get('User-Agent') or '').lower()

    # Block automated vulnerability scanners and abusive crawlers
    if any(blocked in user_agent for blocked in BLOCKED_AGENTS):
        return jsonify({'status': 'error', 'message': 'Access forbidden'}), 403

    return None

# ==================== STREAM & DOWNLOAD ROUTES ====================

@bp.route('/dl/<string:file_code>')
async def transmit_file(file_code):
    # Lookup file record in MongoDB
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    channel_id = doc.get('channel_id')
    message_id = doc.get('message_id')

    # Select worker client for this streaming request
    worker = get_worker_client() or TelegramBot

    # Retrieve message with this specific worker so the file_reference is cryptographically bound to it
    file_msg = await get_message(channel_id, message_id, client=worker)
    if not file_msg and worker != TelegramBot:
        # Fallback to main TelegramBot if worker is not an admin/member in the channel
        file_msg = await get_message(channel_id, message_id, client=TelegramBot)
        worker = TelegramBot

    if not file_msg:
        abort(404, 'Media message not found in channel.')

    file_name = doc.get('file_name')
    file_size = doc.get('file_size')
    mime_type = doc.get('mime_type')

    # Fallback to inspecting message if metadata is incomplete
    if not file_name or not file_size or not mime_type:
        f_name, f_size, m_type = get_file_properties(file_msg)
        file_name = file_name or f_name
        file_size = file_size or f_size
        mime_type = mime_type or m_type

    range_header = request.headers.get('Range')
    start = 0
    end = file_size - 1
    chunk_size = 1024 * 1024  # 1 MB

    if range_header:
        range_match = re_match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start > end or start >= file_size:
                abort(416, 'Requested range not satisfiable')
        else:
            abort(400, 'Invalid Range header')

    total_bytes_to_stream = end - start + 1
    content_length = total_bytes_to_stream
    # Ensure a valid video MIME type so browsers stream inline instead of forcing a download
    if not mime_type or mime_type == 'application/octet-stream':
        if file_name and file_name.lower().endswith('.mkv'):
            mime_type = 'video/x-matroska'
        elif file_name and file_name.lower().endswith('.webm'):
            mime_type = 'video/webm'
        else:
            mime_type = 'video/mp4'

    # Default to 'attachment' so direct download links automatically download the file in browsers.
    # Use 'inline' only when ?stream=1 or ?inline=1 is specified (e.g. by HTML5 video player in player.html).
    is_streaming = (request.args.get('stream') or request.args.get('inline')) and not (request.args.get('dl') or request.args.get('download'))
    disposition = 'inline' if is_streaming else 'attachment'

    headers = {
        'Content-Type': mime_type,
        'Content-Disposition': f'{disposition}; filename="{file_name}"',
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Connection': 'keep-alive',
        'Keep-Alive': 'timeout=300, max=1000',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Content-Range, Accept-Ranges, Content-Length',
        'X-Content-Type-Options': 'nosniff',
    }
    if range_header:
        headers['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    status_code = 206 if range_header else 200

    async def file_stream():
        bytes_streamed = 0
        current_start = start
        offset = current_start // chunk_size
        remaining_total = end - current_start + 1
        chunks_needed = ceil(remaining_total / chunk_size)

        _SENTINEL = object()

        async def stream_with_client(target_client, target_msg):
            nonlocal bytes_streamed
            # Buffer up to 2 chunks (2 MB) in RAM while current chunk is streaming to client
            queue = asyncio.Queue(maxsize=2)
            producer_err = []

            async def producer():
                try:
                    async for chunk in target_client.stream_media(
                        target_msg,
                        offset=offset,
                        limit=chunks_needed,
                    ):
                        await queue.put(chunk)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if isinstance(e, FloodWait):
                        wait_sec = getattr(e, 'value', 30)
                        worker_name = getattr(target_client, 'name', 'bot')
                        mark_worker_cooldown(worker_name, wait_sec)
                        logger.warning("Worker %s hit FloodWait (%ds) during stream production, marked on cooldown", worker_name, wait_sec)
                    producer_err.append(e)
                finally:
                    await queue.put(_SENTINEL)

            producer_task = asyncio.create_task(producer())
            try:
                chunk_index = 0
                while True:
                    item = await queue.get()
                    if item is _SENTINEL:
                        if producer_err and bytes_streamed == 0:
                            raise producer_err[0]
                        break

                    chunk = item
                    if chunk_index == 0:
                        trim_start = current_start % chunk_size
                        if trim_start > 0:
                            chunk = chunk[trim_start:]

                    remaining_bytes = content_length - bytes_streamed
                    if remaining_bytes <= 0:
                        break

                    if len(chunk) > remaining_bytes:
                        chunk = chunk[:remaining_bytes]

                    yield chunk
                    bytes_streamed += len(chunk)
                    del chunk
                    del item
                    chunk_index += 1
                    # Memory guardian: check RSS every 20 chunks (~20 MB streamed)
                    if chunk_index % 20 == 0:
                        check_memory_circuit_breaker()
            finally:
                if not producer_task.done():
                    producer_task.cancel()
                    try:
                        await producer_task
                    except (asyncio.CancelledError, Exception):
                        pass

        try:
            async for data in stream_with_client(worker, file_msg):
                yield data
        except (asyncio.CancelledError, GeneratorExit):
            pass
        except Exception as e:
            if isinstance(e, FloodWait):
                wait_sec = getattr(e, 'value', 30)
                worker_name = getattr(worker, 'name', 'bot')
                mark_worker_cooldown(worker_name, wait_sec)
                logger.warning("Worker %s hit FloodWait (%ds), marked on cooldown", worker_name, wait_sec)

            # If initial chunk failed (e.g. FileReferenceExpired, FloodWait, invalid token, or worker issue),
            # force-refresh a fresh message directly from Telegram via TelegramBot and retry
            if bytes_streamed == 0:
                try:
                    logger.info("Attempting automatic fresh-token retry for msg %s via TelegramBot...", message_id)
                    fallback_msg = await get_message(channel_id, message_id, client=TelegramBot, force_refresh=True)
                    if fallback_msg:
                        async for data in stream_with_client(TelegramBot, fallback_msg):
                            yield data
                except (asyncio.CancelledError, GeneratorExit):
                    pass
                except Exception as fb_err:
                    logger.warning("Fallback stream error on TelegramBot: %s", fb_err)
        finally:
            if bytes_streamed > 0:
                await add_bandwidth_bytes(bytes_streamed)
            check_memory_circuit_breaker()
            flush_ram()

    return Response(file_stream(), headers=headers, status=status_code)

@bp.route('/stream/<string:file_code>')
async def stream_file(file_code):
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    media_url = f'{Server.BASE_URL}/dl/{file_code}?stream=1'
    download_url = f'{Server.BASE_URL}/dl/{file_code}'
    file_name = doc.get('file_name', 'Play Video')
    file_size_str = get_human_size(doc.get('file_size', 0))
    duration_str = doc.get('duration_formatted', '')
    bot_username = getattr(TelegramBot.me, 'username', None) or Telegram.BOT_USERNAME or ''

    return await render_template(
        'player.html',
        mediaLink=media_url,
        downloadLink=download_url,
        fileName=file_name,
        fileSize=file_size_str,
        duration=duration_str,
        fileCode=file_code,
        botUsername=bot_username
    )

# ==================== REST API ENDPOINTS FOR STREAMHUB ====================

@bp.route('/api/batch/<string:batch_id>')
async def api_get_batch(batch_id):
    """Returns structured JSON for a specific anime or web series batch."""
    for col in (db.anime, db.webseries):
        if col is not None:
            doc = await col.find_one({'_id': batch_id})
            if doc:
                episodes = []
                for ep in doc.get('episodes', []):
                    code = ep['code']
                    episodes.append({
                        'episode_num': ep.get('episode_num', 1),
                        'file_name': ep.get('file_name', ''),
                        'file_size': ep.get('file_size', 0),
                        'size_formatted': get_human_size(ep.get('file_size', 0)),
                        'duration': ep.get('duration', 0),
                        'duration_formatted': ep.get('duration_formatted', 'N/A'),
                        'mime_type': ep.get('mime_type', ''),
                        'stream_url': f"{Server.BASE_URL}/stream/{code}",
                        'download_url': f"{Server.BASE_URL}/dl/{code}",
                        'code': code
                    })
                return jsonify({
                    'status': 'success',
                    'batch_id': batch_id,
                    'title': doc.get('title', ''),
                    'category': doc.get('category', ''),
                    'channel_id': doc.get('channel_id'),
                    'total_episodes': len(episodes),
                    'episodes': episodes
                }), 200

    return jsonify({'status': 'error', 'message': 'Batch not found'}), 404

@bp.route('/api/file/<string:file_code>')
async def api_get_file(file_code):
    """Returns structured JSON metadata and streaming links for a single file/movie."""
    doc = await get_file(file_code)
    if not doc:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404

    code = doc.get('code', file_code)
    return jsonify({
        'status': 'success',
        'code': code,
        'file_name': doc.get('file_name', ''),
        'file_size': doc.get('file_size', 0),
        'size_formatted': get_human_size(doc.get('file_size', 0)),
        'duration': doc.get('duration', 0),
        'duration_formatted': doc.get('duration_formatted', 'N/A'),
        'mime_type': doc.get('mime_type', ''),
        'category': doc.get('category', 'movies'),
        'stream_url': f"{Server.BASE_URL}/stream/{code}",
        'download_url': f"{Server.BASE_URL}/dl/{code}"
    }), 200

@bp.route('/api/movies')
async def api_get_movies():
    """Lists indexed movies."""
    if db.movies is None:
        return jsonify({'status': 'error', 'message': 'Database not connected'}), 500
    
    cursor = db.movies.find().sort('created_at', -1).limit(100)
    movies = []
    async for doc in cursor:
        code = doc.get('code', doc.get('_id'))
        movies.append({
            'code': code,
            'file_name': doc.get('file_name', ''),
            'file_size': doc.get('file_size', 0),
            'size_formatted': get_human_size(doc.get('file_size', 0)),
            'duration': doc.get('duration', 0),
            'duration_formatted': doc.get('duration_formatted', 'N/A'),
            'stream_url': f"{Server.BASE_URL}/stream/{code}",
            'download_url': f"{Server.BASE_URL}/dl/{code}"
        })
    return jsonify({'status': 'success', 'count': len(movies), 'movies': movies}), 200
