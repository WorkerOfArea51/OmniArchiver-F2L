# -*- coding: utf-8 -*-
# Thunder/bot/plugins/upload.py - Direct Upload & File Forwarding

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from Thunder.utils.database import db
from Thunder.utils.file_properties import get_media, get_fname, get_fsize
from Thunder.utils.human_readable import humanbytes
from Thunder.vars import Var

logger = logging.getLogger(__name__)

@Client.on_message((filters.document | filters.video | filters.audio | filters.voice | filters.video_note | filters.photo) & filters.private & filters.incoming & ~filters.me)
async def private_file_uploader(client: Client, message: Message):
    if not Var.BIN_CHANNEL:
        await message.reply_text("⚠️ Storage channel (`BIN_CHANNEL`) is not configured.")
        return

    forward_msg = await message.reply_text("⚡ Processing and archiving media...")

    try:
        stored_msg = await message.copy(chat_id=Var.BIN_CHANNEL)
        media = get_media(stored_msg)
        if not media:
            await forward_msg.edit_text("❌ Failed to process media.")
            return

        file_name = get_fname(stored_msg)
        file_size = get_fsize(stored_msg)
        mime_type = getattr(media, "mime_type", "video/mp4") or "application/octet-stream"
        caption = message.caption or ""

        await db.insert_file(
            channel_id=Var.BIN_CHANNEL,
            message_id=stored_msg.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            caption=caption
        )

        dl_link = f"{Var.URL}dl/{Var.BIN_CHANNEL}/{stored_msg.id}"
        stream_link = f"{Var.URL}stream/{Var.BIN_CHANNEL}/{stored_msg.id}"
        player_link = f"{Var.URL}watch/{Var.BIN_CHANNEL}/{stored_msg.id}"

        text = (
            f"✅ **File Uploaded & Archived!**\n\n"
            f"📁 **Name:** `{file_name}`\n"
            f"📦 **Size:** `{humanbytes(file_size)}`\n"
            f"🏷️ **MIME:** `{mime_type}`\n\n"
            f"🔗 **Direct Link:**\n`{dl_link}`\n\n"
            f"🌐 **Web Player:**\n`{player_link}`"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("▶️ Watch Online", url=player_link),
                InlineKeyboardButton("⬇️ Fast Download", url=dl_link)
            ]
        ])

        await forward_msg.edit_text(text, reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error in private_file_uploader: {e}", exc_info=True)
        await forward_msg.edit_text(f"⚠️ Error uploading file: `{str(e)}`")
