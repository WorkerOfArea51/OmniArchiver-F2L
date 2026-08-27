# -*- coding: utf-8 -*-
# Thunder/__main__.py - OmniArchiver F2L Main Orchestrator

import os
import sys
import glob
import asyncio
import importlib.util
from datetime import datetime
from pathlib import Path

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

try:
    import fcntl
    # Self-healing Single-Instance File Lock for Linux/Alwaysdata
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
            try:
                with open(lock_path, "r") as f:
                    old_pid = int(f.read().strip())
                os.kill(old_pid, 0)
                print(f"⚠️ Process {old_pid} is already running active. Exiting duplicate.")
                sys.exit(0)
            except Exception:
                try:
                    _lock_file = open(lock_path, "w")
                    fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    _lock_file.write(str(os.getpid()))
                    _lock_file.flush()
                except Exception:
                    pass

    ensure_single_instance()
except ImportError:
    pass

from aiohttp import web
from pyrogram import idle
from pyrogram.errors import FloodWait

from Thunder import __version__, StartTime
from Thunder.bot import StreamBot
from Thunder.bot.clients import cleanup_clients, initialize_clients
from Thunder.server import web_server
from Thunder.utils.commands import set_commands
from Thunder.utils.database import db
from Thunder.utils.logger import logger
from Thunder.vars import Var

PLUGIN_PATH = "Thunder/bot/plugins/*.py"

def print_banner():
    banner = f"""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║   ████████╗██╗  ██╗██╗   ██╗███╗   ██╗██████╗ ███████╗██████╗     ║
║   ╚══██╔══╝██║  ██║██║   ██║████╗  ██║██╔══██╗██╔════╝██╔══██╗    ║
║      ██║   ███████║██║   ██║██╔██╗ ██║██║  ██║█████╗  ██████╔╝    ║
║      ██║   ██╔══██║██║   ██║██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗    ║
║      ██║   ██║  ██║╚██████╔╝██║ ╚████║██████╔╝███████╗██║  ██║    ║
║      ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝    ║
║                                                                   ║
║            OmniArchiver F2L Video Streaming Engine v{__version__}          ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)

async def import_plugins():
    plugins = glob.glob(PLUGIN_PATH)
    if not plugins:
        logger.warning("No plugins found to import!")
        return 0

    success_count = 0
    for file_path in plugins:
        try:
            plugin_path = Path(file_path)
            plugin_name = plugin_path.stem
            import_path = f"Thunder.bot.plugins.{plugin_name}"

            spec = importlib.util.spec_from_file_location(import_path, plugin_path)
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[import_path] = module
            spec.loader.exec_module(module)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to import plugin {Path(file_path).stem}: {e}")

    logger.info(f"Loaded {success_count} plugins successfully.")
    return success_count

async def start_services():
    start_time = datetime.now()
    print_banner()

    # 1. Initialize Database
    logger.info("Initializing Database...")
    await db.init()

    # 2. Start Primary Bot
    logger.info("Starting Primary Telegram Bot...")
    try:
        try:
            await StreamBot.start()
        except FloodWait as e:
            logger.warning(f"FloodWait on bot start: {e.value}s")
            await asyncio.sleep(e.value)
            await StreamBot.start()

        bot_info = await StreamBot.get_me()
        StreamBot.username = bot_info.username
        logger.info(f"Bot initialized as @{StreamBot.username} [{bot_info.id}]")

        try:
            await set_commands()
        except Exception as e:
            logger.debug(f"Command set note: {e}")

    except Exception as e:
        logger.critical(f"Failed to start Primary Bot: {e}", exc_info=True)
        return

    # 3. Start Multi-Clients
    try:
        await initialize_clients()
    except Exception as e:
        logger.error(f"Error initializing client pool: {e}", exc_info=True)

    # 4. Import Plugins
    await import_plugins()

    # 5. Start aiohttp Web Server (Dual IPv4 + IPv6 for Alwaysdata)
    logger.info("Starting aiohttp Streaming Web Server...")
    app_runner = web.AppRunner(await web_server())
    await app_runner.setup()

    bound = False
    for host in ["0.0.0.0", "::", "127.0.0.1"]:
        try:
            site = web.TCPSite(app_runner, host=host, port=Var.PORT)
            await site.start()
            logger.info(f"🌐 Web Server listening at: http://{host}:{Var.PORT}")
            bound = True
        except Exception as e:
            logger.debug(f"Host bind {host}:{Var.PORT} note: {e}")

    if not bound:
        site = web.TCPSite(app_runner, port=Var.PORT)
        await site.start()

    logger.info(f"🚀 Public Endpoint: {Var.URL}")
    logger.info("✨ OmniArchiver F2L is online and ready!")

    try:
        await idle()
    finally:
        logger.info("Shutting down OmniArchiver services...")
        try:
            await cleanup_clients()
        except Exception:
            pass
        try:
            await app_runner.cleanup()
        except Exception:
            pass
        try:
            await db.close()
        except Exception:
            pass
        logger.info("OmniArchiver stopped cleanly.")

def main():
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        print("Bot stopped by user.")

if __name__ == '__main__':
    main()
