# -*- coding: utf-8 -*-
import os
import sys
import fcntl

# Enforce strictly 1 running instance across the entire server
_lock_file = None
def ensure_single_instance():
    global _lock_file
    lock_path = os.path.join(os.path.expanduser("~"), ".omni_bot_singleton.lock")
    _lock_file = open(lock_path, "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print("⚠️ Duplicate instance detected! Another bot process is already active. Exiting cleanly.")
        sys.exit(0)

ensure_single_instance()

import json
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
    # 4. Start Dual-Stack (IPv4 & IPv6) Web Server for 100% Reverse Proxy Compatibility
    bound_any = False
    for host in ["0.0.0.0", "::", "127.0.0.1"]:
        try:
            site = web.TCPSite(runner, host=host, port=Config.PORT)
            await site.start()
            logger.info(f"🌐 Web Server bound to: http://{host}:{Config.PORT}")
            bound_any = True
        except Exception as e:
            logger.debug(f"Host bind {host}:{Config.PORT} skipped ({e})")

    if not bound_any:
        site = web.TCPSite(runner, port=Config.PORT)
        await site.start()

    logger.info(f"🚀 Public Endpoint URL: {Config.BASE_URL}")
    logger.info("✨ OmniArchiver F2L is ready to stream & download!")

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