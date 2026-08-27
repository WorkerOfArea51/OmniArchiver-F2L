# -*- coding: utf-8 -*-
# Thunder/bot/clients.py - In-Memory Multi-Client Pool

import asyncio
from typing import Dict
from pyrogram import Client
from pyrogram.errors import FloodWait
from Thunder.bot import StreamBot, multi_clients, work_loads
from Thunder.utils.logger import logger
from Thunder.vars import Var

async def cleanup_clients():
    for client in multi_clients.values():
        try:
            try:
                await client.stop()
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await client.stop()
        except Exception as e:
            logger.error(f"Error stopping client: {e}", exc_info=True)

async def initialize_clients():
    logger.info("Initializing primary MTProto client...")
    multi_clients[0] = StreamBot
    work_loads[0] = 0

    # Pre-cache storage channels in memory for zero-latency peer resolution
    if Var.CHANNELS:
        logger.info("Pre-caching storage channel access hashes...")
        for ch_id in Var.CHANNELS:
            try:
                chat = await StreamBot.get_chat(ch_id)
                logger.info(f"✅ Storage channel cached: {getattr(chat, 'title', 'Channel')} [{ch_id}]")
            except Exception as e:
                logger.warning(f"Note on channel {ch_id}: {e}")

    if not Var.MULTI_TOKENS:
        logger.info("No auxiliary tokens specified; primary client will handle streams.")
        return

    logger.info(f"Setting up {len(Var.MULTI_TOKENS)} auxiliary stream workers...")

    async def start_client(client_id, token):
        try:
            client = Client(
                name=f"Worker_{client_id}",
                api_id=Var.API_ID,
                api_hash=Var.API_HASH,
                bot_token=token,
                in_memory=True,
                no_updates=True,
                max_concurrent_transmissions=1000,
                sleep_threshold=Var.SLEEP_THRESHOLD
            )
            try:
                await client.start()
            except FloodWait as e:
                logger.warning(f"Worker {client_id} FloodWait ({e.value}s) - sleeping...")
                await asyncio.sleep(e.value)
                await client.start()
            
            work_loads[client_id] = 0
            w_me = await client.get_me()
            logger.info(f"⚡ Stream Worker {client_id} online: @{w_me.username}")
            return client_id, client
        except Exception as e:
            logger.error(f"Failed to start Client ID {client_id}: {e}")
            return None

    clients = await asyncio.gather(*[start_client(i, token) for i, token in enumerate(Var.MULTI_TOKENS, start=1)])
    clients = [c for c in clients if c]

    multi_clients.update(dict(clients))
    logger.info(f"🚀 Client Pool active with {len(multi_clients)} high-speed session(s)!")
