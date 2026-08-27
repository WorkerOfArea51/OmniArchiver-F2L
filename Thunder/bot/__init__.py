# -*- coding: utf-8 -*-
from pyrogram import Client
from Thunder.vars import Var

StreamBot = Client(
    name="OmniArchiver_Primary",
    api_id=Var.API_ID,
    api_hash=Var.API_HASH,
    bot_token=Var.BOT_TOKEN,
    sleep_threshold=Var.SLEEP_THRESHOLD,
    workers=Var.WORKERS,
    in_memory=True,
    max_concurrent_transmissions=1000,
)

multi_clients = {}
work_loads = {}
