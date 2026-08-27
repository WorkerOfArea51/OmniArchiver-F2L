import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

def parse_header_post(caption: str):
    """
    Extracts Series Name and Arc Title from header posts like:
    🎬 Bleach : 1.Agent of the Shinigami Arc
    🎬 86 Eighty Six Part 2
    """
    if not caption:
        return "", ""

    first_line = caption.split("\n")[0].replace("🎬", "").strip()

    # If format is "Series : Arc Name" or "Series - Arc Name"
    if ":" in first_line:
        parts = first_line.split(":", 1)
        series_name = parts[0].strip()
        arc_name = parts[1].strip()
        return series_name, arc_name
    elif " - " in first_line:
        parts = first_line.split(" - ", 1)
        series_name = parts[0].strip()
        arc_name = parts[1].strip()
        return series_name, arc_name

    return first_line, ""

def extract_episode_num(text: str, filename: str):
    """
    Extracts continuous 1-to-4 digit episode numbers (e.g. EP - 01 to EP - 1100).
    """
    combined = f"{text} {filename}"
    ep_match = re.search(r'(?:ep|episode|e)[\s_\.-]*(\d{1,4})', combined, re.IGNORECASE)
    if ep_match:
        num = int(ep_match.group(1))
        return f"EP - {num:02d}" if num < 100 else f"EP - {num}"
    return ""

@Client.on_message(filters.command("index") & filters.private)
async def index_channels_cmd(client: Client, message: Message):
    """Indexes past messages and arcs from all configured channels into the database."""
    user_id = message.from_user.id if message.from_user else 0
    if Config.OWNER_ID and user_id != Config.OWNER_ID and user_id not in Config.AUTH_USERS:
        await message.reply_text("⛔ **Admin Only:** You do not have permission to run indexer.")
        return

    if not Config.CHANNELS:
        await message.reply_text("❌ No channels configured in `CHANNELS` env variable.")
        return

    status_msg = await message.reply_text("⏳ **Starting Channel Arc & Episode Indexing...**\nThis may take a moment.")
    total_indexed = 0
    current_series = ""
    current_arc = ""

    for channel_id in Config.CHANNELS:
        try:
            await status_msg.edit_text(f"🔍 Scanning Channel: `{channel_id}`...")
            async for post in client.get_chat_history(channel_id):
                caption = post.caption or post.text or ""

                # Detect Arc / Header Post
                if "🎬" in caption or "Episodes:" in caption or "Quality:" in caption:
                    s_name, a_name = parse_header_post(caption)
                    if s_name:
                        current_series = s_name
                        current_arc = a_name if a_name else s_name

                media = get_media_from_message(post)
                if media:
                    file_name, file_size, mime_type, _ = get_file_details(post)
                    ep_num = extract_episode_num(caption, file_name)

                    await db.add_file(
                        channel_id=channel_id,
                        message_id=post.id,
                        file_name=file_name,
                        file_size=file_size,
                        mime_type=mime_type,
                        caption=caption,
                        series_name=current_series,
                        arc_name=current_arc,
                        episode_num=ep_num
                    )
                    total_indexed += 1

                await asyncio.sleep(0.04)

        except Exception as e:
            logger.error(f"Error indexing channel {channel_id}: {e}")
            await message.reply_text(f"⚠️ Error on channel `{channel_id}`: `{str(e)}`")

    await status_msg.edit_text(
        f"✅ **Indexing Complete!**\n\n"
        f"📁 **Total Episodes & Movies Indexed:** `{total_indexed}`\n"
        f"🌐 All Arcs and continuous episode numbers are now searchable with `/search <query>`!"
    )

@Client.on_message((filters.document | filters.video | filters.audio) & filters.channel)
async def auto_channel_listener(client: Client, message: Message):
    """Real-time auto-indexer for new uploads in your Anime, Movie & Web Series channels."""
    if message.chat.id not in Config.CHANNELS:
        return

    caption = message.caption or ""
    file_name, file_size, mime_type, _ = get_file_details(message)
    ep_num = extract_episode_num(caption, file_name)

    await db.add_file(
        channel_id=message.chat.id,
        message_id=message.id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        caption=caption,
        series_name="",
        arc_name="",
        episode_num=ep_num
    )
    logger.info(f"Auto-indexed file: {file_name} from channel {message.chat.id}")
