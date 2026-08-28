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
    title: str = None
) -> dict:
    """Saves a single movie or direct file."""
    collection = db.get_collection(category)
    
    # Check if this exact channel message is already indexed
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
        'created_at': datetime.utcnow()
    }
    
    await collection.insert_one(doc)
    return doc

async def save_batch(
    channel_id: int,
    start_id: int,
    end_id: int,
    category: str,
    user_id: int,
    episodes: list[dict],
    title: str = None
) -> dict:
    """Saves an entire batch of anime or web series episodes as a SINGLE unified document."""
    collection = db.get_collection(category)

    # Check if exact batch range is already indexed
    existing = await collection.find_one({
        'channel_id': channel_id,
        'start_id': start_id,
        'end_id': end_id
    })
    if existing:
        return existing

    batch_code = token_hex(16)
    doc = {
        '_id': batch_code,
        'batch_code': batch_code,
        'title': title or f"{category.upper()} Batch ({len(episodes)} episodes)",
        'category': category.lower(),
        'channel_id': channel_id,
        'start_id': start_id,
        'end_id': end_id,
        'total_episodes': len(episodes),
        'user_id': user_id,
        'created_at': datetime.utcnow(),
        'episodes': episodes
    }

    await collection.insert_one(doc)
    return doc

async def get_file(code: str, category_hint: str = None) -> dict | None:
    """Resolves a file by its unique code, supporting both single documents and episodes inside batch documents."""
    if not code:
        return None

    # 1. Search in single file collections (movies, direct_files)
    for col in (db.movies, db.direct_files):
        if col is not None:
            doc = await col.find_one({'_id': code})
            if doc:
                return doc

    # 2. Search inside batch documents (anime, webseries)
    for col in (db.anime, db.webseries):
        if col is not None:
            # First check if the code is the batch _id itself
            batch_doc = await col.find_one({'_id': code})
            if batch_doc:
                return batch_doc

            # Check if code matches an episode inside the episodes array
            batch_doc = await col.find_one({'episodes.code': code})
            if batch_doc:
                for ep in batch_doc.get('episodes', []):
                    if ep.get('code') == code:
                        return {
                            '_id': ep['code'],
                            'code': ep['code'],
                            'channel_id': batch_doc['channel_id'],
                            'message_id': ep['message_id'],
                            'file_name': ep['file_name'],
                            'file_size': ep['file_size'],
                            'mime_type': ep['mime_type'],
                            'category': batch_doc.get('category', 'anime'),
                            'user_id': batch_doc.get('user_id'),
                            'batch_id': batch_doc['_id']
                        }

    return None

async def delete_file(code: str) -> bool:
    """Deletes a file or removes an episode from a batch."""
    if not code:
        return False
        
    # Delete from single file collections
    for col in (db.movies, db.direct_files):
        if col is not None:
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True

    # Delete or pull from batch collections
    for col in (db.anime, db.webseries):
        if col is not None:
            # Delete whole batch if batch code matched
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True
            
            # Otherwise pull single episode from batch
            res = await col.update_one(
                {'episodes.code': code},
                {'$pull': {'episodes': {'code': code}}}
            )
            if res.modified_count > 0:
                return True

    return False

async def add_bandwidth_bytes(byte_count: int):
    try:
        if db.db is not None and byte_count > 0:
            await db.db['analytics'].update_one(
                {'_id': 'bandwidth'},
                {'$inc': {'bytes_streamed': byte_count, 'requests': 1}},
                upsert=True
            )
    except Exception:
        pass

async def get_bandwidth_stats() -> tuple[int, int]:
    try:
        if db.db is not None:
            doc = await db.db['analytics'].find_one({'_id': 'bandwidth'})
            if doc:
                return doc.get('bytes_streamed', 0), doc.get('requests', 0)
    except Exception:
        pass
    return 0, 0

async def get_stats() -> dict:
    stats = {
        'movies': 0,
        'anime': 0,
        'webseries': 0,
        'direct_files': 0
    }
    
    if db.movies is not None:
        stats['movies'] = await db.movies.count_documents({})
    if db.direct_files is not None:
        stats['direct_files'] = await db.direct_files.count_documents({})

    # Count total episodes across all batches in anime and webseries
    for name, col in (('anime', db.anime), ('webseries', db.webseries)):
        if col is not None:
            pipeline = [
                {'$project': {'count': {'$size': {'$ifNull': ['$episodes', []]}}}},
                {'$group': {'_id': None, 'total': {'$sum': '$count'}}}
            ]
            cursor = col.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            stats[name] = docs[0]['total'] if docs else 0

    return stats

