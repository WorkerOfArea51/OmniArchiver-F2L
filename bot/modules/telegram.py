import time
from collections import OrderedDict
from hydrogram import Client
from hydrogram.types import Message
from datetime import datetime
from mimetypes import guess_type
from bot.clients import TelegramBot, get_worker_client, mark_worker_cooldown

try:
    from hydrogram.errors import FloodWait
except ImportError:
    try:
        from pyrogram.errors import FloodWait
    except ImportError:
        FloodWait = Exception

# Fast in-memory LRU cache for channel file messages (eliminates Telegram round-trips on seek/range requests)
_MESSAGE_CACHE: OrderedDict[tuple, tuple[Message, float]] = OrderedDict()
_CACHE_MAX_SIZE = 500
_CACHE_TTL = 3600  # 1 hour

async def get_message(chat_id: int | str, message_id: int, client: Client = None, force_refresh: bool = False) -> Message | None:
    target_client = client or get_worker_client() or TelegramBot
    client_name = getattr(target_client, 'name', 'bot')
    cache_key = (client_name, chat_id, message_id)
    now = time.time()

    if not force_refresh and cache_key in _MESSAGE_CACHE:
        cached_msg, ts = _MESSAGE_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            _MESSAGE_CACHE.move_to_end(cache_key)
            return cached_msg
        else:
            _MESSAGE_CACHE.pop(cache_key, None)

    message = None

    try:
        message = await target_client.get_messages(chat_id=chat_id, message_ids=message_id)
        if message and message.empty:
            message = None
    except Exception as e:
        if isinstance(e, FloodWait):
            mark_worker_cooldown(client_name, getattr(e, 'value', 30))
        # Fallback to main TelegramBot only if no specific client was requested
        if client is None and target_client != TelegramBot:
            try:
                target_client = TelegramBot
                client_name = getattr(target_client, 'name', 'bot')
                cache_key = (client_name, chat_id, message_id)
                message = await TelegramBot.get_messages(chat_id=chat_id, message_ids=message_id)
                if message and message.empty:
                    message = None
            except Exception:
                message = None
        else:
            message = None

    if message:
        if len(_MESSAGE_CACHE) >= _CACHE_MAX_SIZE:
            _MESSAGE_CACHE.popitem(last=False)
        _MESSAGE_CACHE[cache_key] = (message, now)

    return message

def is_media_message(msg: Message) -> bool:
    if not msg:
        return False
    attributes = ('document', 'video', 'audio', 'voice', 'photo', 'video_note')
    return any(getattr(msg, attr, None) is not None for attr in attributes)

from bot.modules.static import format_duration

def get_file_properties(msg: Message) -> tuple[str, int, str, int, str]:
    if not msg:
        return None, 0, 'application/octet-stream', 0, 'N/A'
        
    attributes = (
        'video',
        'document',
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
        return None, 0, 'application/octet-stream', 0, 'N/A'

    file_name = getattr(media, 'file_name', None)
    file_size = getattr(media, 'file_size', 0) or 0
    duration = getattr(media, 'duration', 0) or 0

    # If document, inspect attributes for video/audio duration
    if file_type == 'document' and not duration:
        for attr in getattr(media, 'attributes', []):
            if hasattr(attr, 'duration') and attr.duration:
                duration = attr.duration
                break

    # Extract clean file_name:
    # 1. Prefer message caption if it contains the episode/movie title as written in channel
    if msg.caption:
        first_line = msg.caption.strip().split('\n')[0].strip()
        if 3 < len(first_line) < 200:
            file_name = first_line
        else:
            file_name = getattr(media, 'file_name', None)
    else:
        file_name = getattr(media, 'file_name', None)

    # 2. Fallback to timestamp if neither caption nor media.file_name exists
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

    duration_formatted = format_duration(duration)

    return file_name, file_size, mime_type, duration, duration_formatted
