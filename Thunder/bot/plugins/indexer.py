# -*- coding: utf-8 -*-
# Thunder/bot/plugins/indexer.py - Multi-Channel Historical Indexer & Auto Listener

import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from Thunder.utils.database import db
from Thunder.utils.file_properties import get_media, get_fname, get_fsize
from Thunder.vars import Var

logger = logging.getLogger(__name__)

EPISODE_REGEX = re.compile(
    r'(?:EP|Episode|E|Ep\.?|EP\.?)[ -_]?([0-9]{1,4})',
    re.IGNORECASE
)

ARC_REGEX = re.compile(
    r'(?:Season|S|Arc|Part|Cour)[ -_]?([0-9]{1,2}|[A-Za-z0-9 -]+)',
    re.IGNORECASE
)

def parse_media_metadata(file_name: str, caption: str = ""):
    text = f"{file_name} {caption}".strip()

    ep_match = EPISODE_REGEX.search(text)
    episode_num = f"EP {int(ep_match.group(1)):02d}" if ep_match else ""

    arc_match = ARC_REGEX.search(text)
    arc_name = arc_match.group(0).strip() if arc_match else ""

    series_name = file_name
    clean = re.sub(r'\[.*?\]|\(.*?\)', '', file_name)
    clean = re.sub(r'(\.mkv|\.mp4|\.avi|\.webm|\.ts|1080p|720p|480p|BluRay|WEB-DL|x264|x265|HEVC|AAC|Hindi|Eng|Dual|Sub).*', '', clean, flags=re.IGNORECASE)
    clean = clean.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    if clean:
        series_name = clean

    return series_name, arc_name, episode_num

@Client.on_message(filters.command("index") & filters.private & filters.incoming & ~filters.me, group=1)
async def index_channels_cmd(client: Client, message: Message):
    message.stop_propagation()
    user_id = message.from_user.id if message.from_user else 0
    if user_id not in Var.AUTH_USERS:
        await message.reply_text("⛔ You are not authorized to trigger indexing.")
        return

    if not Var.CHANNELS:
        await message.reply_text("⚠️ No channels configured in `CHANNELS` or `BIN_CHANNEL`.")
        return

    status_msg = await message.reply_text(f"🚀 Starting multi-channel index across `{len(Var.CHANNELS)}` channel(s)...")

    total_indexed = 0
    for channel_id in Var.CHANNELS:
        try:
            chat = await client.get_chat(channel_id)
            title = getattr(chat, 'title', 'Channel')
            await status_msg.edit_text(f"⏳ Indexing: **{title}** (`{channel_id}`)...\nIndexed so far: `{total_indexed}`")

            channel_count = 0
            async for msg in client.get_chat_history(channel_id):
                media = get_media(msg)
                if not media:
                    continue

                file_name = get_fname(msg)
                file_size = get_fsize(msg)
                mime_type = getattr(media, "mime_type", "video/mp4") or "application/octet-stream"
                caption = msg.caption or ""

                series, arc, ep = parse_media_metadata(file_name, caption)

                await db.insert_file(
                    channel_id=channel_id,
                    message_id=msg.id,
                    file_name=file_name,
                    file_size=file_size,
                    mime_type=mime_type,
                    caption=caption,
                    series_name=series,
                    arc_name=arc,
                    episode_num=ep
                )
                channel_count += 1
                total_indexed += 1

                if channel_count % 100 == 0:
                    await status_msg.edit_text(
                        f"⏳ Indexing: **{title}**\n"
                        f"Channel progress: `{channel_count}` files\n"
                        f"Total indexed: `{total_indexed}`"
                    )

            logger.info(f"Finished indexing channel {channel_id}: {channel_count} files indexed.")

        except Exception as e:
            logger.error(f"Error indexing channel {channel_id}: {e}", exc_info=True)
            await message.reply_text(f"⚠️ Error on channel `{channel_id}`: `{str(e)}`")

    await status_msg.edit_text(
        f"✅ **Indexing Complete!**\n\n"
        f"📚 Total files indexed: `{total_indexed}`\n"
        f"📡 Channels processed: `{len(Var.CHANNELS)}`\n"
        f"🔍 Instant search & M3U generation is active!"
    )

@Client.on_message((filters.document | filters.video | filters.audio) & filters.channel)
async def auto_channel_listener(client: Client, message: Message):
    if not message.chat or message.chat.id not in Var.CHANNELS:
        return

    media = get_media(message)
    if not media:
        return

    file_name = get_fname(message)
    file_size = get_fsize(message)
    mime_type = getattr(media, "mime_type", "video/mp4") or "application/octet-stream"
    caption = message.caption or ""

    series, arc, ep = parse_media_metadata(file_name, caption)

    await db.insert_file(
        channel_id=message.chat.id,
        message_id=message.id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        caption=caption,
        series_name=series,
        arc_name=arc,
        episode_num=ep
    )
    logger.info(f"Auto-indexed new channel post: {file_name} in {message.chat.id}")
