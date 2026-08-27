import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

def extract_episode_and_series(text: str, filename: str):
    """Extracts series name and episode number using regex patterns."""
    combined = f"{text} {filename}"
    
    # Match patterns like EP - 11, Episode 05, E08, S01E02
    ep_match = re.search(r'(?:ep|episode|e)[\s_\.-]*(\d{1,3})', combined, re.IGNORECASE)
    ep_num = f"EP - {ep_match.group(1).zfill(2)}" if ep_match else ""

    clean_name = filename
    if ep_match:
        parts = re.split(r'(?:ep|episode|e)[\s_\.-]*\d{1,3}', filename, flags=re.IGNORECASE)
        if parts:
            clean_name = parts[0].replace(".", " ").replace("_", " ").strip(" -_")

    return clean_name, ep_num

@Client.on_message(filters.command("index") & filters.private)
async def index_channels_cmd(client: Client, message: Message):
    """Indexes past messages from all configured channels into the database."""
    user_id = message.from_user.id if message.from_user else 0
    if Config.OWNER_ID and user_id != Config.OWNER_ID and user_id not in Config.AUTH_USERS:
        await message.reply_text("⛔ **Admin Only:** You do not have permission to run indexer.")
        return

    if not Config.CHANNELS:
        await message.reply_text("❌ No channels configured in `CHANNELS` env variable.")
        return

    status_msg = await message.reply_text("⏳ **Starting Channel History Indexing...**\nThis may take a moment.")
    total_indexed = 0
    current_series = ""

    for channel_id in Config.CHANNELS:
        try:
            await status_msg.edit_text(f"🔍 Scanning Channel: `{channel_id}`...")
            async for post in client.get_chat_history(channel_id):
                caption = post.caption or post.text or ""
                
                # Check for header post (e.g., 🎬 86 Eighty Six, Ballerina)
                if "🎬" in caption or "Episodes:" in caption or "Quality:" in caption:
                    lines = [l.strip() for l in caption.split("\n") if l.strip()]
                    if lines:
                        current_series = lines[0].replace("🎬", "").strip()

                media = get_media_from_message(post)
                if media:
                    file_name, file_size, mime_type, _ = get_file_details(post)
                    series_name, ep_num = extract_episode_and_series(caption, file_name)
                    if not series_name and current_series:
                        series_name = current_series

                    await db.add_file(
                        channel_id=channel_id,
                        message_id=post.id,
                        file_name=file_name,
                        file_size=file_size,
                        mime_type=mime_type,
                        caption=caption,
                        series_name=series_name,
                        episode_num=ep_num
                    )
                    total_indexed += 1

                await asyncio.sleep(0.05)

        except Exception as e:
            logger.error(f"Error indexing channel {channel_id}: {e}")
            await message.reply_text(f"⚠️ Error on channel `{channel_id}`: `{str(e)}`")

    await status_msg.edit_text(
        f"✅ **Indexing Complete!**\n\n"
        f"📁 **Total Media Files Indexed:** `{total_indexed}`\n"
        f"🌐 You can now search for movies & series with `/search <query>` or in PM directly!"
    )

@Client.on_message((filters.document | filters.video | filters.audio) & filters.channel)
async def auto_channel_listener(client: Client, message: Message):
    """Real-time auto-indexer for new uploads in your Anime, Movie & Web Series channels."""
    if message.chat.id not in Config.CHANNELS:
        return

    caption = message.caption or ""
    file_name, file_size, mime_type, _ = get_file_details(message)
    series_name, ep_num = extract_episode_and_series(caption, file_name)

    await db.add_file(
        channel_id=message.chat.id,
        message_id=message.id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        caption=caption,
        series_name=series_name,
        episode_num=ep_num
    )
    logger.info(f"Auto-indexed new file: {file_name} from channel {message.chat.id}")
