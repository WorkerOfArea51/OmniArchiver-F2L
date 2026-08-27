# -*- coding: utf-8 -*-
# Thunder/bot/plugins/admin.py - Admin Management & Diagnostics

import os
import sys
import time
import shutil
from pyrogram import Client, filters
from pyrogram.types import Message
from Thunder import __version__, StartTime
from Thunder.bot import multi_clients, work_loads
from Thunder.utils.database import db
from Thunder.utils.time_format import get_readable_time
from Thunder.vars import Var

@Client.on_message(filters.command("stats") & filters.private & filters.incoming & ~filters.me, group=1)
async def stats_handler(client: Client, message: Message):
    message.stop_propagation()
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in Var.AUTH_USERS:
        return

    total_files = await db.get_total_files()
    uptime = get_readable_time(time.time() - StartTime)

    total_load = sum(work_loads.values()) if work_loads else 0
    load_breakdown = ", ".join([f"W{k}: {v}" for k, v in work_loads.items()]) if work_loads else "0"

    total_disk, used_disk, free_disk = shutil.disk_usage(os.path.expanduser("~"))

    text = (
        f"📊 **OmniArchiver Engine Statistics**\n\n"
        f"• **Version:** `v{__version__}`\n"
        f"• **Uptime:** `{uptime}`\n"
        f"• **Indexed Files:** `{total_files:,}`\n"
        f"• **Active Workers:** `{len(multi_clients)}`\n"
        f"• **Current Stream Workload:** `{total_load}` ({load_breakdown})\n"
        f"• **Channels Configured:** `{len(Var.CHANNELS)}`\n"
        f"• **Free Disk Space:** `{free_disk / (1024**3):.2f} GB` / `{total_disk / (1024**3):.2f} GB`\n"
        f"• **Public URL:** `{Var.URL}`"
    )
    await message.reply_text(text, disable_web_page_preview=True)

@Client.on_message(filters.command("status") & filters.incoming & ~filters.me, group=1)
async def status_handler(client: Client, message: Message):
    message.stop_propagation()
    uptime = get_readable_time(time.time() - StartTime)
    await message.reply_text(f"⚡ **OmniArchiver Status:** Operational\n⏳ **Uptime:** `{uptime}`\n👥 **Sessions:** `{len(multi_clients)}`")

@Client.on_message(filters.command("del") & filters.private & filters.incoming & ~filters.me, group=1)
async def delete_handler(client: Client, message: Message):
    message.stop_propagation()
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in Var.AUTH_USERS:
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: `/del <message_id> [channel_id]`")
        return

    mid = int(message.command[1])
    cid = int(message.command[2]) if len(message.command) > 2 else None

    await db.delete_file(mid, cid)
    await message.reply_text(f"🗑️ File record with message ID `{mid}` deleted from database.")

@Client.on_message(filters.command("restart") & filters.private & filters.incoming & ~filters.me, group=1)
async def restart_handler(client: Client, message: Message):
    message.stop_propagation()
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in Var.AUTH_USERS:
        return

    await message.reply_text("🔄 Restarting bot process...")
    os.execv(sys.executable, [sys.executable] + sys.argv)
