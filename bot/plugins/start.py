# -*- coding: utf-8 -*-
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import time_formatter

BOT_START_TIME = time.time()

START_TEXT = """
👋 **Hello {mention}!**

Welcome to **OmniArchiver F2L** — High-Speed Video Streaming Gateway.

⚡ **Features:**
• **Instant Search:** Type any movie or anime name to get links.
• **Batch Links:** Get single M3U playlists or all episode links.
• **Ultra-Fast Streaming:** Full RFC 7233 Range seeking support for StreamHub, ExoPlayer, and VLC.

👉 *Type a movie or anime name below to get started!*
"""

HELP_TEXT = """
📖 **OmniArchiver F2L — Help & Commands**

🔍 **Search & Streaming:**
• Type any title directly (e.g. `Bleach`, `86`, `Ballerina`)
• `/search <title>` — Search movies, anime arcs & web series
• `/index` — Crawl and index configured channel history (Admin)

📊 **System & Info:**
• `/stats` — Real-time RAM, CPU, Workers & Indexed Media
• `/status` — Quick health check
• `/ping` — Measure bot response time
• `/del <id>` — Delete file from channel & database (Admin)
"""

ABOUT_TEXT = """
⚡ **OmniArchiver F2L v2.0**
• **Engine:** Pyrofork MTProto v2.2
• **Server:** aiohttp Async Gateway
• **Database:** MongoDB Atlas / SQLite
• **License:** MIT License
"""

@Client.on_message(filters.command("start") & filters.private & filters.incoming & ~filters.me)
async def start_handler(client: Client, message: Message):
    mention = message.from_user.mention if message.from_user else "User"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help_data"),
            InlineKeyboardButton("ℹ️ About", callback_data="about_data")
        ],
        [
            InlineKeyboardButton("🌐 Web Dashboard", url=Config.BASE_URL)
        ]
    ])
    await message.reply_text(START_TEXT.format(mention=mention), reply_markup=keyboard, disable_web_page_preview=True)

@Client.on_message(filters.command("help") & filters.private & filters.incoming & ~filters.me)
async def help_handler(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Start", callback_data="start_data")]
    ])
    await message.reply_text(HELP_TEXT, reply_markup=keyboard)

@Client.on_message(filters.command("about") & filters.private & filters.incoming & ~filters.me)
async def about_handler(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Start", callback_data="start_data")]
    ])
    await message.reply_text(ABOUT_TEXT, reply_markup=keyboard)

@Client.on_message(filters.command("ping") & filters.incoming & ~filters.me)
async def ping_handler(client: Client, message: Message):
    start = time.time()
    msg = await message.reply_text("🏓 Pinging...")
    end = time.time()
    latency = (end - start) * 1000
    await msg.edit_text(f"🏓 **Pong!** `{latency:.2f}ms`")

@Client.on_callback_query(filters.regex("^(start_data|help_data|about_data)$"))
async def cb_handler(client: Client, query):
    data = query.data
    mention = query.from_user.mention if query.from_user else "User"

    if data == "start_data":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📖 Help", callback_data="help_data"),
                InlineKeyboardButton("ℹ️ About", callback_data="about_data")
            ],
            [
                InlineKeyboardButton("🌐 Web Dashboard", url=Config.BASE_URL)
            ]
        ])
        await query.message.edit_text(START_TEXT.format(mention=mention), reply_markup=keyboard, disable_web_page_preview=True)
    elif data == "help_data":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Start", callback_data="start_data")]
        ])
        await query.message.edit_text(HELP_TEXT, reply_markup=keyboard)
    elif data == "about_data":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Start", callback_data="start_data")]
        ])
        await query.message.edit_text(ABOUT_TEXT, reply_markup=keyboard)

    await query.answer()
