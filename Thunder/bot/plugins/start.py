# -*- coding: utf-8 -*-
# Thunder/bot/plugins/start.py

import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from Thunder import StartTime
from Thunder.utils.time_format import get_readable_time
from Thunder.vars import Var

START_TEXT = (
    "👋 **Hello {name}!**\n\n"
    "Welcome to **OmniArchiver F2L** — High-Speed Video Streaming Gateway.\n\n"
    "⚡ **Features:**\n"
    "• **Instant Search:** Type any movie or anime name to get links.\n"
    "• **Batch Links:** Get single M3U playlists or all episode links.\n"
    "• **Ultra-Fast Streaming:** Full RFC 7233 Range seeking support for StreamHub, ExoPlayer, and VLC.\n\n"
    "*Type a movie or anime name below to get started!*"
)

@Client.on_message(filters.command("start") & filters.private & filters.incoming & ~filters.me, group=1)
async def start_handler(client: Client, message: Message):
    message.stop_propagation()
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help_data"),
            InlineKeyboardButton("ℹ️ About", callback_data="about_data")
        ],
        [
            InlineKeyboardButton("🌐 Web Dashboard", url=Var.URL)
        ]
    ])
    await message.reply_text(
        START_TEXT.format(name=message.from_user.first_name if message.from_user else "User"),
        reply_markup=buttons,
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("help") & filters.private & filters.incoming & ~filters.me, group=1)
async def help_handler(client: Client, message: Message):
    message.stop_propagation()
    text = (
        "📖 **OmniArchiver Help & Usage:**\n\n"
        "1. **Direct Search:** Just type any name (e.g. `Bleach`, `86`, `John Wick`).\n"
        "2. **Arc Navigation:** Click on any arc button to view episodes.\n"
        "3. **M3U Playlist:** Tap the M3U playlist button to import all episodes into StreamHub / VLC.\n"
        "4. **Admin Indexing:** Send `/index` to crawl and index configured channels."
    )
    await message.reply_text(text, disable_web_page_preview=True)

@Client.on_message(filters.command("ping") & filters.incoming & ~filters.me, group=1)
async def ping_handler(client: Client, message: Message):
    message.stop_propagation()
    start = time.time()
    msg = await message.reply_text("🏓 Pong!")
    end = time.time()
    await msg.edit_text(f"🏓 **Pong!** Latency: `{int((end - start) * 1000)}ms`\n⏳ Uptime: `{get_readable_time(time.time() - StartTime)}`")

@Client.on_callback_query(filters.regex(r"^(help_data|about_data|home_data)$"))
async def cb_handler(client: Client, query: CallbackQuery):
    if query.data == "help_data":
        text = (
            "📖 **Help & Usage:**\n\n"
            "• Type any anime or movie name directly in this chat.\n"
            "• Use the interactive buttons to copy links or open video stream.\n"
            "• Import `.m3u` links into IPTV / StreamHub app."
        )
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home_data")]])
        await query.message.edit_text(text, reply_markup=buttons)
    elif query.data == "about_data":
        text = (
            "ℹ️ **About OmniArchiver F2L:**\n\n"
            "• **Engine:** FileToLink (Thunder) MTProto Streamer\n"
            "• **Seeking:** RFC 7233 Byte-Range\n"
            "• **Status:** Operational"
        )
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="home_data")]])
        await query.message.edit_text(text, reply_markup=buttons)
    elif query.data == "home_data":
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📖 Help", callback_data="help_data"),
                InlineKeyboardButton("ℹ️ About", callback_data="about_data")
            ],
            [
                InlineKeyboardButton("🌐 Web Dashboard", url=Var.URL)
            ]
        ])
        await query.message.edit_text(
            START_TEXT.format(name=query.from_user.first_name if query.from_user else "User"),
            reply_markup=buttons,
            disable_web_page_preview=True
        )
    await query.answer()
