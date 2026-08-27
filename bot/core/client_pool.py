# -*- coding: utf-8 -*-
import asyncio
import logging
from typing import List, Dict, Tuple
from pyrogram import Client
from pyrogram.errors import FloodWait
from bot.core.config import Config

logger = logging.getLogger("ClientPool")

class ClientPoolManager:
    """
    High-Performance Multi-Client Workload Balancer patterned after FileToLink/Thunder.
    """

    def __init__(self):
        self.clients: List[Client] = []
        self.work_loads: Dict[int, int] = {}
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
        self.work_loads[0] = 0
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
                    return idx, worker
                except Exception as e:
                    logger.error(f"Worker {idx} startup note: {e}")
                    return idx, None

            started_workers = await asyncio.gather(
                *[start_worker(i, t) for i, t in enumerate(Config.MULTI_TOKENS, start=1)]
            )
            for idx, w in started_workers:
                if w:
                    self.clients.append(w)
                    self.work_loads[len(self.clients) - 1] = 0

        logger.info(f"🚀 Client Pool active with {len(self.clients)} high-speed session(s)!")

    def select_optimal_client(self) -> Tuple[int, Client]:
        """Selects client with lowest active streaming workload."""
        if not self.clients:
            return 0, self.primary_client
        
        # Pick client with lowest load
        best_id = min(self.work_loads.keys(), key=lambda k: self.work_loads.get(k, 0))
        return best_id, self.clients[best_id]

    def increment_load(self, client_id: int):
        self.work_loads[client_id] = self.work_loads.get(client_id, 0) + 1

    def decrement_load(self, client_id: int):
        if client_id in self.work_loads and self.work_loads[client_id] > 0:
            self.work_loads[client_id] -= 1

    async def stop_all(self):
        logger.info("Stopping all Pyrofork clients...")
        for client in self.clients:
            try:
                if client.is_connected:
                    await client.stop()
            except Exception as e:
                logger.warning(f"Error stopping client: {e}")

client_pool = ClientPoolManager()
