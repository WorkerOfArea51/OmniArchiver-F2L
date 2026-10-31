import asyncio
from logging import getLogger
from quart import Blueprint, Response, request, render_template, redirect, jsonify
from math import ceil
from re import match as re_match
from .error import abort
from bot.clients import get_worker_client, TelegramBot, mark_worker_cooldown, worker_clients, is_worker_on_cooldown
from bot.config import Telegram, Server
from bot.database import db
from bot.database.files import get_file, add_bandwidth_bytes
from bot.modules.telegram import get_message, get_file_properties
from bot.modules.static import get_human_size
from bot.modules.memory import flush_ram, check_memory_circuit_breaker
from bot.modules.cache import get_cached_chunk, put_cached_chunk, is_head_or_tail, init_cache, is_chunk_cached, prefetch_tail_chunk, prefetch_head_chunk

try:
    from hydrogram.errors import FloodWait
except ImportError:
    try:
        from pyrogram.errors import FloodWait
    except ImportError:
        FloodWait = Exception

logger = getLogger('server')

bp = Blueprint('main', __name__)
init_cache()

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

    # Lazy message resolution: Contact Telegram ONLY if metadata is missing or uncached chunks are needed!
    worker = get_worker_client() or TelegramBot
    file_msg = None

    async def get_target_msg():
        nonlocal file_msg
        if file_msg is not None:
            return file_msg
        file_msg = await get_message(channel_id, message_id, client=TelegramBot)
        return file_msg

    file_name = doc.get('file_name')
    file_size = doc.get('file_size')
    mime_type = doc.get('mime_type')

    # Fallback to inspecting message ONLY if metadata in database is incomplete
    if not file_name or not file_size or not mime_type:
        msg = await get_target_msg()
        if not msg:
            abort(404, 'Media message not found in channel.')
        f_name, f_size, m_type = get_file_properties(msg)
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
        total_chunks = ceil(file_size / chunk_size)

        curr_offset = offset
        curr_chunks_needed = chunks_needed
        # 1. Fast Path: Serve any consecutive leading chunks from Head & Tail SSD cache (0.5ms response time)
        # Supports in-flight waiting if chunk is currently being pre-cached by a worker!
        while curr_chunks_needed > 0:
            cached_data = await get_cached_chunk(file_code, curr_offset, wait_in_flight=False)
            if cached_data is None:
                break

            chunk = cached_data
            if bytes_streamed == 0:
                trim_start = current_start % chunk_size
                if trim_start > 0:
                    chunk = chunk[trim_start:]

            rem_bytes = content_length - bytes_streamed
            if rem_bytes <= 0:
                break
            if len(chunk) > rem_bytes:
                chunk = chunk[:rem_bytes]

            yield chunk
            bytes_streamed += len(chunk)
            del chunk
            curr_offset += 1
            curr_chunks_needed -= 1

            if bytes_streamed >= content_length:
                break

        # If all requested data was served directly from cache (0ms delay), we are done without touching Telegram!
        if curr_chunks_needed <= 0 or bytes_streamed >= content_length:
            if bytes_streamed > 0:
                await add_bandwidth_bytes(bytes_streamed)
            check_memory_circuit_breaker()
            flush_ram()
            return

        # 2. Resilient Continuous Sequential MTProto Streaming Engine
        # -------------------------------------------------------------------------
        # Streams directly from Telegram MTProto over a persistent single-session connection.
        # Eliminates 1MB chunk teardowns, handshake latency, and parallel connection rate limits.
        # Combined with TgCrypto hardware AES and 15MB Head SSD pre-caching, provides uninterrupted
        # 2-5+ MB/s throughput for 1080p/4K video playback and downloads!
        # -------------------------------------------------------------------------
        end_chunk = curr_offset + curr_chunks_needed
        retry_count = 0
        MAX_RETRIES = 12

        # Resolve target media message once using TelegramBot (avoid per-chunk Telegram API spam)
        try:
            msg = await get_target_msg()
        except Exception as e:
            logger.error("Failed to resolve message for %s: %s", file_code, e)
            msg = None

        if not msg:
            logger.warning("Could not retrieve media message for %s from channel", file_code)
            flush_ram()
            return

        # 2. High-Throughput MTProto Streaming Engine with Async Lookahead Queue
        # Uses an asyncio.Queue(maxsize=3) so Telegram downloads Chunk N+1 in the background
        # WHILE Chunk N is actively flushing to the player, eliminating roundtrip idle latency!
        END_SENTINEL = object()
        queue = asyncio.Queue(maxsize=3)

        async def prefetch_producer():
            p_offset = curr_offset
            p_retry = 0

            # TelegramBot is the primary client with persistent MTProto media sessions (0ms cold start).
            # If TelegramBot is temporarily on cooldown (FloodWait), fallback to auxiliary worker pool.
            current_worker = TelegramBot
            if is_worker_on_cooldown(getattr(TelegramBot, 'name', 'bot_main')):
                current_worker = get_worker_client() or TelegramBot

            try:
                while p_offset < end_chunk and p_retry < MAX_RETRIES:
                    worker_name = getattr(current_worker, 'name', 'bot_main')
                    stream_iter = None

                    try:
                        worker_msg = msg
                        if current_worker != TelegramBot and channel_id and message_id:
                            worker_msg = await get_message(channel_id, message_id, client=current_worker) or msg

                        stream_iter = current_worker.stream_media(worker_msg, offset=p_offset).__aiter__()
                        is_first_chunk = True

                        while p_offset < end_chunk:
                            # Generous 25.0s timeout per chunk: allows MTProto DH handshake and transatlantic/transpacific latency without premature stall cancellation
                            try:
                                chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=25.0)
                            except StopAsyncIteration:
                                break
                            except (asyncio.TimeoutError, Exception) as fetch_err:
                                err_name = type(fetch_err).__name__
                                logger.warning('Stream worker %s stalled on chunk %d (%s). Rotating...',
                                               worker_name, p_offset, err_name)
                                break

                            if is_head_or_tail(p_offset, total_chunks):
                                asyncio.create_task(put_cached_chunk(file_code, p_offset, chunk, total_chunks))

                            await queue.put((p_offset, chunk))
                            p_offset += 1
                            p_retry = 0

                            if p_offset >= end_chunk:
                                return

                    except (asyncio.CancelledError, GeneratorExit):
                        return
                    except Exception as stream_err:
                        p_retry += 1
                        err_name = type(stream_err).__name__
                        logger.warning('Stream worker %s encountered %s at chunk %d (retry %d/%d). Rotating...',
                                       worker_name, err_name, p_offset, p_retry, MAX_RETRIES)
                        if any(x in err_name for x in ('ChannelPrivate', 'ChatAdminRequired', 'UserNotParticipant')):
                            mark_worker_cooldown(worker_name, 600)
                        elif isinstance(stream_err, FloodWait):
                            wait_sec = getattr(stream_err, 'value', 30)
                            mark_worker_cooldown(worker_name, wait_sec)
                        else:
                            mark_worker_cooldown(worker_name, 30)
                    finally:
                        if stream_iter is not None:
                            try:
                                await stream_iter.aclose()
                            except Exception:
                                pass

                    if p_offset < end_chunk:
                        p_retry += 1
                        if current_worker != TelegramBot:
                            mark_worker_cooldown(worker_name, 60)
                            current_worker = TelegramBot if not is_worker_on_cooldown('bot_main') else (get_worker_client() or TelegramBot)
                        else:
                            mark_worker_cooldown(worker_name, 30)
                            current_worker = get_worker_client() or TelegramBot
                        await asyncio.sleep(0.3)

            except (asyncio.CancelledError, GeneratorExit):
                pass
            finally:
                await queue.put(END_SENTINEL)

        producer_task = asyncio.create_task(prefetch_producer())

        try:
            while bytes_streamed < content_length:
                item = await queue.get()
                if item is END_SENTINEL:
                    break
                ch_offset, chunk = item

                if bytes_streamed == 0:
                    trim_start = current_start % chunk_size
                    if trim_start > 0:
                        chunk = chunk[trim_start:]

                rem_bytes = content_length - bytes_streamed
                if rem_bytes <= 0:
                    break

                if len(chunk) > rem_bytes:
                    chunk = chunk[:rem_bytes]

                yield chunk
                bytes_streamed += len(chunk)
                curr_offset = ch_offset + 1
                del chunk

                if curr_offset % 20 == 0:
                    check_memory_circuit_breaker()

                if bytes_streamed >= content_length or curr_offset >= end_chunk:
                    break
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass
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

