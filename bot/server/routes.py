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
    return web.json_response({
        "status": "ok",
        "service": "OmniArchiver-F2L",
        "uptime": time_formatter(time.time() - SERVER_START_TIME),
        "workers": len(client_pool.clients),
        "base_url": Config.BASE_URL
    })

# Stream routes (both /stream/{msg_id} and /stream/{channel_id}/{msg_id})
@routes.get("/stream/{message_id:\d+}")
async def stream_single(request: web.Request):
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, as_download=False)

@routes.get("/stream/{channel_id:-?\d+}/{message_id:\d+}")
async def stream_multi_channel(request: web.Request):
    channel_id = int(request.match_info["channel_id"])
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, channel_id=channel_id, as_download=False)

# Download routes (both /dl/{msg_id} and /dl/{channel_id}/{msg_id})
@routes.get("/dl/{message_id:\d+}")
@routes.get("/download/{message_id:\d+}")
async def download_single(request: web.Request):
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, as_download=True)

@routes.get("/dl/{channel_id:-?\d+}/{message_id:\d+}")
@routes.get("/download/{channel_id:-?\d+}/{message_id:\d+}")
async def download_multi_channel(request: web.Request):
    channel_id = int(request.match_info["channel_id"])
    msg_id = int(request.match_info["message_id"])
    return await StreamHandler.serve(request, message_id=msg_id, channel_id=channel_id, as_download=True)

# Web Player routes
@routes.get("/watch/{message_id:\d+}")
async def web_player_single(request: web.Request):
    msg_id = int(request.match_info["message_id"])
    record = await db.get_file(msg_id)
    channel_id = record["channel_id"] if record else (Config.CHANNELS[0] if Config.CHANNELS else 0)
    return await render_player(request, channel_id, msg_id)

@routes.get("/watch/{channel_id:-?\d+}/{message_id:\d+}")
async def web_player_multi(request: web.Request):
    channel_id = int(request.match_info["channel_id"])
    msg_id = int(request.match_info["message_id"])
    return await render_player(request, channel_id, msg_id)

async def render_player(request: web.Request, channel_id: int, msg_id: int):
    try:
        msg = await client_pool.primary_client.get_messages(channel_id, msg_id)
        media = get_media_from_message(msg)
        if not media:
            return aiohttp_jinja2.render_template("404.html", request, {"message": "Media not found in archive."})

        file_name, file_size, mime_type, _ = get_file_details(msg)
        stream_url = f"{Config.BASE_URL}/stream/{channel_id}/{msg_id}"
        download_url = f"{Config.BASE_URL}/dl/{channel_id}/{msg_id}"

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

# Search API for StreamHub app
@routes.get("/api/v1/search")
async def api_search(request: web.Request):
    q = request.query.get("q", "").strip()
    if not q:
        return web.json_response({"success": False, "error": "Query 'q' is required."}, status=400)

    results = await db.search_files(q, limit=30)
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
            "episode_num": item.get("episode_num", ""),
            "stream_url": f"{Config.BASE_URL}/stream/{ch}/{mid}",
            "download_url": f"{Config.BASE_URL}/dl/{ch}/{mid}",
            "player_url": f"{Config.BASE_URL}/watch/{ch}/{mid}"
        })

    return web.json_response({"success": True, "count": len(formatted), "results": formatted})
