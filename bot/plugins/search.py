import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import humanbytes

logger = logging.getLogger(__name__)

@Client.on_message(filters.command("search") & filters.private)
async def search_command(client: Client, message: Message):
    query = message.text.split(maxsplit=1)
    if len(query) < 2:
        await message.reply_text("🔍 **Usage:** `/search <movie or series name>`\nExample: `/search 86` or `/search Ballerina`")
        return
    await execute_search(client, message, query[1].strip())

@Client.on_message(filters.text & filters.private & ~filters.command(["start", "help", "about", "ping", "stats", "status", "index", "ban", "unban", "del", "restart", "search"]))
async def direct_text_search(client: Client, message: Message):
    query = message.text.strip()
    if len(query) >= 2:
        await execute_search(client, message, query)

async def execute_search(client: Client, message: Message, query: str):
    search_msg = await message.reply_text(f"🔍 *Searching for:* `{query}`...")
    results = await db.search_files(query, limit=35)

    if not results:
        await search_msg.edit_text(f"❌ No media found matching `{query}`.\nMake sure your channels are indexed with `/index`.")
        return

    # Check if multiple episodes belonging to a series
    is_series = len(results) > 1 and any(r.get("episode_num") for r in results)

    if is_series:
        # BATCH / SERIES VIEW
        series_title = results[0].get("series_name") or query
        batch_text_lines = []
        batch_copy_payload = []
        keyboard_buttons = []

        batch_text_lines.append(f"🎬 **{series_title}**")
        batch_text_lines.append(f"📦 **Available Episodes:** `{len(results)}`\n")

        for idx, item in enumerate(reversed(results), start=1):
            ch = item["channel_id"]
            mid = item["message_id"]
            ep = item.get("episode_num") or f"EP {idx:02d}"
            size = humanbytes(item["file_size"])
            dl_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
            stream_url = f"{Config.BASE_URL}/stream/{ch}/{mid}"

            batch_text_lines.append(f"• **{ep}** ({size})\n  `{dl_url}`")
            batch_copy_payload.append(f"{ep}: {dl_url}")

            keyboard_buttons.append([
                InlineKeyboardButton(f"▶️ {ep}", url=stream_url),
                InlineKeyboardButton("⬇️ Download", url=dl_url)
            ])

        all_batch_links = "\n".join(batch_copy_payload)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Copy All Batch Links", copy_text=all_batch_links)],
            *keyboard_buttons[:8]
        ])

        final_msg = "\n".join(batch_text_lines[:15])
        if len(batch_text_lines) > 15:
            final_msg += f"\n\n*(+ {len(batch_text_lines) - 15} more episodes - use Copy All button below)*"

        await search_msg.edit_text(final_msg, reply_markup=keyboard, disable_web_page_preview=True)

    else:
        # SINGLE MOVIE / FILE VIEW
        item = results[0]
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

        await search_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)

# Telegram Inline Search Mode (@OmniArchiverBot query)
@Client.on_inline_query()
async def inline_search_handler(client: Client, query: InlineQuery):
    q = query.query.strip()
    if not q:
        await query.answer([], switch_pm_text="Type movie or anime name to search...", switch_pm_parameter="help")
        return

    results = await db.search_files(q, limit=15)
    articles = []

    for item in results:
        ch = item["channel_id"]
        mid = item["message_id"]
        file_name = item["file_name"]
        size = humanbytes(item["file_size"])
        stream_url = f"{Config.BASE_URL}/stream/{ch}/{mid}"
        download_url = f"{Config.BASE_URL}/dl/{ch}/{mid}"
        player_url = f"{Config.BASE_URL}/watch/{ch}/{mid}"

        content_text = (
            f"🎬 **{file_name}**\n"
            f"📦 **Size:** `{size}`\n\n"
            f"⬇️ **Download Link:** `{download_url}`\n"
            f"🔗 **Stream Link:** `{stream_url}`"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Stream", url=player_url),
                InlineKeyboardButton("⬇️ Download", url=download_url)
            ]
        ])

        articles.append(
            InlineQueryResultArticle(
                title=file_name,
                description=f"Size: {size} | Channel: {ch}",
                input_message_content=InputTextMessageContent(content_text, disable_web_page_preview=True),
                reply_markup=keyboard
            )
        )

    await query.answer(articles, cache_time=5)
