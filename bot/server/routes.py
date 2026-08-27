import time
import aiohttp_jinja2
from aiohttp import web
from bot.core.config import Config
from bot.core.client_pool import client_pool
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message, humanbytes, time_formatter
from bot.server.stream_handler import StreamHandler

routes = web.RouteTableDef()
SERVER_START_TIME = time.time()

@routes.get("/")
async def index_route(request: web.Request):
    """Status dashboard landing page."""
    total_files = await db.get_total_files()
    context = {
        "title": "OmniArchiver F2L",
        "fqdn": Config.BASE_URL.replace("https://", "").replace("http://", ""),
        "base_url": Config.BASE_URL,
        "uptime": time_formatter(time.time() - SERVER_START_TIME),
        "total_files": total_files,
        "workers_count": len(client_pool.clients),
        "status": "Online & Streaming"
    }
    return aiohttp_jinja2.render_template("index.html", request, context)

@routes.get("/health")
@routes.get("/ping")
async def health_route(request: web.Request):
    """Uptime health check JSON."""
    return web.json_response({
        "status": "ok",
        "service": "OmniArchiver-F2L",
        "uptime": time_formatter(time.time() - SERVER_START_TIME),
        "workers": len(client_pool.clients),
        "base_url": Config.BASE_URL
    })

@routes.get("/stream/{message_id:\\d+}")
@routes.get("/watch_raw/{message_id:\\d+}")
async def stream_media_route(request: web.Request):
    """Raw binary byte-stream endpoint for external video players (ExoPlayer, VLC, mpv)."""
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, as_download=False)

@routes.get("/dl/{message_id:\\d+}")
@routes.get("/download/{message_id:\\d+}")
async def download_media_route(request: web.Request):
    """Direct attachment download endpoint."""
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, as_download=True)

@routes.get("/watch/{message_id:\\d+}")
async def web_player_route(request: web.Request):
    """Responsive Plyr.js HTML5 Web Video Player."""
    msg_id = int(request.match_info["message_id"])
    try:
        msg = await client_pool.primary_client.get_messages(Config.BIN_CHANNEL_ID, msg_id)
        media = get_media_from_message(msg)
        if not media:
            return aiohttp_jinja2.render_template("404.html", request, {"message": "Media not found in archive."})

        file_name, file_size, mime_type, _ = get_file_details(msg)
        stream_url = f"{Config.BASE_URL}/stream/{msg_id}"
        download_url = f"{Config.BASE_URL}/dl/{msg_id}"

        context = {
            "title": file_name,
            "file_name": file_name,
            "file_size": humanbytes(file_size),
            "mime_type": mime_type,
            "stream_url": stream_url,
            "download_url": download_url,
            "message_id": msg_id
        }
        return aiohttp_jinja2.render_template("player.html", request, context)
    except Exception as e:
        return aiohttp_jinja2.render_template("404.html", request, {"message": str(e)})

@routes.get("/api/v1/info/{message_id:\\d+}")
async def file_info_api_route(request: web.Request):
    """JSON API providing full stream metadata for the StreamHub app."""
    msg_id = int(request.match_info["message_id"])
    try:
        msg = await client_pool.primary_client.get_messages(Config.BIN_CHANNEL_ID, msg_id)
        media = get_media_from_message(msg)
        if not media:
            return web.json_response({"success": False, "error": "Media not found"}, status=404)

        file_name, file_size, mime_type, unique_id = get_file_details(msg)

        return web.json_response({
            "success": True,
            "message_id": msg_id,
            "unique_id": unique_id,
            "file_name": file_name,
            "file_size_bytes": file_size,
            "file_size_human": humanbytes(file_size),
            "mime_type": mime_type,
            "stream_url": f"{Config.BASE_URL}/stream/{msg_id}",
            "download_url": f"{Config.BASE_URL}/dl/{msg_id}",
            "player_url": f"{Config.BASE_URL}/watch/{msg_id}"
        })
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)
