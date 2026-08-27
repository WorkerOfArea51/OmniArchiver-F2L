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
    """Processes uploaded media, forwards to BIN_CHANNEL_ID, indexes to DB, and returns stream links."""
    user_id = message.from_user.id if message.from_user else 0

    if await db.is_user_banned(user_id):
        await message.reply_text("? **Account Suspended:** You are banned from using this bot.")
        return

    if not is_authorized(user_id):
        await message.reply_text("? **Access Denied:** You are not in the authorized users list.")
        return

    progress_msg = await message.reply_text("? *Processing file & indexing stream link...*")

    try:
        # Copy to secure storage bin channel
        forwarded = await message.copy(chat_id=Config.BIN_CHANNEL_ID)
        msg_id = forwarded.id

        file_name, file_size, mime_type, unique_hash = get_file_details(forwarded)

        # Index to Database
        await db.add_file(
            message_id=msg_id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            unique_hash=unique_hash
        )

        stream_url = f"{Config.BASE_URL}/stream/{msg_id}"
        download_url = f"{Config.BASE_URL}/dl/{msg_id}"
        player_url = f"{Config.BASE_URL}/watch/{msg_id}"

        response_text = (
            f"?? **File Name:** `{file_name}`\n"
            f"?? **File Size:** `{humanbytes(file_size)}`\n"
            f"??? **MIME:** `{mime_type}`\n\n"
            f"?? **Direct Stream URL (for StreamHub / ExoPlayer):**\n`{stream_url}`\n\n"
            f"?? **Direct Download URL:**\n`{download_url}`\n\n"
            f"?? **Online Web Player:**\n`{player_url}`\n\n"
            f"? *Multi-Client MTProto streaming enabled.*"
        )

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("?? Watch Online", url=player_url),
                InlineKeyboardButton("?? Fast Download", url=download_url)
            ],
            [
                InlineKeyboardButton("?? Copy Stream Link", copy_text=stream_url)
            ]
        ])

        await progress_msg.edit_text(response_text, reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Error indexing file: {e}", exc_info=True)
        await progress_msg.edit_text(f"? **Error generating stream link:** `{str(e)}`")


@Client.on_message((filters.document | filters.video | filters.audio) & filters.channel)
async def channel_post_listener(client: Client, message: Message):
    """Automatically indexes posts in the BIN_CHANNEL_ID."""
    if message.chat.id != Config.BIN_CHANNEL_ID:
        return

    msg_id = message.id
    file_name, file_size, mime_type, unique_hash = get_file_details(message)

    await db.add_file(
        message_id=msg_id,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        unique_hash=unique_hash
    )

    player_url = f"{Config.BASE_URL}/watch/{msg_id}"
    download_url = f"{Config.BASE_URL}/dl/{msg_id}"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("?? Stream", url=player_url),
            InlineKeyboardButton("?? Download", url=download_url)
        ]
    ])

    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        pass
