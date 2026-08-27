from hydrogram import Client
from hydrogram.types import Message
from datetime import datetime
from mimetypes import guess_type
from bot.clients import TelegramBot, get_worker_client

async def get_message(chat_id: int | str, message_id: int, client: Client = None) -> Message | None:
    message = None
    target_client = client or get_worker_client() or TelegramBot
    
    try:
        message = await target_client.get_messages(chat_id=chat_id, message_ids=message_id)
        if message and message.empty:
            message = None
    except Exception:
        # Fallback to main TelegramBot if worker client fails
        if target_client != TelegramBot:
            try:
                message = await TelegramBot.get_messages(chat_id=chat_id, message_ids=message_id)
                if message and message.empty:
                    message = None
            except Exception:
                message = None

    return message

def is_media_message(msg: Message) -> bool:
    if not msg:
        return False
    attributes = ('document', 'video', 'audio', 'voice', 'photo', 'video_note')
    return any(getattr(msg, attr, None) is not None for attr in attributes)

def get_file_properties(msg: Message) -> tuple[str, int, str]:
    if not msg:
        return None, 0, 'application/octet-stream'
        
    attributes = (
        'document',
        'video',
        'audio',
        'voice',
        'photo',
        'video_note'
    )
    media = None
    file_type = None
    for attribute in attributes:
        media = getattr(msg, attribute, None)
        if media:
            file_type = attribute
            break

    if not media:
        return None, 0, 'application/octet-stream'

    file_name = getattr(media, 'file_name', None)
    file_size = getattr(media, 'file_size', 0)

    if not file_name:
        file_format = {
            'video': 'mp4',
            'audio': 'mp3',
            'voice': 'ogg',
            'photo': 'jpg',
            'video_note': 'mp4'
        }.get(file_type, 'bin')
        date = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f'{file_type}-{date}.{file_format}'
    
    mime_type = getattr(media, 'mime_type', None)
    if not mime_type:
        mime_type = guess_type(file_name)[0] or 'application/octet-stream'

    return file_name, file_size, mime_type