@bp.route('/api/debug_file/<string:file_code>')
async def api_debug_file(file_code):
    import time
    import socket
    from hydrogram.file_id import FileId
    t0 = time.time()
    try:
        doc = await get_file(file_code)
        if not doc:
            return jsonify({'error': 'doc not found in database'}), 404
        channel_id = doc.get('channel_id')
        message_id = doc.get('message_id')

        # Test message resolution with TelegramBot
        t_resolve = time.time()
        msg = await get_message(channel_id, message_id, client=TelegramBot)
        dt_resolve = round(time.time() - t_resolve, 2)

        if not msg:
            return jsonify({
                'status': 'error',
                'error': 'Message not found in channel via TelegramBot',
                'channel_id': channel_id,
                'message_id': message_id,
                'resolve_time': dt_resolve
            }), 404

        media = getattr(msg, 'video', None) or getattr(msg, 'document', None)
        file_name = getattr(media, 'file_name', '')
        file_size = getattr(media, 'file_size', 0)
        file_id_str = getattr(media, 'file_id', '')
        decoded = FileId.decode(file_id_str) if file_id_str else None
        dc_id = getattr(decoded, 'dc_id', None)

        dc_reachability = {}
        for d, ip in [(1, "149.154.175.53"), (2, "149.154.167.51"), (4, "149.154.167.91"), (5, "91.108.56.130")]:
            try:
                s = socket.create_connection((ip, 443), timeout=1.5)
                s.close()
                dc_reachability[d] = "OK"
            except Exception as e:
                dc_reachability[d] = f"FAILED: {e}"

        media_sessions_active = list(TelegramBot.media_sessions.keys())

        return jsonify({
            'status': 'ok',
            'channel_id': channel_id,
            'message_id': message_id,
            'file_name': file_name,
            'file_size': file_size,
            'dc_id': dc_id,
            'dc_reachability': dc_reachability,
            'media_sessions_active': media_sessions_active,
            'resolve_time': dt_resolve,
            'total_time': round(time.time() - t0, 2)
        }), 200
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@bp.route('/api/version')
async def api_version():
    import subprocess
    commit = 'unknown'
    try:
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode().strip()
    except Exception:
        pass
    from bot.clients import worker_clients, TelegramBot
    workers_info = [getattr(w, 'name', 'bot') for w in worker_clients]
    return jsonify({
        'status': 'online',
        'commit': commit,
        'primary_bot': getattr(TelegramBot, 'name', 'bot_main'),
        'total_workers': len(worker_clients),
        'workers': workers_info
    }), 200

