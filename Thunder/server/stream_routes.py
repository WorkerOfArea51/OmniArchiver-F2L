# -*- coding: utf-8 -*-
# Thunder/server/stream_routes.py - OmniArchiver Streaming Server & API

import re
import time
import secrets
import asyncio
from urllib.parse import quote, unquote
from aiohttp import web
from Thunder import __version__, StartTime
from Thunder.bot import StreamBot, multi_clients, work_loads
from Thunder.server.exceptions import FileNotFound, InvalidHash
from Thunder.utils.custom_dl import ByteStreamer
from Thunder.utils.database import db
from Thunder.utils.file_properties import get_media, get_fname, get_fsize, get_uniqid, get_hash
from Thunder.utils.human_readable import humanbytes
from Thunder.utils.logger import logger
from Thunder.utils.render_template import render_media_page
from Thunder.utils.time_format import get_readable_time
from Thunder.vars import Var

routes = web.RouteTableDef()

CHUNK_SIZE = 1024 * 1024
RANGE_REGEX = re.compile(r"^bytes=(?P<start>\d*)-(?P<end>\d*)$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "Range, Content-Type, Authorization, *",
    "Access-Control-Expose-Headers": "Content-Length, Content-Range, Content-Disposition, Accept-Ranges",
}

streamers = {}

def get_streamer(client_id: int, channel_id: int = None) -> ByteStreamer:
    if client_id not in multi_clients:
        client_id = 0
    return ByteStreamer(multi_clients[client_id], chat_id=channel_id or Var.BIN_CHANNEL)

def select_optimal_client() -> tuple[int, ByteStreamer]:
    if not work_loads:
        return 0, get_streamer(0)
    client_id = min(work_loads.keys(), key=lambda x: work_loads[x])
    return client_id, get_streamer(client_id)

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

