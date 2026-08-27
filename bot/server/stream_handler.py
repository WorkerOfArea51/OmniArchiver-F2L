# -*- coding: utf-8 -*-
import re
import asyncio
import logging
from urllib.parse import quote
from aiohttp import web
from bot.core.config import Config
from bot.core.client_pool import client_pool
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024  # 1 MiB MTProto standard block
RANGE_REGEX = re.compile(r"^bytes=(?P<start>\d*)-(?P<end>\d*)$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Range, Content-Type, Authorization, *",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Content-Disposition, Accept-Ranges",
}

def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    if not range_header:
        return 0, file_size - 1

    match = RANGE_REGEX.fullmatch(range_header.strip())
    if not match:
        return 0, file_size - 1

    start_str = match.group("start")
    end_str = match.group("end")

    if start_str:
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
    else:
        if not end_str:
            return 0, file_size - 1
        suffix_len = int(end_str)
        if suffix_len <= 0:
            raise web.HTTPRequestRangeNotSatisfiable(headers={"Content-Range": f"bytes */{file_size}"})
        start = max(file_size - suffix_len, 0)
        end = file_size - 1

    if start < 0 or end >= file_size or start > end:
        raise web.HTTPRequestRangeNotSatisfiable(headers={"Content-Range": f"bytes */{file_size}"})

    return start, end

class StreamHandler:
    """Zero-RAM Direct HTTP Stream & Download Engine for Telegram Media."""

    @classmethod
    async def serve(
        cls,
        request: web.Request,
        message_id: int,
        channel_id: int = None,
        as_download: bool = False
    ) -> web.StreamResponse:
        target_channel = channel_id
        if not target_channel:
            record = await db.get_file(message_id)
            if record and record.get("channel_id"):
                target_channel = record["channel_id"]
            elif Config.CHANNELS:
                target_channel = Config.CHANNELS[0]

        if not target_channel:
            raise web.HTTPNotFound(text="Target channel not configured.", headers=CORS_HEADERS)

        # Use primary client to fetch message safely
        try:
            msg = await client_pool.primary_client.get_messages(target_channel, message_id)
        except Exception as e:
            logger.error(f"Error fetching message {message_id} from {target_channel}: {e}")
            raise web.HTTPNotFound(text="File not found in storage channel.", headers=CORS_HEADERS)

        media = get_media_from_message(msg)
        if not media:
            raise web.HTTPNotFound(text="Message contains no streamable media.", headers=CORS_HEADERS)

        file_name, file_size, mime_type, _ = get_file_details(msg)
        if file_size == 0:
            raise web.HTTPNotFound(text="File size is reported as zero.", headers=CORS_HEADERS)

        range_header = request.headers.get("Range", "")
        start, end = parse_range_header(range_header, file_size)
        content_length = end - start + 1

        is_full_file = (start == 0 and end == file_size - 1)
        disposition = "attachment" if as_download else "inline"
        safe_filename = file_name.replace('"', '\"')

        headers = {
            "Content-Type": mime_type,
            "Content-Length": str(content_length),
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"; filename*=UTF-8''{quote(file_name)}',
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=31536000",
            "Connection": "keep-alive",
            **CORS_HEADERS,
        }

        status = 206 if range_header else 200
        if range_header:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        # Initialize StreamResponse (Immediate header delivery to download manager/browser)
        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        # Fast HEAD response
        if request.method == "HEAD":
            return response

        # Track statistics in background
        if as_download:
            asyncio.create_task(db.increment_downloads(target_channel, message_id))
        else:
            asyncio.create_task(db.increment_views(target_channel, message_id))

        # Select worker client for downloading stream
        stream_client = client_pool.primary_client

        chunk_offset = 0 if is_full_file else (start // CHUNK_SIZE)
        chunk_limit = 0 if is_full_file else (((content_length + CHUNK_SIZE - 1) // CHUNK_SIZE) + 1)
        bytes_to_skip = 0 if is_full_file else (start % CHUNK_SIZE)
        bytes_sent = 0

        try:
            async for chunk in stream_client.stream_media(
                msg,
                offset=chunk_offset,
                limit=chunk_limit
            ):
                if bytes_to_skip > 0:
                    if len(chunk) <= bytes_to_skip:
                        bytes_to_skip -= len(chunk)
                        continue
                    chunk = chunk[bytes_to_skip:]
                    bytes_to_skip = 0

                remaining = content_length - bytes_sent
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]

                if chunk:
                    await response.write(chunk)
                    bytes_sent += len(chunk)

                if bytes_sent >= content_length:
                    break

            await response.write_eof()

        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as e:
            logger.debug(f"Streaming error on msg {message_id}: {e}")

        return response
