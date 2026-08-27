import logging
from typing import List
from pyrogram import Client
from bot.core.config import Config

logger = logging.getLogger(__name__)

class ClientPoolManager:
    """
    Manages primary and auxiliary Pyrofork clients to distribute
    MTProto download streams across multiple Telegram sessions.
    """

    def __init__(self):
        self.clients: List[Client] = []
        self._current_index = 0
        self.primary_client: Client = None

    async def initialize(self):
        """Initializes primary bot and all auxiliary multi-token clients."""
        logger.info("Initializing primary bot client...")
        self.primary_client = Client(
            name="OmniArchiver_Primary",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/plugins"),
            sleep_threshold=Config.SLEEP_THRESHOLD,
            workers=Config.WORKERS,
            workdir=Config.WORKDIR
        )
        await self.primary_client.start()
        self.clients.append(self.primary_client)
        me = await self.primary_client.get_me()
        logger.info(f"Primary Bot online: @{me.username} [{me.id}]")

        # Initialize auxiliary workers if configured
        if Config.MULTI_TOKENS:
            logger.info(f"Setting up {len(Config.MULTI_TOKENS)} auxiliary worker clients...")
            for idx, token in enumerate(Config.MULTI_TOKENS, start=1):
                try:
                    worker = Client(
                        name=f"OmniArchiver_Worker_{idx}",
                        api_id=Config.API_ID,
                        api_hash=Config.API_HASH,
                        bot_token=token,
                        sleep_threshold=Config.SLEEP_THRESHOLD,
                        workers=2,
                        workdir=Config.WORKDIR
                    )
                    await worker.start()
                    self.clients.append(worker)
                    w_me = await worker.get_me()
                    logger.info(f"Auxiliary Worker {idx} online: @{w_me.username}")
                except Exception as e:
                    logger.error(f"Failed to start auxiliary worker {idx}: {e}")

        logger.info(f"Client Pool ready with {len(self.clients)} active session(s).")

    def get_client(self) -> Client:
        """Returns next client in round-robin sequence to distribute network load."""
        if not self.clients:
            return self.primary_client
        client = self.clients[self._current_index % len(self.clients)]
        self._current_index += 1
        return client

    async def stop_all(self):
        """Gracefully stops all client sessions."""
        logger.info("Stopping all Pyrofork clients...")
        for client in self.clients:
            try:
                if client.is_connected:
                    await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client: {e}")

client_pool = ClientPoolManager()