async def serve_media(
    request: web.Request,
    message_id: int,
    channel_id: int = None,
    as_download: bool = False
) -> web.Response:
    target_channel = channel_id
    if not target_channel:
        record = await db.get_file(message_id)
        if record and record.get("channel_id"):
            target_channel = record["channel_id"]
        elif Var.CHANNELS:
            target_channel = Var.CHANNELS[0]

    if not target_channel:
        raise web.HTTPNotFound(text="Target channel not configured.", headers=CORS_HEADERS)

    client_id, streamer = select_optimal_client()
    work_loads[client_id] = work_loads.get(client_id, 0) + 1

    try:
        try:
            msg = await streamer.get_message(message_id, target_channel)
        except Exception:
            streamer = get_streamer(0, target_channel)
            msg = await streamer.get_message(message_id, target_channel)

        media = get_media(msg)
        if not media:
            raise web.HTTPNotFound(text="Message contains no streamable media.", headers=CORS_HEADERS)

        file_name = get_fname(msg)
        file_size = get_fsize(msg)
        mime_type = getattr(media, "mime_type", "video/mp4") or "application/octet-stream"

        if file_size == 0:
            raise web.HTTPNotFound(text="File size is reported as zero.", headers=CORS_HEADERS)

        range_header = request.headers.get("Range", "")
        start, end = parse_range_header(range_header, file_size)
        content_length = end - start + 1

        if start == 0 and end == file_size - 1:
            range_header = ""

        disposition = "attachment" if as_download else "inline"
        safe_filename = file_name.replace('"', '\\"')

        headers = {
            "Content-Type": mime_type,
            "Content-Length": str(content_length),
            "Content-Disposition": f'{disposition}; filename="{safe_filename}"; filename*=UTF-8\'\'{quote(file_name)}',
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=31536000",
            "Connection": "keep-alive",
            **CORS_HEADERS,
        }

        if range_header:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        if request.method == "HEAD":
            work_loads[client_id] = max(0, work_loads.get(client_id, 1) - 1)
            return web.Response(
                status=206 if range_header else 200,
                headers=headers
            )

        if as_download:
            asyncio.create_task(db.increment_downloads(target_channel, message_id))
        else:
            asyncio.create_task(db.increment_views(target_channel, message_id))

        async def stream_generator():
            try:
                bytes_sent = 0
                bytes_to_skip = start % CHUNK_SIZE

                async for chunk in streamer.stream_file(
                    msg,
                    channel_id=target_channel,
                    offset=start,
                    limit=content_length
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
                        yield chunk
                        bytes_sent += len(chunk)

                    if bytes_sent >= content_length:
                        break
            finally:
                work_loads[client_id] = max(0, work_loads.get(client_id, 1) - 1)

        return web.Response(
            status=206 if range_header else 200,
            body=stream_generator(),
            headers=headers
        )

    except Exception as e:
        work_loads[client_id] = max(0, work_loads.get(client_id, 1) - 1)
        logger.error(f"Error streaming message {message_id}: {e}")
        raise web.HTTPNotFound(text=str(e), headers=CORS_HEADERS)

# --- Routes Definition ---

@routes.options(r"/{path:.+}")
async def options_handler(request: web.Request):
    return web.Response(headers={**CORS_HEADERS, "Access-Control-Max-Age": "86400"})

@routes.get("/")
async def root_handler(request: web.Request):
    total_files = await db.get_total_files()
    uptime = time.time() - StartTime
    return web.json_response({
        "service": "OmniArchiver-F2L",
        "version": __version__,
        "status": "operational",
        "total_indexed_files": total_files,
        "workers": len(multi_clients),
        "uptime": get_readable_time(uptime),
        "endpoint": Var.URL
    }, headers=CORS_HEADERS)

@routes.get("/health")
@routes.get("/ping")
async def health_handler(request: web.Request):
    return web.json_response({"status": "ok", "service": "OmniArchiver-F2L"}, headers=CORS_HEADERS)

# Stream & Download Endpoints
@routes.get(r"/dl/{message_id:\d+}")
@routes.get(r"/download/{message_id:\d+}")
async def dl_single(request: web.Request):
    return await serve_media(request, int(request.match_info["message_id"]), as_download=True)

@routes.get(r"/dl/{channel_id:-?\d+}/{message_id:\d+}")
@routes.get(r"/download/{channel_id:-?\d+}/{message_id:\d+}")
async def dl_multi(request: web.Request):
    return await serve_media(
        request,
        int(request.match_info["message_id"]),
        channel_id=int(request.match_info["channel_id"]),
        as_download=True
    )

@routes.get(r"/stream/{message_id:\d+}")
async def stream_single(request: web.Request):
    return await serve_media(request, int(request.match_info["message_id"]), as_download=False)

@routes.get(r"/stream/{channel_id:-?\d+}/{message_id:\d+}")
async def stream_multi(request: web.Request):
    return await serve_media(
        request,
        int(request.match_info["message_id"]),
        channel_id=int(request.match_info["channel_id"]),
        as_download=False
    )

# Cinema Web Player (Vidstack)
@routes.get(r"/watch/{channel_id:-?\d+}/{message_id:\d+}")
@routes.get(r"/watch/{message_id:\d+}")
async def watch_handler(request: web.Request):
    msg_id = int(request.match_info["message_id"])
    ch_id = int(request.match_info.get("channel_id") or (Var.CHANNELS[0] if Var.CHANNELS else 0))
    try:
        msg = await StreamBot.get_messages(ch_id, msg_id)
        file_name = get_fname(msg)
        src = f"{Var.URL}stream/{ch_id}/{msg_id}"
        rendered_html = await render_media_page(file_name, src, requested_action='stream')
        return web.Response(text=rendered_html, content_type='text/html', headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"Error rendering watch page: {e}")
        raise web.HTTPNotFound(text="Media not found")

# Dynamic M3U / M3U8 Playlist
@routes.get(r"/playlist/{query}.m3u")
@routes.get(r"/playlist/{query}.m3u8")
async def playlist_handler(request: web.Request):
    raw_query = request.match_info["query"]
    query = unquote(raw_query).replace("_", " ").strip()
    results = await db.search_files(query, limit=200)

    if not results:
        return web.Response(status=404, text=f"#EXTM3U\n# No media found for query: {query}", headers=CORS_HEADERS)

    m3u_lines = ["#EXTM3U", f"# Playlist for: {query}"]
    for idx, item in enumerate(results, start=1):
        ch = item["channel_id"]
        mid = item["message_id"]
        ep = item.get("episode_num") or f"EP {idx:02d}"
        file_name = item.get("file_name", f"Episode_{idx}.mkv")
        arc = item.get("arc_name") or item.get("series_name") or query
        stream_url = f"{Var.URL}stream/{ch}/{mid}"
        m3u_lines.append(f'#EXTINF:-1 tvg-id="{mid}" tvg-name="{ep}" group-title="{arc}",{ep} - {file_name}')
        m3u_lines.append(stream_url)

    content = "\n".join(m3u_lines)
    return web.Response(
        text=content,
        content_type="audio/x-mpegurl",
        headers={
            "Content-Disposition": f'attachment; filename="{query.replace(" ", "_")}.m3u"',
            "Access-Control-Allow-Origin": "*"
        }
    )

# StreamHub Search JSON API
@routes.get("/api/v1/search")
async def search_api_handler(request: web.Request):
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"success": False, "error": "Query parameter 'q' is required."}, status=400, headers=CORS_HEADERS)

    results = await db.search_files(q, limit=60)
    formatted = []
    for item in results:
        ch = item["channel_id"]
        mid = item["message_id"]
        formatted.append({
            "message_id": mid,
            "channel_id": ch,
            "file_name": item["file_name"],
            "file_size_human": humanbytes(item["file_size"]),
            "mime_type": item["mime_type"],
            "series_name": item.get("series_name", ""),
            "arc_name": item.get("arc_name", ""),
            "episode_num": item.get("episode_num", ""),
            "stream_url": f"{Var.URL}stream/{ch}/{mid}",
            "download_url": f"{Var.URL}dl/{ch}/{mid}",
            "player_url": f"{Var.URL}watch/{ch}/{mid}"
        })

    return web.json_response({
        "success": True,
        "count": len(formatted),
        "playlist_url": f"{Var.URL}playlist/{quote(q.replace(' ', '_'))}.m3u",
        "results": formatted
    }, headers=CORS_HEADERS)
