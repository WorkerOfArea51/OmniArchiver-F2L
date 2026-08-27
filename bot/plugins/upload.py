import logging
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.core.config import Config
from bot.core.database import db
from bot.core.file_properties import get_file_details, humanbytes

logger = logging.getLogger(__name__)

def is_authorized(user_id: int) -> bool:
    if not Config.AUTH_USERS:
        return True
    return user_id in Config.AUTH_USERS

@Client.on_message((filters.document | filters.video | filters.audio | filters.voice | filters.video_note | filters.photo) & filters.private)
async def private_file_uploader(client: Client, message: Message):
    """Processes uploaded media in PM and generates clean Direct Link."""
    user_id = message.from_user.id if message.from_user else 0

    if await db.is_user_banned(user_id):
        await message.reply_text("⛔ **Account Suspended:** You are banned from using this bot.")
        return

    if not is_authorized(user_id):
        await message.reply_text("⛔ **Access Denied:** You are not in the authorized users list.")
        return

    target_channel = Config.CHANNELS[0] if Config.CHANNELS else 0
    if not target_channel:
        await message.reply_text("❌ No storage channel configured in `CHANNELS`.")
        return

    progress_msg = await message.reply_text("⚡ *Processing file & indexing link...*")

    try:
        forwarded = await message.copy(chat_id=target_channel)
        msg_id = forwarded.id

        file_name, file_size, mime_type, _ = get_file_details(forwarded)

        await db.add_file(
            channel_id=target_channel,
            message_id=msg_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            caption=forwarded.caption or ""
        )

        direct_link = f"{Config.BASE_URL}/dl/{target_channel}/{msg_id}"
        player_url = f"{Config.BASE_URL}/watch/{target_channel}/{msg_id}"

        response_text = (
            f"🎬 **{file_name}**\n"
            f"📦 **Size:** `{humanbytes(file_size)}`\n"
            f"🏷️ **MIME:** `{mime_type}`\n\n"
            f"🔗 **Direct Link (For StreamHub App & Download):**\n`{direct_link}`\n\n"
            f"🌐 **Watch Online in Browser:**\n`{player_url}`"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📋 Copy Direct Link", copy_text=direct_link),
                InlineKeyboardButton("▶️ Watch Online", url=player_url)
            ]
        ])

        await progress_msg.edit_text(response_text, reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error handling media: {e}", exc_info=True)
        await progress_msg.edit_text(f"❌ **Error generating link:** `{str(e)}`")
