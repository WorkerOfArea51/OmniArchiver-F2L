from quart import Blueprint, Response, request, render_template, redirect, jsonify
from math import ceil
from re import match as re_match
from .error import abort
from bot.clients import get_worker_client, TelegramBot
from bot.config import Telegram, Server
from bot.database import db
from bot.database.files import get_file, add_bandwidth_bytes
from bot.modules.telegram import get_message, get_file_properties
from bot.modules.static import get_human_size
from bot.modules.memory import flush_ram

bp = Blueprint('main', __name__)

@bp.route('/')
async def home():
    return redirect(f'https://t.me/{Telegram.BOT_USERNAME}')

@bp.route('/ping')
@bp.route('/health')
async def health_check():
    return "OK", 200

# ==================== STREAM & DOWNLOAD ROUTES ====================

@bp.route('/dl/<string:file_code>')
async def transmit_file(file_code):
    # Lookup file record in MongoDB
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    channel_id = doc.get('channel_id')
    message_id = doc.get('message_id')

    # Get a worker client from the multi-client pool
    worker = get_worker_client() or TelegramBot

    file_msg = await get_message(channel_id, message_id, client=worker)
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

    offset_chunks = start // chunk_size
    total_bytes_to_stream = end - start + 1
    chunks_to_stream = ceil(total_bytes_to_stream / chunk_size)

    content_length = total_bytes_to_stream
    headers = {
        'Content-Type': mime_type or 'application/octet-stream',
        'Content-Disposition': f'attachment; filename="{file_name}"',
        'Content-Range': f'bytes {start}-{end}/{file_size}',
        'Accept-Ranges': 'bytes',
        'Content-Length': str(content_length),
        'Access-Control-Allow-Origin': '*',
    }
    status_code = 206 if range_header else 200

    async def file_stream():
        bytes_streamed = 0
        current_worker = worker

        for attempt in range(max(1, len(worker_clients))):
            try:
                chunk_index = 0
                current_start = start + bytes_streamed
                offset = current_start // chunk_size
                remaining_total = end - current_start + 1
                chunks_needed = ceil(remaining_total / chunk_size)

                # Use current worker or fetch message if worker rotated
                msg = file_msg if current_worker == worker else (await get_message(channel_id, message_id, client=current_worker) or file_msg)

                async for chunk in current_worker.stream_media(
                    msg,
                    offset=offset,
                    limit=chunks_needed,
                ):
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
                    chunk_index += 1

                # If all requested bytes were streamed, we are done
                if bytes_streamed >= content_length:
                    break

            except (asyncio.CancelledError, GeneratorExit):
                # Player disconnected or seeked to a new timestamp - clean up immediately
                break
            except Exception as e:
                logger.warning("Stream chunk interrupted (%s). Auto-recovering stream at byte %d...", e, start + bytes_streamed)
                # Rotate to another worker client to resume streaming seamlessly
                current_worker = get_worker_client() or TelegramBot
                if bytes_streamed >= content_length:
                    break
                await asyncio.sleep(0.1)

        if bytes_streamed > 0:
            await add_bandwidth_bytes(bytes_streamed)
        flush_ram()

    return Response(file_stream(), headers=headers, status=status_code)

@bp.route('/stream/<string:file_code>')
async def stream_file(file_code):
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    media_url = f'{Server.BASE_URL}/dl/{file_code}'
    return await render_template('player.html', mediaLink=media_url, fileName=doc.get('file_name', 'Play Video'))

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
