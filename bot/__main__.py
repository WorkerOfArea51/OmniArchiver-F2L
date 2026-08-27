import asyncio
import logging
import signal
import sys
from aiohttp import web
from bot.core.config import Config
from bot.core.database import db
from bot.core.client_pool import client_pool
from bot.server.web_server import setup_web_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("OmniArchiver")

async def start_services():
    """Main asynchronous orchestrator for Bot, Database, and Web Server."""
    logger.info("=" * 60)
    logger.info("   ?? Starting OmniArchiver F2L Video Streaming Engine   ")
    logger.info("=" * 60)

    # 1. Validate Configurations
    Config.validate()

    # 2. Initialize Database Layer
    await db.init()

    # 3. Initialize MTProto Pyrofork Client Pool
    await client_pool.initialize()

    # 4. Start aiohttp Web Server
    app = setup_web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=Config.BIND_ADDRESS, port=Config.PORT)
    await site.start()

    logger.info(f"?? Web Server listening at: http://{Config.BIND_ADDRESS}:{Config.PORT}")
    logger.info(f"? Public Endpoint URL: {Config.BASE_URL}")
    logger.info("?? OmniArchiver F2L is ready to stream!")

    # 5. Keep services running
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Termination signal received. Shutting down gracefully...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handlers on Windows
            pass

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        logger.info("Cleaning up server and MTProto client connections...")
        await runner.cleanup()
        await client_pool.stop_all()
        logger.info("OmniArchiver F2L stopped cleanly.")

def main():
    try:
        asyncio.run(start_services())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")

if __name__ == "__main__":
    main()
