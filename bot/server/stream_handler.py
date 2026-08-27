# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import Tuple, Optional
from aiohttp import web
from bot.core.config import Config
from bot.core.client_pool import client_pool
from bot.core.cache import chunk_cache
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

# Pyrogram stream_media default chunk size is 1 MiB
PYRO_CHUNK_SIZE = 1024 * 1024

class StreamHandler:
    """Production RFC 7233 HTTP Range Stream Engine with Accurate Chunk Alignment."""

    @staticmethod
    def parse_range(range_header: str, file_size: int) -> Tuple[int, int, int]:
        if not range_header or "=" not in range_header:
            return 0, file_size - 1, file_size

        unit, range_val = range_header.split("=", 1)
        if unit.strip().lower() != "bytes":
            return 0, file_size - 1, file_size

        range_val = range_val.strip()
        if "," in range_val:
            range_val = range_val.split(",")[0].strip()

        parts = range_val.split("-")
        start_str = parts[0].strip()
        end_str = parts[1].strip() if len(parts) > 1 else ""

        if not start_str and not end_str:
            return 0, file_size - 1, file_size

        if not start_str:
            length = int(end_str)
            if length > file_size: length = file_size
            start = file_size - length
            end = file_size - 1
        else:
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1

        if start >= file_size or start < 0 or end >= file_size or start > end:
            raise ValueError(f"Range {range_header} not satisfiable for size {file_size}")

        content_length = (end - start) + 1
        return start, end, content_length

    @classmethod
    async def serve(
        cls,
        request: web.Request,
        message_id: int,
        channel_id: Optional[int] = None,
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
            raise web.HTTPNotFound(text="Target channel not configured.")

        try:
            msg = await client_pool.primary_client.get_messages(target_channel, message_id)
        except Exception as e:
            logger.error(f"Failed to fetch message {message_id} from channel {target_channel}: {e}")
            raise web.HTTPNotFound(text="Media not found or channel inaccessible.")

        media = get_media_from_message(msg)
        if not media:
            raise web.HTTPNotFound(text="Message contains no streamable media.")

        file_name, file_size, mime_type, _ = get_file_details(msg)

        range_header = request.headers.get("Range")
        try:
            start, end, length = cls.parse_range(range_header, file_size)
        except ValueError:
            return web.Response(
                status=416,
                headers={"Content-Range": f"bytes */{file_size}"},
                text="Requested Range Not Satisfiable"
            )

        disposition = "attachment" if as_download else "inline"
        safe_filename = file_name.replace('"', '\"')

        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"',
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
            "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges",
            "Cache-Control": "public, max-age=86400"
        }

        status = 206 if range_header else 200
        if range_header:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        response = web.StreamResponse(status=status, headers=headers)
        await response.prepare(request)

        if as_download:
            asyncio.create_task(db.increment_downloads(target_channel, message_id))
        else:
            asyncio.create_task(db.increment_views(target_channel, message_id))

        # Check in-memory fast header cache
        cached_chunk = await chunk_cache.get(message_id, start, length)
        if cached_chunk:
            try:
                await response.write(cached_chunk)
                await response.write_eof()
                return response
            except Exception:
                return response

        # Round-robin worker client for high bandwidth
        worker_client = client_pool.get_client()

        # Calculate exact 1 MiB chunk offsets for Pyrogram stream_media
        start_chunk = start // PYRO_CHUNK_SIZE
        end_chunk = end // PYRO_CHUNK_SIZE
        chunk_limit = (end_chunk - start_chunk) + 1

        bytes_sent = 0
        chunk_idx = 0
        cached_buffer = bytearray()

        try:
            async for chunk in worker_client.stream_media(
                message=media,
                offset=start_chunk,
                limit=chunk_limit
            ):
                # Slice first chunk if start byte is not aligned to 1MB boundary
                if chunk_idx == 0 and (start % PYRO_CHUNK_SIZE != 0):
                    offset_in_first = start % PYRO_CHUNK_SIZE
                    chunk = chunk[offset_in_first:]

                # Slice last chunk if end byte exceeds requested length
                remaining = length - bytes_sent
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]

                if chunk:
                    await response.write(chunk)
                    bytes_sent += len(chunk)
                    if length <= 5 * 1024 * 1024:
                        cached_buffer.extend(chunk)

                chunk_idx += 1
                if bytes_sent >= length:
                    break

            await response.write_eof()

            if cached_buffer and len(cached_buffer) == length:
                await chunk_cache.put(message_id, start, length, bytes(cached_buffer))

        except (ConnectionResetError, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.error(f"Stream error on channel {target_channel} msg {message_id}: {e}")

        return response
