# -*- coding: utf-8 -*-
import os
import sys
import fcntl

# Enforce strictly 1 running instance with self-healing PID verification
_lock_file = None
def ensure_single_instance():
    global _lock_file
    lock_path = os.path.join(os.path.expanduser("~"), ".omni_bot_singleton.lock")
    try:
        _lock_file = open(lock_path, "a+")
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.seek(0)
        _lock_file.truncate()
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
    except (IOError, OSError):
        # Check if the process holding the lock is actually alive
        try:
            with open(lock_path, "r") as f:
                old_pid = int(f.read().strip())
            os.kill(old_pid, 0)
            print(f"⚠️ Process {old_pid} is already running active. Exiting duplicate.")
            sys.exit(0)
        except Exception:
            # Stale lock from killed process - override safely
            try:
                _lock_file = open(lock_path, "w")
                fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _lock_file.write(str(os.getpid()))
                _lock_file.flush()
            except Exception:
                pass

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
    # 4. Start Dual IPv4 + IPv6 Web Server for Alwaysdata & VPS
    port = int(os.environ.get("PORT", 8100))
    always_ip = os.environ.get("IP")

    # Bind specific Alwaysdata IP if provided
    if always_ip:
        try:
            site_always = web.TCPSite(runner, host=always_ip, port=port)
            await site_always.start()
            logger.info(f"🌐 Alwaysdata IP listening at: http://[{always_ip}]:{port}")
        except Exception as e:
            logger.warning(f"Alwaysdata IP bind note: {e}")

    # Bind IPv6 universal (::)
    try:
        site_v6 = web.TCPSite(runner, host="::", port=port)
        await site_v6.start()
        logger.info(f"🌐 IPv6 listening at: http://[::]:{port}")
    except Exception as e:
        logger.warning(f"IPv6 bind note: {e}")

    # Bind IPv4 universal (0.0.0.0)
    try:
        site_v4 = web.TCPSite(runner, host="0.0.0.0", port=port)
        await site_v4.start()
        logger.info(f"🌐 IPv4 listening at: http://0.0.0.0:{port}")
    except Exception as e:
        logger.warning(f"IPv4 bind note: {e}")

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