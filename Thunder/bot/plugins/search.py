# -*- coding: utf-8 -*-
# Thunder/bot/plugins/search.py - Smart Search & Interactive Arc Cards

import logging
from urllib.parse import quote
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from Thunder.utils.database import db
from Thunder.utils.human_readable import humanbytes
from Thunder.vars import Var

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("search") & filters.private & filters.incoming & ~filters.me, group=1)
async def search_command(client: Client, message: Message):
    message.stop_propagation()
    query = " ".join(message.command[1:]).strip()
    if not query:
        await message.reply_text("❓ Please provide a search query.\nExample: `/search Bleach` or `/search 86`")
        return
    await execute_search(client, message, query)

@Client.on_message(filters.text & filters.private & filters.incoming & ~filters.me & ~filters.bot, group=3)
async def direct_text_search(client: Client, message: Message):
    query = message.text.strip()
    if query.startswith("/"):
        return
    await execute_search(client, message, query)

async def execute_search(client: Client, message: Message, query: str):
    search_msg = await message.reply_text(f"🔍 *Searching for:* `{query}`...")

    try:
        arcs = await db.get_series_arcs(query)

        if len(arcs) > 1:
            buttons = []
            row = []
            for arc in arcs:
                clean_arc = arc.strip()
                row.append(InlineKeyboardButton(f"📁 {clean_arc}", callback_data=f"arc:{clean_arc[:40]}"))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)

            playlist_url = f"{Var.URL}playlist/{quote(query.replace(' ', '_'))}.m3u"
            buttons.insert(0, [InlineKeyboardButton("📺 Open M3U Playlist", url=playlist_url)])

            total_matches = await db.search_files(query, limit=500)
            text = (
                f"🎬 **{query.title()} — Multi-Arc Series**\n"
                f"📚 **Detected Arcs:** `{len(arcs)}`\n"
                f"📦 **Total Episodes:** `{len(total_matches)}`\n\n"
                f"📺 **M3U Playlist URL (Tap to copy):**\n`{playlist_url}`\n\n"
                f"*Select an Arc below to view episodes:*"
            )
            try:
                await search_msg.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)
            except MessageNotModified:
                pass
            return

        results = await db.search_files(query, limit=60)
        if not results:
            try:
                await search_msg.edit_text(f"❌ No media found matching `{query}`.\nMake sure your channels are indexed with `/index`.")
            except MessageNotModified:
                pass
            return

        if len(results) == 1:
            await render_single_view(search_msg, results[0])
        else:
            await render_batch_view(search_msg, results, query)

    except MessageNotModified:
        pass
    except Exception as e:
        logger.error(f"Search execution error for query \'{query}\': {e}", exc_info=True)
        try:
            await search_msg.edit_text(f"⚠️ **Search Error:** `{str(e)}`")
        except Exception:
            pass

async def render_batch_view(target_msg, results, title_name):
    total = len(results)
    playlist_url = f"{Var.URL}playlist/{quote(title_name.replace(' ', '_'))}.m3u"

    batch_text_lines = [
        f"🎬 **{title_name.title()}**",
        f"📦 **Total Episodes:** `{total}`",
        f"📺 **M3U Playlist:**\n`{playlist_url}`\n"
    ]

    keyboard_buttons = []
    for idx, item in enumerate(results[:25], start=1):
        mid = item["message_id"]
        ch = item["channel_id"]
        size = humanbytes(item["file_size"])
        ep = item.get("episode_num") or f"ID {mid}"
        dl_link = f"{Var.URL}dl/{ch}/{mid}"
        stream_link = f"{Var.URL}stream/{ch}/{mid}"

        batch_text_lines.append(f"• **{ep}** ({size})\n`{dl_link}`")

        keyboard_buttons.append([
            InlineKeyboardButton(f"▶️ {ep}", url=stream_link),
            InlineKeyboardButton("⬇️ Download", url=dl_link)
        ])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Open M3U Playlist", url=playlist_url)],
        *keyboard_buttons
    ])

    final_msg = "\n".join(batch_text_lines[:15])
    if len(batch_text_lines) > 15:
        final_msg += f"\n\n*(+ {len(batch_text_lines) - 15} more episodes - tap links above to copy)*"

    try:
        await target_msg.edit_text(final_msg, reply_markup=keyboard, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        logger.warning(f"render_batch_view note: {e}")

async def render_single_view(target_msg, item):
    ch = item["channel_id"]
    mid = item["message_id"]
    file_name = item["file_name"]
    size = humanbytes(item["file_size"])
    direct_link = f"{Var.URL}dl/{ch}/{mid}"
    player_url = f"{Var.URL}watch/{ch}/{mid}"

    text = (
        f"🎬 **{file_name}**\n"
        f"📦 **Size:** `{size}`\n"
        f"🏷️ **MIME:** `{item['mime_type']}`\n\n"
        f"🔗 **Direct Link (Tap to copy for StreamHub):**\n`{direct_link}`\n\n"
        f"🌐 **Watch Online in Browser:**\n`{player_url}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Watch Online", url=player_url),
            InlineKeyboardButton("⬇️ Fast Download", url=direct_link)
        ]
    ])

    try:
        await target_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
    except MessageNotModified:
        pass
    except Exception as e:
        logger.warning(f"render_single_view note: {e}")

@Client.on_callback_query(filters.regex(r"^arc:(.+)"))
async def arc_callback_handler(client: Client, query: CallbackQuery):
    arc_name = query.data.split(":", 1)[1]
    arc_files = await db.get_arc_files(arc_name)

    if not arc_files:
        await query.answer("No episodes found for this arc.", show_alert=True)
        return

    await render_batch_view(query.message, arc_files, arc_name)
    await query.answer()
