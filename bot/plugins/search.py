import logging
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent
)
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import humanbytes

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("search") & filters.private)
async def search_command(client: Client, message: Message):
    query = message.text.split(maxsplit=1)
    if len(query) < 2:
        await message.reply_text("🔍 **Usage:** `/search <name>`\nExamples:\n• `/search Bleach`\n• `/search 86`\n• `/search Ballerina`")
        return
    await execute_search(client, message, query[1].strip())

@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "about", "ping", "stats", "status", "index", "ban", "unban", "del", "restart", "search"]))
async def direct_text_search(client: Client, message: Message):
    query = message.text.strip()
    if len(query) >= 2:
        await execute_search(client, message, query)

async def execute_search(client: Client, message: Message, query: str):
    search_msg = await message.reply_text(f"🔍 *Searching for:* `{query}`...")

    # 1. Check if query matches a series with multiple Arcs (e.g. Bleach, Naruto, One Piece)
    arcs = await db.get_series_arcs(query)

    if len(arcs) > 1:
        # MULTI-ARC SAGA VIEW
        arc_buttons = []
        for arc in arcs:
            arc_buttons.append([
                InlineKeyboardButton(f"📁 {arc}", callback_data=f"arc:{arc[:40]}")
            ])

        # Also get all episodes for the full copy button
        all_files = await db.search_files(query, limit=500)
        full_batch_payload = []
        for item in all_files:
            ch = item["channel_id"]
            mid = item["message_id"]
            ep = item.get("episode_num") or f"ID {mid}"
            dl_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
            full_batch_payload.append(f"{ep}: {dl_url}")

        keyboard = InlineKeyboardMarkup([
            *arc_buttons,
            [InlineKeyboardButton(f"📋 Copy Entire Series ({len(all_files)} Files)", copy_text="\n".join(full_batch_payload))]
        ])

        text = (
            f"🎬 **{query.title()} — Multi-Arc Series**\n"
            f"📚 **Detected Arcs/Sagas:** `{len(arcs)}`\n"
            f"📦 **Total Episodes:** `{len(all_files)}`\n\n"
            f"👉 *Select an Arc below to view and copy episode links:* "
        )

        await search_msg.edit_text(text, reply_markup=keyboard)
        return

    # 2. Regular search across files and individual arcs
    results = await db.search_files(query, limit=60)
    if not results:
        await search_msg.edit_text(f"❌ No media found matching `{query}`.\nMake sure your channels are indexed with `/index`.")
        return

    # Check if multiple episodes belonging to one arc/series
    is_series = len(results) > 1 and any(r.get("episode_num") for r in results)

    if is_series:
        await render_batch_view(search_msg, results, query)
    else:
        # Single Movie / File View
        await render_single_view(search_msg, results[0])

async def render_batch_view(target_msg, results, title: str):
    """Renders clean batch view with individual episode buttons and Copy All button."""
    batch_text_lines = []
    batch_copy_payload = []
    keyboard_buttons = []

    series_header = results[0].get("arc_name") or results[0].get("series_name") or title
    batch_text_lines.append(f"🎬 **{series_header}**")
    batch_text_lines.append(f"📦 **Episodes in this Arc:** `{len(results)}`\n")

    for item in results:
        ch = item["channel_id"]
        mid = item["message_id"]
        ep = item.get("episode_num") or f"ID {mid}"
        size = humanbytes(item["file_size"])
        dl_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
        stream_url = f"{Config.BASE_URL}/stream/{ch}/{mid}"

        batch_text_lines.append(f"• **{ep}** ({size})\n  `{dl_url}`")
        batch_copy_payload.append(f"{ep}: {dl_url}")

        if len(keyboard_buttons) < 10:
            keyboard_buttons.append([
                InlineKeyboardButton(f"▶️ {ep}", url=stream_url),
                InlineKeyboardButton("⬇️ Download", url=dl_url)
            ])

    all_batch_links = "\n".join(batch_copy_payload)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Copy Arc Batch Links", copy_text=all_batch_links)],
        *keyboard_buttons
    ])

    final_msg = "\n".join(batch_text_lines[:15])
    if len(batch_text_lines) > 15:
        final_msg += f"\n\n*(+ {len(batch_text_lines) - 15} more episodes - use Copy button below)*"

    await target_msg.edit_text(final_msg, reply_markup=keyboard, disable_web_page_preview=True)

async def render_single_view(target_msg, item):
    """Renders single movie/file view."""
    ch = item["channel_id"]
    mid = item["message_id"]
    file_name = item["file_name"]
    size = humanbytes(item["file_size"])
    stream_url = f"{Config.BASE_URL}/stream/{ch}/{mid}"
    download_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
    player_url = f"{Config.BASE_URL}/watch/{ch}/{mid}"

    text = (
        f"🎬 **{file_name}**\n"
        f"📦 **Size:** `{size}`\n"
        f"🏷️ **MIME:** `{item['mime_type']}`\n\n"
        f"⬇️ **Direct Download Link:**\n`{download_url}`\n\n"
        f"🔗 **Direct Stream Link (for StreamHub app):**\n`{stream_url}`"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ Watch Online", url=player_url),
            InlineKeyboardButton("⬇️ Fast Download", url=download_url)
        ],
        [
            InlineKeyboardButton("📋 Copy Download Link", copy_text=download_url),
            InlineKeyboardButton("📋 Copy Stream Link", copy_text=stream_url)
        ]
    ])

    await target_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)

# Callback handler for selecting an Arc from the menu
@Client.on_callback_query(filters.regex(r"^arc:(.+)"))
async def arc_callback_handler(client: Client, query: CallbackQuery):
    arc_name = query.data.split(":", 1)[1]
    arc_files = await db.get_arc_files(arc_name)

    if not arc_files:
        await query.answer("No episodes found for this arc.", show_alert=True)
        return

    await render_batch_view(query.message, arc_files, arc_name)
    await query.answer()
