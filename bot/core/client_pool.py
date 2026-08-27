# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import List
from pyrogram import Client
from pyrogram.errors import FloodWait
from bot.core.config import Config

logger = logging.getLogger("ClientPool")

class ClientPoolManager:
    """
    High-Performance Multi-Client Engine patterned after FileToLink/Thunder.
    """

    def __init__(self):
        self.clients: List[Client] = []
        self._current_index = 0
        self.primary_client: Client = None

    async def initialize(self):
        logger.info("Initializing primary MTProto client...")
        self.primary_client = Client(
            name="OmniArchiver_Primary",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN,
            plugins=dict(root="bot/plugins"),
            sleep_threshold=Config.SLEEP_THRESHOLD,
            workers=Config.WORKERS,
            in_memory=True,
            max_concurrent_transmissions=1000
        )

        try:
            await self.primary_client.start()
        except FloodWait as e:
            logger.warning(f"FloodWait on primary client ({e.value}s) - waiting...")
            await asyncio.sleep(e.value)
            await self.primary_client.start()

        self.clients.append(self.primary_client)
        me = await self.primary_client.get_me()
        logger.info(f"Primary Bot online: @{me.username} [{me.id}]")

        # Pre-cache storage channels in memory for zero-latency peer resolution
        if Config.CHANNELS:
            logger.info("Pre-caching storage channel access hashes...")
            for ch_id in Config.CHANNELS:
                try:
                    chat = await self.primary_client.get_chat(ch_id)
                    logger.info(f"✅ Storage channel cached: {getattr(chat, 'title', 'Channel')} [{ch_id}]")
                except Exception as e:
                    logger.warning(f"Note on channel {ch_id}: {e}")


        # Initialize auxiliary workers for dedicated MTProto streaming
        if Config.MULTI_TOKENS:
            logger.info(f"Setting up {len(Config.MULTI_TOKENS)} auxiliary stream workers...")

            async def start_worker(idx, token):
                try:
                    worker = Client(
                        name=f"Worker_{idx}",
                        api_id=Config.API_ID,
                        api_hash=Config.API_HASH,
                        bot_token=token,
                        in_memory=True,
                        no_updates=True,
                        sleep_threshold=Config.SLEEP_THRESHOLD,
                        max_concurrent_transmissions=1000
                    )
                    try:
                        await worker.start()
                    except FloodWait as e:
                        logger.warning(f"Worker {idx} FloodWait ({e.value}s), sleeping...")
                        await asyncio.sleep(e.value)
                        await worker.start()

                    w_me = await worker.get_me()
                    logger.info(f"⚡ Stream Worker {idx} online: @{w_me.username}")
                    return worker
                except Exception as e:
                    logger.error(f"Worker {idx} startup note: {e}")
                    return None

            started_workers = await asyncio.gather(
                *[start_worker(i, t) for i, t in enumerate(Config.MULTI_TOKENS, start=1)]
            )
            for w in started_workers:
                if w:
                    self.clients.append(w)

        logger.info(f"🚀 Client Pool active with {len(self.clients)} high-speed session(s)!")

    def get_client(self) -> Client:
        """Returns next client in round-robin sequence to distribute download bandwidth."""
        if not self.clients:
            return self.primary_client
        client = self.clients[self._current_index % len(self.clients)]
        self._current_index += 1
        return client

    async def stop_all(self):
        logger.info("Stopping all Pyrofork clients...")
        for client in self.clients:
            try:
                if client.is_connected:
                    await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client: {e}")

client_pool = ClientPoolManager()
