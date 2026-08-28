from hydrogram import Client
from logging import getLogger
from itertools import cycle
from bot.config import Telegram
from bot.database import db

logger = getLogger('bot')

# Main Bot Client (Processes user commands, interactions, and updates)
TelegramBot = Client(
    name='bot_main',
    api_id=Telegram.API_ID,
    api_hash=Telegram.API_HASH,
    bot_token=Telegram.BOT_TOKEN,
    plugins=dict(root='bot.plugins'),
    sleep_threshold=-1,
    max_concurrent_transmissions=10
)

# Multi-Client Worker Pool (Used for fast parallel chunk downloading and streaming)
worker_clients: list[Client] = []
_worker_cycler = None

def init_worker_clients():
    global worker_clients, _worker_cycler
    worker_clients.clear()
    
    # 1. The primary TelegramBot is worker #0 (reuse existing connection, no duplicate session!)
    worker_clients.append(TelegramBot)
    
    # 2. Add extra worker bots from MULTI_BOT_TOKENS
    for idx, token in enumerate(Telegram.MULTI_BOT_TOKENS, start=1):
        if token and token != Telegram.BOT_TOKEN:
            worker = Client(
                name=f'worker_{idx}',
                api_id=Telegram.API_ID,
                api_hash=Telegram.API_HASH,
                bot_token=token,
                sleep_threshold=-1,
                max_concurrent_transmissions=10,
                no_updates=True
            )
            worker_clients.append(worker)
        
    _worker_cycler = cycle(worker_clients)
    logger.info("Initialized %d bot client(s) in worker pool.", len(worker_clients))

def get_worker_client() -> Client:
    global _worker_cycler
    if not worker_clients:
        return TelegramBot
    if _worker_cycler is None:
        _worker_cycler = cycle(worker_clients)
    return next(_worker_cycler)

async def start_all_clients():
    import os
    import time

    # Connect MongoDB
    db.connect()
    
    # Start Main Bot
    logger.info("Starting Main Telegram Bot...")
    await TelegramBot.start()

    # Check and resolve pending restart notification
    if os.path.exists('.restart_state.txt'):
        try:
            with open('.restart_state.txt', 'r') as f:
                parts = f.read().strip().split()
            if len(parts) >= 2:
                chat_id = int(parts[0])
                msg_id = int(parts[1])
                duration_str = ""
                if len(parts) >= 3:
                    elapsed = round(time.time() - float(parts[2]), 1)
                    duration_str = f" in `{elapsed}s`"
                await TelegramBot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"✅ **OmniArchiver Bot rebooted successfully{duration_str}!**\n\n"
                        f"🚀 All worker bots, MongoDB connection, and web server are active."
                    )
                )
        except Exception as e:
            logger.warning("Failed to edit restart notification: %s", e)
        finally:
            try:
                os.remove('.restart_state.txt')
            except Exception:
                pass
    
    # Start Worker Clients
    init_worker_clients()
    logger.info("Starting Worker Clients pool (%d total)...", len(worker_clients))
    for idx, client in enumerate(worker_clients):
        if client == TelegramBot:
            continue
        try:
            await client.start()
            logger.info("Worker client #%d started successfully.", idx)
        except Exception as e:
            logger.warning("Failed to start worker client #%d: %s", idx, e)

async def stop_all_clients():
    logger.info("Stopping all clients...")
    for client in worker_clients:
        if client == TelegramBot:
            continue
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    if TelegramBot.is_connected:
        await TelegramBot.stop()
    logger.info("All clients stopped.")
