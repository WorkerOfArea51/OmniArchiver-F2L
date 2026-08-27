import asyncio
import logging
from typing import Tuple
from aiohttp import web
from bot.core.config import Config
from bot.core.client_pool import client_pool
from bot.core.cache import chunk_cache
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

class StreamHandler:
    """Production RFC 7233 HTTP Range Stream Engine with MTProto Chunk Streaming & LRU Caching."""

    @staticmethod
    def parse_range(range_header: str, file_size: int) -> Tuple[int, int, int]:
        """
        Parses HTTP Range header (RFC 7233).
        Returns: (start_byte, end_byte, content_length)
        """
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
            # Suffix range: bytes=-500 (last 500 bytes)
            length = int(end_str)
            if length > file_size:
                length = file_size
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
    async def serve(cls, request: web.Request, message_id: int, as_download: bool = False) -> web.StreamResponse:
        """Streams Telegram file with range seeking and LRU chunk acceleration."""
        try:
            # Fetch message from bin channel using primary client
            msg = await client_pool.primary_client.get_messages(Config.BIN_CHANNEL_ID, message_id)
        except Exception as e:
            logger.error(f"Failed to fetch message {message_id}: {e}")
            raise web.HTTPNotFound(text="Media not found or deleted from storage.")

        media = get_media_from_message(msg)
        if not media:
            raise web.HTTPNotFound(text="Message contains no streamable media.")

        file_name, file_size, mime_type, _ = get_file_details(msg)

        # Parse Range
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
        safe_filename = file_name.replace('"', '\\"')

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

        # Track views or downloads asynchronously
        if as_download:
            asyncio.create_task(db.increment_downloads(message_id))
        else:
            asyncio.create_task(db.increment_views(message_id))

        # Check LRU cache for short header requests (e.g. initial 256KB-2MB)
        cached_chunk = await chunk_cache.get(message_id, start, length)
        if cached_chunk:
            try:
                await response.write(cached_chunk)
                await response.write_eof()
                return response
            except Exception:
                return response

        # Obtain a client from worker pool to balance MTProto load
        worker_client = client_pool.get_client()

        try:
            cached_buffer = bytearray()
            async for chunk in worker_client.stream_media(
                message=msg,
                offset=start,
                limit=length
            ):
                await response.write(chunk)
                
                # Cache initial 5MB or last 2MB for future instant seeking
                if length <= 5 * 1024 * 1024:
                    cached_buffer.extend(chunk)

            await response.write_eof()

            if cached_buffer and len(cached_buffer) == length:
                await chunk_cache.put(message_id, start, length, bytes(cached_buffer))

        except (ConnectionResetError, asyncio.CancelledError):
            logger.debug(f"Consumer disconnected on msg {message_id}")
        except Exception as e:
            logger.error(f"Stream error on msg {message_id}: {e}")

        return response
