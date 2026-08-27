from quart import Blueprint, Response, request, render_template, redirect
from math import ceil
from re import match as re_match
from .error import abort
from bot.clients import get_worker_client, TelegramBot
from bot.config import Telegram, Server
from bot.database.files import get_file
from bot.modules.telegram import get_message, get_file_properties

bp = Blueprint('main', __name__)

@bp.route('/')
async def home():
    return redirect(f'https://t.me/{Telegram.BOT_USERNAME}')

@bp.route('/ping')
@bp.route('/health')
async def health_check():
    return "OK", 200

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
        chunk_index = 0
        async for chunk in worker.stream_media(
            file_msg,
            offset=offset_chunks,
            limit=chunks_to_stream,
        ):
            if chunk_index == 0:  # Trim initial chunk if offset doesn't align with 1MB boundary
                trim_start = start % chunk_size
                if trim_start > 0:
                    chunk = chunk[trim_start:]

            remaining_bytes = content_length - bytes_streamed
            if remaining_bytes <= 0:
                break

            if len(chunk) > remaining_bytes:  # Trim trailing chunk
                chunk = chunk[:remaining_bytes]

            yield chunk
            bytes_streamed += len(chunk)
            chunk_index += 1

    return Response(file_stream(), headers=headers, status=status_code)

@bp.route('/stream/<string:file_code>')
async def stream_file(file_code):
    doc = await get_file(file_code)
    if not doc:
        abort(404, 'File not found or link has expired.')

    media_url = f'{Server.BASE_URL}/dl/{file_code}'
    return await render_template('player.html', mediaLink=media_url, fileName=doc.get('file_name', 'Play Video'))
