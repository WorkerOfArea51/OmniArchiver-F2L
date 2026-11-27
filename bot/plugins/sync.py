from datetime import datetime
from logging import getLogger
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot
from bot.database import db
from bot.modules.cache import evict_file_chunks
from bot.modules.telegram import get_file_properties, is_media_message, invalidate_message_cache

logger = getLogger('auto_sync')

@TelegramBot.on_edited_message(filters.channel)
async def auto_sync_channel_edit(_, msg: Message):
    """
    Automatically detects when an administrator edits a channel message to swap or update media.
    Updates MongoDB metadata in-place and clears SSD/RAM caches while keeping the EXACT same link code!
    """
    if not is_media_message(msg):
        return

    channel_id = msg.chat.id
    message_id = msg.id

    try:
        file_name, file_size, mime_type, duration, duration_formatted = get_file_properties(msg)
    except Exception as e:
        logger.debug(f"[AutoSync] Could not extract media properties for msg {message_id}: {e}")
        return

    # Always invalidate in-memory message cache so workers immediately fetch fresh file_reference token
    invalidate_message_cache(channel_id, message_id)

    # 1. Check collections: movies, direct_files (single items)
    for coll_name in ('movies', 'direct_files'):
        coll = db.get_collection(coll_name)
        existing = await coll.find_one({'channel_id': channel_id, 'message_id': message_id})
        if existing:
            evict_file_chunks(existing['_id'])
            if (
                file_size != existing.get('file_size')
                or file_name != existing.get('file_name')
                or duration != existing.get('duration')
            ):
                update_data = {
                    'file_name': file_name,
                    'file_size': file_size,
                    'mime_type': mime_type,
                    'duration': duration,
                    'duration_formatted': duration_formatted,
                    'updated_at': datetime.utcnow()
                }
                await coll.update_one({'_id': existing['_id']}, {'$set': update_data})
                logger.info(
                    f"[AutoSync] Auto-updated {coll_name} post #{message_id} "
                    f"('{file_name}', {file_size / (1024*1024):.1f} MB). Link code '{existing['_id']}' preserved!"
                )
            else:
                logger.info(
                    f"[AutoSync] Purged cache & refreshed token for {coll_name} post #{message_id} (code: '{existing['_id']}')"
                )
            return

    # 2. Check collections: anime, webseries (batch objects with episodes array)
    for coll_name in ('anime', 'webseries'):
        coll = db.get_collection(coll_name)
        batch = await coll.find_one({'channel_id': channel_id, 'episodes.message_id': message_id})
        if batch:
            for ep in batch.get('episodes', []):
                if ep.get('message_id') == message_id:
                    ep_code = ep.get('code')
                    if ep_code:
                        evict_file_chunks(ep_code)
                    if (
                        file_size != ep.get('file_size')
                        or file_name != ep.get('file_name')
                        or duration != ep.get('duration')
                    ):
                        update_data = {
                            'episodes.$.file_name': file_name,
                            'episodes.$.file_size': file_size,
                            'episodes.$.mime_type': mime_type,
                            'episodes.$.duration': duration,
                            'episodes.$.duration_formatted': duration_formatted,
                            'updated_at': datetime.utcnow()
                        }
                        await coll.update_one(
                            {'_id': batch['_id'], 'episodes.message_id': message_id},
                            {'$set': update_data}
                        )
                        logger.info(
                            f"[AutoSync] Auto-updated episode #{message_id} in {coll_name} "
                            f"('{batch.get('title')}' -> '{file_name}'). Link code '{ep_code}' preserved!"
                        )
                    else:
                        logger.info(
                            f"[AutoSync] Purged cache & refreshed token for episode #{message_id} in {coll_name} (code: '{ep_code}')"
                        )
                    return
