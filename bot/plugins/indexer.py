# -*- coding: utf-8 -*-
import re
import time
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait, MessageNotModified
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import get_file_details, get_media_from_message

logger = logging.getLogger(__name__)

def parse_header_post(caption: str):
    """Extracts Series Name and Arc Title from header posts."""
    if not caption:
        return "", ""

    first_line = caption.split("\n")[0].replace("🎬", "").strip()

    if ":" in first_line:
        parts = first_line.split(":", 1)
        return parts[0].strip(), parts[1].strip()
    elif " - " in first_line:
        parts = first_line.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()

    return first_line, ""

def extract_episode_num(text: str, filename: str):
    """Extracts continuous 1-to-4 digit episode numbers (e.g. EP - 01 to EP - 1100)."""
    combined = f"{text} {filename}"
    ep_match = re.search(r'(?:ep|episode|e)[\s_\.-]*(\d{1,4})', combined, re.IGNORECASE)
    if ep_match:
        num = int(ep_match.group(1))
        return f"EP - {num:02d}" if num < 100 else f"EP - {num}"
    return ""

@Client.on_message(filters.command("index") & filters.private & filters.incoming & ~filters.me)
async def index_channels_cmd(client: Client, message: Message):
    """High-speed resilient channel history indexer with time-throttled UI updates."""
    user_id = message.from_user.id if message.from_user else 0
    if Config.OWNER_ID and user_id != Config.OWNER_ID and user_id not in Config.AUTH_USERS:
        await message.reply_text("⛔ **Admin Only:** You do not have permission to run indexer.")
        return

    if not Config.CHANNELS:
        await message.reply_text("❌ No channels configured in `CHANNELS` env variable.")
        return

    status_msg = await message.reply_text("⏳ **Starting Channel Arc & Episode Indexing...**")
    total_indexed = 0
    last_ui_update = time.time()
    BATCH_SIZE = 100

    for ch_idx, channel_id in enumerate(Config.CHANNELS, start=1):
        try:
            # Probe channel max message ID
            max_id = 5000
            try:
                dummy = await client.send_message(channel_id, "🔍 *Indexing channel...*")
                max_id = dummy.id
                await dummy.delete()
            except Exception as e:
                logger.info(f"Using default max_id probe for {channel_id}: {e}")

            current_series = ""
            current_arc = ""
            channel_indexed = 0

            # Scan in chunks of 100
            for start_id in range(1, max_id + 1, BATCH_SIZE):
                ids_to_fetch = list(range(start_id, min(start_id + BATCH_SIZE, max_id + 1)))
                try:
                    messages = await client.get_messages(channel_id, message_ids=ids_to_fetch)
                except FloodWait as fw:
                    logger.warning(f"FloodWait on get_messages: sleeping {fw.value}s")
                    await asyncio.sleep(fw.value)
                    messages = await client.get_messages(channel_id, message_ids=ids_to_fetch)
                except Exception as e:
                    logger.warning(f"Error fetching batch {start_id} for {channel_id}: {e}")
                    continue

                if not isinstance(messages, list):
                    messages = [messages]

                for post in messages:
                    if not post or post.empty:
                        continue

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
                        channel_indexed += 1

                # Time-throttled UI update (every 2.5s) to avoid Telegram edit FloodWait
                now = time.time()
                if now - last_ui_update > 2.5:
                    try:
                        await status_msg.edit_text(
                            f"🔍 **Scanning Channel ({ch_idx}/{len(Config.CHANNELS)}):** `{channel_id}`\n"
                            f"📊 **Progress:** `{min(start_id + BATCH_SIZE, max_id)} / {max_id}` IDs\n"
                            f"📁 **Total Indexed Media:** `{total_indexed}`"
                        )
                        last_ui_update = now
                    except (MessageNotModified, FloodWait):
                        pass

                await asyncio.sleep(0.02)

        except Exception as e:
            logger.error(f"Error indexing channel {channel_id}: {e}", exc_info=True)
            await message.reply_text(f"⚠️ Channel `{channel_id}`: `{str(e)}`")

    # Final summary
    await status_msg.edit_text(
        f"✅ **Indexing Complete!**\n\n"
        f"📁 **Total Episodes & Movies Indexed:** `{total_indexed}`\n"
        f"🗄️ **Database:** Saved to MongoDB Atlas\n"
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
