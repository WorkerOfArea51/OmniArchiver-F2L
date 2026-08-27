import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.core.config import Config
from bot.core.file_properties import time_formatter
from bot.core.client_pool import client_pool

BOT_START_TIME = time.time()

START_TEXT = """
?? **Hello, {first_name}!**

Welcome to **OmniArchiver F2L** ?
High-performance Telegram **File-to-Link & Video Streaming Gateway**.

?? **Core Capabilities:**
• **Instant Direct Stream Links** with Multi-Client DC connection pooling.
• **RFC 7233 HTTP 206 Range Seeking** (instant seek in ExoPlayer, VLC, mpv).
• **Embedded HTML5 Plyr.js Web Player**.
• **In-Memory LRU Ring Buffer** for 0ms initial metadata probing.
• Native JSON API integration for **StreamHub**.

Send or forward any media file to get instant streaming links!
"""

HELP_TEXT = """
?? **OmniArchiver F2L — Help & Commands**

• **Generate Stream Link:** Send or forward any video/audio/document to the bot.
• **Channel Auto-Sync:** Add the bot as an admin in your storage channel.
• `/link <tg_link>` — Generate stream link from public message URL.
• `/stats` — Real-time memory, CPU, and stream worker stats (Admin).
• `/status` — Quick server health and connection status.
• `/ping` — Measure bot latency.
"""

ABOUT_TEXT = """
?? **About OmniArchiver F2L**

• **Core Framework:** Pyrofork MTProto + aiohttp Async Server
• **Connection Workers:** {workers} Active Session(s)
• **Range Seek:** Supported (RFC 7233)
• **Host Domain:** {fqdn}
"""

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    first_name = message.from_user.first_name if message.from_user else "User"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("?? Web Dashboard", url=Config.BASE_URL),
            InlineKeyboardButton("?? Help", callback_data="help_data")
        ],
        [
            InlineKeyboardButton("?? About", callback_data="about_data")
        ]
    ])
    await message.reply_text(
        START_TEXT.format(first_name=first_name),
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("help") & filters.private)
async def help_handler(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("?? Back", callback_data="start_data")]])
    await message.reply_text(HELP_TEXT, reply_markup=keyboard)

@Client.on_message(filters.command("about") & filters.private)
async def about_handler(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("?? Back", callback_data="start_data")]])
    await message.reply_text(
        ABOUT_TEXT.format(
            workers=len(client_pool.clients),
            fqdn=Config.BASE_URL.replace("https://", "").replace("http://", "")
        ),
        reply_markup=keyboard
    )

@Client.on_message(filters.command("ping"))
async def ping_handler(client: Client, message: Message):
    start = time.time()
    msg = await message.reply_text("? Ping...")
    latency = (time.time() - start) * 1000
    uptime = time_formatter(time.time() - BOT_START_TIME)
    await msg.edit_text(f"?? **Pong:** `{latency:.2f}ms`\n?? **Uptime:** `{uptime}`")

@Client.on_callback_query()
async def cb_handler(client: Client, query):
    data = query.data
    first_name = query.from_user.first_name if query.from_user else "User"

    if data == "start_data":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("?? Web Dashboard", url=Config.BASE_URL),
                InlineKeyboardButton("?? Help", callback_data="help_data")
            ],
            [
                InlineKeyboardButton("?? About", callback_data="about_data")
            ]
        ])
        await query.message.edit_text(START_TEXT.format(first_name=first_name), reply_markup=keyboard, disable_web_page_preview=True)
    elif data == "help_data":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("?? Back", callback_data="start_data")]])
        await query.message.edit_text(HELP_TEXT, reply_markup=keyboard)
    elif data == "about_data":
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("?? Back", callback_data="start_data")]])
        await query.message.edit_text(
            ABOUT_TEXT.format(
                workers=len(client_pool.clients),
                fqdn=Config.BASE_URL.replace("https://", "").replace("http://", "")
            ),
            reply_markup=keyboard
        )
