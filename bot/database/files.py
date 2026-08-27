from secrets import token_hex
from datetime import datetime
from bot.config import Telegram
from bot.database import db

async def save_file(
    channel_id: int,
    message_id: int,
    file_name: str,
    file_size: int,
    mime_type: str,
    user_id: int,
    category: str = 'movies',
    title: str = None,
    episode: int = None,
    season: int = None
) -> dict:
    collection = db.get_collection(category)
    
    # Check if this exact channel message is already indexed in this collection
    existing = await collection.find_one({
        'channel_id': channel_id,
        'message_id': message_id
    })
    if existing:
        return existing

    code = token_hex(Telegram.SECRET_CODE_LENGTH)
    doc = {
        '_id': code,
        'code': code,
        'channel_id': channel_id,
        'message_id': message_id,
        'file_name': file_name,
        'file_size': file_size,
        'mime_type': mime_type,
        'user_id': user_id,
        'category': category.lower(),
        'title': title or file_name,
        'episode': episode,
        'season': season,
        'created_at': datetime.utcnow()
    }
    
    await collection.insert_one(doc)
    return doc

async def get_file(code: str, category_hint: str = None) -> dict | None:
    if not code:
        return None

    if category_hint:
        col = db.get_collection(category_hint)
        doc = await col.find_one({'_id': code})
        if doc:
            return doc

    # Search in priority order: movies, anime, webseries, direct_files
    for col in (db.movies, db.anime, db.webseries, db.direct_files):
        if col is not None:
            doc = await col.find_one({'_id': code})
            if doc:
                return doc
    return None

async def delete_file(code: str) -> bool:
    if not code:
        return False
    for col in (db.movies, db.anime, db.webseries, db.direct_files):
        if col is not None:
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True
    return False

async def get_stats() -> dict:
    stats = {}
    for name, col in (
        ('movies', db.movies),
        ('anime', db.anime),
        ('webseries', db.webseries),
        ('direct_files', db.direct_files)
    ):
        if col is not None:
            stats[name] = await col.count_documents({})
        else:
            stats[name] = 0
    return stats
