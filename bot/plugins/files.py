from hydrogram import filters
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.clients import TelegramBot
from bot.config import Telegram, Server
from bot.database.files import save_file
from bot.modules.decorators import verify_user
from bot.modules.telegram import get_file_properties
from bot.modules.static import MediaLinksText, FileLinksText, get_human_size

@TelegramBot.on_message(
    filters.private
    & (
        filters.document
        | filters.video
        | filters.video_note
        | filters.audio
        | filters.voice
        | filters.photo
    )
)
@verify_user
async def handle_user_file(_, msg: Message):
    sender_id = msg.from_user.id
    status_msg = await msg.reply("⏳ *Processing file and generating links...*", quote=True)
    
    try:
        # Copy to default storage / bin channel
        forwarded = await msg.copy(chat_id=Telegram.CHANNEL_ID)
        file_name, file_size, mime_type = get_file_properties(forwarded)
        
        # Save into MongoDB 'direct_files' collection
        doc = await save_file(
            channel_id=Telegram.CHANNEL_ID,
            message_id=forwarded.id,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            user_id=sender_id,
            category='direct_files'
        )
        
        code = doc['code']
        human_size = get_human_size(file_size)
        dl_link = f"{Server.BASE_URL}/dl/{code}"
        stream_link = f"{Server.BASE_URL}/stream/{code}"
        
        buttons = [
            [
                InlineKeyboardButton('📥 Download', url=dl_link),
                InlineKeyboardButton('▶️ Stream', url=stream_link)
            ],
            [
                InlineKeyboardButton('🗑️ Revoke', callback_data=f"rm_{code}")
            ]
        ]
        
        if (msg.document and 'video' in (msg.document.mime_type or '')) or msg.video:
            caption = MediaLinksText % {
                'file_name': file_name,
                'file_size': human_size,
                'category': 'Direct Upload',
                'dl_link': dl_link,
                'stream_link': stream_link
            }
        else:
            caption = FileLinksText % {
                'file_name': file_name,
                'file_size': human_size,
                'category': 'Direct Upload',
                'dl_link': dl_link
            }

        await status_msg.edit_text(
            text=caption,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )

    except Exception as e:
        await status_msg.edit_text(f"❌ Failed to process file: `{e}`")
