import json
import os
import sys
import psutil
import time
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.core.config import Config
from bot.core.database import db
from bot.core.client_pool import client_pool
from bot.core.file_properties import humanbytes, time_formatter

ADMIN_START_TIME = time.time()

def is_admin(user_id: int) -> bool:
    return (Config.OWNER_ID and user_id == Config.OWNER_ID) or (user_id in Config.AUTH_USERS)

@Client.on_message(filters.command("stats") & filters.private & filters.incoming & ~filters.me)
async def stats_handler(client: Client, message: Message):
    """Displays real-time system, memory, and database metrics."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        await message.reply_text("⛔ **Admin Only:** You do not have permission to view stats.")
        return

    msg = await message.reply_text("📊 *Gathering performance metrics...*")

    process = psutil.Process(os.getpid())
    ram_usage = process.memory_info().rss
    ram_percent = process.memory_percent()
    cpu_percent = psutil.cpu_percent(interval=0.3)
    sys_ram = psutil.virtual_memory()

    total_files = await db.get_total_files()
    uptime = time_formatter(time.time() - ADMIN_START_TIME)

    text = (
        f"📊 **OmniArchiver F2L — Performance Dashboard**\n\n"
        f"⏱️ **Process Uptime:** `{uptime}`\n"
        f"🧠 **Bot RAM Footprint:** `{humanbytes(ram_usage)}` ({ram_percent:.1f}%)\n"
        f"💻 **System RAM:** `{humanbytes(sys_ram.used)} / {humanbytes(sys_ram.total)}`\n"
        f"⚡ **CPU Usage:** `{cpu_percent}%`\n"
        f"📁 **Indexed Files:** `{total_files}`\n"
        f"🚀 **Worker Pool:** `{len(client_pool.clients)} Client Session(s)`\n"
        f"🗄️ **Database Mode:** `{'MongoDB' if db.is_mongo else 'Embedded SQLite'}`\n"
        f"🌐 **Endpoint Host:** `{Config.BASE_URL}`"
    )

    await msg.edit_text(text)

@Client.on_message(filters.command("status") & filters.incoming & ~filters.me)
async def status_handler(client: Client, message: Message):
    """Quick operational health check."""
    uptime = time_formatter(time.time() - ADMIN_START_TIME)
    await message.reply_text(
        f"🟢 **OmniArchiver F2L is Operational!**\n"
        f"• Workers: `{len(client_pool.clients)}`\n"
        f"• Uptime: `{uptime}`\n"
        f"• Host: `{Config.BASE_URL}`"
    )

@Client.on_message(filters.command("del") & filters.private & filters.incoming & ~filters.me)
async def delete_handler(client: Client, message: Message):
    """Deletes a file from both the Telegram Channel and the Database index."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin(user_id):
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.reply_text("Usage: `/del <message_id>`\nExample: `/del 145`")
        return

    target_msg_id = int(parts[1])
    record = await db.get_file(target_msg_id)

    target_channel = record["channel_id"] if record else (Config.CHANNELS[0] if Config.CHANNELS else 0)

    # 1. Delete from Telegram channel
    deleted_from_tg = False
    if target_channel:
        try:
            await client_pool.primary_client.delete_messages(target_channel, target_msg_id)
            deleted_from_tg = True
        except Exception as e:
            pass

    # 2. Delete from Database index
    if not db.is_mongo:
        import aiosqlite
        async with aiosqlite.connect(db.sqlite_path) as sdb:
            await sdb.execute("DELETE FROM files WHERE message_id = ?", (target_msg_id,))
            await sdb.commit()
    else:
        await db._mongo_db.files.delete_one({"message_id": target_msg_id})

    await message.reply_text(
        f"🗑️ **Message `{target_msg_id}` deleted successfully!**\n"
        f"• Telegram Channel: `{'Deleted' if deleted_from_tg else 'Not Found/Failed'}`\n"
        f"• Database Search Index: `Removed`"
    )

@Client.on_message(filters.command("restart") & filters.private & filters.incoming & ~filters.me)
async def restart_handler(client: Client, message: Message):
    """Graceful restart with automatic completion notification."""
    user_id = message.from_user.id if message.from_user else 0
    if Config.OWNER_ID and user_id != Config.OWNER_ID:
        await message.reply_text("⛔ Only the bot owner can trigger a restart.")
        return

    msg = await message.reply_text("🔄 **Restarting OmniArchiver F2L Service...**\nPlease wait a few seconds.")
    
    # Save state to send confirmation on boot
    state_file = os.path.join(Config.WORKDIR, ".restart_notice.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"chat_id": message.chat.id, "message_id": msg.id, "time": time.time()}, f)
    except Exception:
        pass

    os.execl(sys.executable, sys.executable, *sys.argv)
