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
    
    # If WORKER_TOKENS is empty, fallback to primary bot token
    tokens = Telegram.WORKER_TOKENS if Telegram.WORKER_TOKENS else [Telegram.BOT_TOKEN]
    
    for idx, token in enumerate(tokens):
        # Use no_updates=True so worker clients only serve streaming requests without processing updates
        is_primary = (token == Telegram.BOT_TOKEN and idx == 0)
        worker = Client(
            name=f'worker_{idx}',
            api_id=Telegram.API_ID,
            api_hash=Telegram.API_HASH,
            bot_token=token,
            sleep_threshold=-1,
            max_concurrent_transmissions=10,
            no_updates=not is_primary
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
    # Connect MongoDB
    db.connect()
    
    # Start Main Bot
    logger.info("Starting Main Telegram Bot...")
    await TelegramBot.start()
    
    # Start Worker Clients
    init_worker_clients()
    logger.info("Starting %d Worker Clients...", len(worker_clients))
    for idx, client in enumerate(worker_clients):
        if client.name == 'worker_0' and client.bot_token == Telegram.BOT_TOKEN:
            # If worker 0 is the primary token and already started via TelegramBot, we can use TelegramBot
            pass
        else:
            try:
                await client.start()
                logger.info("Worker client #%d started successfully.", idx)
            except Exception as e:
                logger.warning("Failed to start worker client #%d: %s", idx, e)

async def stop_all_clients():
    logger.info("Stopping all clients...")
    for idx, client in enumerate(worker_clients):
        try:
            if client.is_connected:
                await client.stop()
        except Exception:
            pass
    if TelegramBot.is_connected:
        await TelegramBot.stop()
    logger.info("All clients stopped.")