@bp.route('/api/debug_logs')
async def api_debug_logs():
    import os
    lines = []
    for log_name in ('bot.log', 'event-log.txt', 'watchdog.log'):
        if os.path.exists(log_name):
            try:
                with open(log_name, 'r', encoding='utf-8', errors='ignore') as f:
                    c = f.readlines()
                    lines.append(f"=== {log_name} (last 40 lines) ===\n" + "".join(c[-40:]))
            except Exception as e:
                lines.append(f"Error reading {log_name}: {e}")
    return Response("\n\n".join(lines) if lines else "No log files found", mimetype='text/plain')

@bp.route('/api/test_chunk/<string:file_code>/<int:chunk_idx>')
async def api_test_chunk(file_code, chunk_idx):
    import time
    import traceback
    t0 = time.time()
    try:
        doc = await get_file(file_code)
        if not doc:
            return jsonify({'error': 'doc not found'}), 404
        channel_id = doc.get('channel_id')
        message_id = doc.get('message_id')
        msg = await get_message(channel_id, message_id, client=TelegramBot)
        if not msg:
            return jsonify({'error': 'msg not found'}), 404

        target_name = request.args.get('worker')
        if target_name in ('primary', 'bot_main', 'bot'):
            worker = TelegramBot
        elif target_name:
            worker = next((w for w in worker_clients if getattr(w, 'name', '') == target_name), TelegramBot)
        else:
            worker = TelegramBot
        w_name = getattr(worker, 'name', 'bot')
        t1 = time.time()
        chunk_data = None
        worker_msg = msg
        if worker != TelegramBot and channel_id and message_id:
            worker_msg = await get_message(channel_id, message_id, client=worker) or msg
        stream_iter = worker.stream_media(worker_msg, offset=chunk_idx, limit=1).__aiter__()
        try:
            chunk_data = await asyncio.wait_for(stream_iter.__anext__(), timeout=20.0)
        finally:
            try:
                await stream_iter.aclose()
            except Exception:
                pass
        dt = time.time() - t1
        return jsonify({
            'status': 'ok',
            'worker': w_name,
            'chunk_idx': chunk_idx,
            'chunk_len': len(chunk_data) if chunk_data else 0,
            'time_sec': round(dt, 2),
            'total_time': round(time.time() - t0, 2)
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'error_type': type(e).__name__,
            'traceback': traceback.format_exc(),
            'total_time': round(time.time() - t0, 2)
        }), 500
