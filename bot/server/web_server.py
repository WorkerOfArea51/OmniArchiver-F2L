import os
import jinja2
import aiohttp_jinja2
from aiohttp import web
from bot.server.routes import routes

def setup_web_server() -> web.Application:
    """Configures the aiohttp web server with Jinja2 and CORS."""
    app = web.Application()

    # Configure Jinja2 templates directory
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(templates_dir)
    )

    # Register Routes
    app.add_routes(routes)

    # Universal CORS Middleware for App Players (Flutter / ExoPlayer / Web)
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Range, Content-Type, Authorization"
        return response

    app.middlewares.append(cors_middleware)
    return app
