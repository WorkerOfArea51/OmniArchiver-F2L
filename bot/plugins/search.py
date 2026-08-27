# -*- coding: utf-8 -*-
import logging
import urllib.parse
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import humanbytes

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("search") & filters.private & filters.incoming & ~filters.me, group=1)
async def search_command(client: Client, message: Message):
    message.stop_propagation()
    query = message.text.split(maxsplit=1)
    if len(query) < 2:
        await message.reply_text("🔍 **Usage:** `/search <name>`\nExamples:\n• `/search Bleach`\n• `/search 86`\n• `/search Ballerina`")
        return
    await execute_search(client, message, query[1].strip())

@Client.on_message(filters.text & filters.private & filters.incoming & ~filters.me & ~filters.bot, group=3)
async def direct_text_search(client: Client, message: Message):
    query = message.text.strip()
    # Ignore any command or single character text
    if query.startswith("/") or len(query) < 2:
        return
    await execute_search(client, message, query)

async def execute_search(client: Client, message: Message, query: str):
    search_msg = await message.reply_text(f"🔍 *Searching for:* `{query}`...")

    try:
        # 1. Check for multi-arc series (e.g. Bleach, Naruto, One Piece)
        arcs = await db.get_series_arcs(query)

        if len(arcs) > 1:
            arc_buttons = []
            for arc in arcs:
                arc_buttons.append([
                    InlineKeyboardButton(f"📁 {arc}", callback_data=f"arc:{arc[:40]}")
                ])

            all_files = await db.search_files(query, limit=500)
            playlist_url = f"{Config.BASE_URL}/playlist/{urllib.parse.quote(query.replace(' ', '_'))}.m3u"

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 Open M3U Playlist", url=playlist_url)],
                *arc_buttons
            ])

            text = (
                f"🎬 **{query.title()} — Multi-Arc Series**\n"
                f"📚 **Detected Arcs:** `{len(arcs)}`\n"
                f"📦 **Total Episodes:** `{len(all_files)}`\n\n"
                f"📺 **M3U Playlist URL (Tap to copy):**\n`{playlist_url}`\n\n"
                f"👉 *Select an Arc below to view episodes:* "
            )

            await search_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)
            return

        # 2. Search for files / specific arc
        results = await db.search_files(query, limit=60)
        if not results:
            await search_msg.edit_text(f"❌ No media found matching `{query}`.\nMake sure your channels are indexed with `/index`.")
            return

        is_series = len(results) > 1 and any(r.get("episode_num") for r in results)

        if is_series:
            await render_batch_view(search_msg, results, query)
        else:
            await render_single_view(search_msg, results[0])

    except Exception as e:
        logger.error(f"Search execution error for query '{query}': {e}", exc_info=True)
        await search_msg.edit_text(f"⚠️ **Search Error:** `{str(e)}`")

async def render_batch_view(target_msg, results, title: str):
    """Renders clean batch view with 1-tap copyable links and M3U playlist."""
    batch_text_lines = []
    keyboard_buttons = []

    series_header = results[0].get("arc_name") or results[0].get("series_name") or title
    playlist_url = f"{Config.BASE_URL}/playlist/{urllib.parse.quote(series_header.replace(' ', '_'))}.m3u"

    batch_text_lines.append(f"🎬 **{series_header}**")
    batch_text_lines.append(f"📦 **Total Episodes:** `{len(results)}`")
    batch_text_lines.append(f"📺 **M3U Playlist:** `{playlist_url}`\n")

    for item in results:
        ch = item["channel_id"]
        mid = item["message_id"]
        ep = item.get("episode_num") or f"ID {mid}"
        size = humanbytes(item["file_size"])
        direct_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
        watch_url = f"{Config.BASE_URL}/watch/{ch}/{mid}"

        batch_text_lines.append(f"• **{ep}** ({size})\n  `{direct_url}`")

        if len(keyboard_buttons) < 10:
            keyboard_buttons.append([
                InlineKeyboardButton(f"▶️ {ep}", url=watch_url),
                InlineKeyboardButton("⬇️ Download", url=direct_url)
            ])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 Open M3U Playlist", url=playlist_url)],
        *keyboard_buttons
    ])

    final_msg = "\n".join(batch_text_lines[:15])
    if len(batch_text_lines) > 15:
        final_msg += f"\n\n*(+ {len(batch_text_lines) - 15} more episodes - tap links above to copy)*"

    await target_msg.edit_text(final_msg, reply_markup=keyboard, disable_web_page_preview=True)

async def render_single_view(target_msg, item):
    """Renders single movie/video card with Direct Link for StreamHub & Web Player."""
    ch = item["channel_id"]
    mid = item["message_id"]
    file_name = item["file_name"]
    size = humanbytes(item["file_size"])
    direct_link = f"{Config.BASE_URL}/dl/{ch}/{mid}"
    player_url = f"{Config.BASE_URL}/watch/{ch}/{mid}"

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

    await target_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)

@Client.on_callback_query(filters.regex(r"^arc:(.+)"))
async def arc_callback_handler(client: Client, query: CallbackQuery):
    arc_name = query.data.split(":", 1)[1]
    arc_files = await db.get_arc_files(arc_name)

    if not arc_files:
        await query.answer("No episodes found for this arc.", show_alert=True)
        return

    await render_batch_view(query.message, arc_files, arc_name)
    await query.answer()
