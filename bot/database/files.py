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
    duration: int = 0,
    duration_formatted: str = "N/A"
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
        'duration': duration,
        'duration_formatted': duration_formatted,
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

    # 1. Search in single file collections / direct document match across all collections
    for col in (db.movies, db.direct_files, db.anime, db.webseries):
        if col is not None:
            doc = await col.find_one({'_id': code})
            if doc:
                # If it's a single file (not a batch container with episodes array)
                if 'episodes' not in doc:
                    return doc
                # If the batch _id itself was requested, return it
                return doc

    # 2. Search inside batch documents (anime, webseries)
    for col in (db.anime, db.webseries):
        if col is not None:
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
                            'duration': ep.get('duration', 0),
                            'duration_formatted': ep.get('duration_formatted', 'N/A'),
                            'category': batch_doc.get('category', 'anime'),
                            'user_id': batch_doc.get('user_id'),
                            'batch_id': batch_doc['_id']
                        }

    return None

async def delete_file(code: str) -> bool:
    """Deletes a file or removes an episode from a batch."""
    if not code:
        return False
        
    # Delete from single file collections or direct _id match
    for col in (db.movies, db.direct_files, db.anime, db.webseries):
        if col is not None:
            res = await col.delete_one({'_id': code})
            if res.deleted_count > 0:
                return True

    # Pull single episode from batch if it was part of an episodes array
    for col in (db.anime, db.webseries):
        if col is not None:
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
        'movie_titles': 0,
        'anime': 0,
        'anime_titles': 0,
        'anime_episodes': 0,
        'webseries': 0,
        'webseries_titles': 0,
        'webseries_episodes': 0,
        'direct_files': 0,
        'total_titles': 0
    }
    
    if db.movies is not None:
        stats['movie_titles'] = await db.movies.count_documents({})
        stats['movies'] = stats['movie_titles']
    if db.direct_files is not None:
        stats['direct_files'] = await db.direct_files.count_documents({})

    # Count titles and total playable files/episodes across anime and webseries
    for name, col in (('anime', db.anime), ('webseries', db.webseries)):
        if col is not None:
            stats[f'{name}_titles'] = await col.count_documents({})
            pipeline = [
                {'$project': {
                    'count': {
                        '$cond': [
                            {'$isArray': '$episodes'},
                            {'$size': {'$ifNull': ['$episodes', []]}},
                            1
                        ]
                    }
                }},
                {'$group': {'_id': None, 'total': {'$sum': '$count'}}}
            ]
            cursor = col.aggregate(pipeline)
            docs = await cursor.to_list(length=1)
            tot_eps = docs[0]['total'] if docs else 0
            stats[f'{name}_episodes'] = tot_eps
            stats[name] = tot_eps

    # Calculate unique parent Anime franchises (matching the 224 in StreamHub and uploader bot)
    anime_franchises = 0
    try:
        if db._client is not None:
            dbs = await db._client.list_database_names()
            if 'OmniArchiverDB' in dbs:
                anime_franchises = await db._client['OmniArchiverDB']['anime_index'].count_documents({})
    except Exception:
        pass

    if not anime_franchises and db.anime is not None:
        import re
        unique_titles = set()
        async for doc in db.anime.find({}, {'title': 1, 'file_name': 1}):
            t = doc.get('title') or doc.get('file_name', '')
            norm = re.sub(r'(?i)\s+[-:]?\s*(?:Part|Season|S|Cour|Arc)\s*\d+.*$', '', t).strip()
            if norm:
                unique_titles.add(norm.lower())
        anime_franchises = len(unique_titles) if unique_titles else stats['anime_titles']

    stats['anime_franchises'] = anime_franchises

    # Total titles = Parent Anime franchises + Live-Action Movies + Series
    stats['total_titles'] = (
        stats['anime_franchises'] + stats['movie_titles'] + stats['webseries_titles']
    )
    return stats

async def search_records(query: str, limit: int = 30) -> list[dict]:
    """Searches across movies, anime, webseries, and direct files by title or filename with smart multi-word matching."""
    import re
    from bot.config import Server
    from bot.modules.static import get_human_size

    if not query or not query.strip():
        return []

    clean_q = query.strip()
    words = [re.escape(w) for w in clean_q.split() if len(w) > 1]
    phrase_pattern = re.compile(re.escape(clean_q), re.IGNORECASE)

    # Build smart multi-word token filters (matches docs containing query words)
    if words:
        single_word_conds = [
            {
                '$or': [
                    {'file_name': {'$regex': w, '$options': 'i'}},
                    {'title': {'$regex': w, '$options': 'i'}}
                ]
            }
            for w in words
        ]
        single_filter = {'$or': [{'file_name': {'$regex': phrase_pattern}}, {'title': {'$regex': phrase_pattern}}, {'$and': single_word_conds}]}

        batch_word_conds = [
            {'title': {'$regex': w, '$options': 'i'}}
            for w in words
        ]
        batch_filter = {'$or': [{'title': {'$regex': phrase_pattern}}, {'$and': batch_word_conds}]}
    else:
        single_filter = {'$or': [{'file_name': {'$regex': phrase_pattern}}, {'title': {'$regex': phrase_pattern}}]}
        batch_filter = {'title': {'$regex': phrase_pattern}}

    results = []

    # 1. Search in single files across movies, direct_files, and single anime/series
    for col, default_cat in (
        (db.movies, 'movies'),
        (db.direct_files, 'direct_files'),
        (db.anime, 'anime'),
        (db.webseries, 'webseries')
    ):
        if col is not None and len(results) < limit:
            query_cond = dict(single_filter)
            if col in (db.anime, db.webseries):
                query_cond['episodes'] = {'$exists': False}

            cursor = col.find(query_cond).sort('created_at', -1).limit(limit - len(results))

            async for doc in cursor:
                code = doc.get('code', doc.get('_id'))
                cat = doc.get('category', default_cat)
                results.append({
                    'type': 'movie',
                    'category': cat,
                    'code': code,
                    'title': doc.get('title') or doc.get('file_name'),
                    'file_name': doc.get('file_name'),
                    'file_size': doc.get('file_size', 0),
                    'size_formatted': get_human_size(doc.get('file_size', 0)),
                    'duration': doc.get('duration', 0),
                    'duration_formatted': doc.get('duration_formatted', 'N/A'),
                    'stream_url': f"{Server.BASE_URL}/stream/{code}",
                    'download_url': f"{Server.BASE_URL}/dl/{code}",
                    'api_url': f"{Server.BASE_URL}/api/file/{code}"
                })

    # 2. Search in batches (anime, webseries)
    for col, cat_name in ((db.anime, 'anime'), (db.webseries, 'webseries')):
        if col is not None and len(results) < limit:
            b_filter = dict(batch_filter)
            b_filter['episodes'] = {'$exists': True}
            cursor = col.find(b_filter).sort('created_at', -1).limit(limit - len(results))

            async for batch_doc in cursor:
                batch_id = batch_doc.get('_id')
                episodes = batch_doc.get('episodes', [])
                total_size = sum(ep.get('file_size', 0) for ep in episodes)
                
                formatted_episodes = []
                for ep in episodes:
                    code = ep['code']
                    formatted_episodes.append({
                        'episode_num': ep.get('episode_num', 1),
                        'file_name': ep.get('file_name', ''),
                        'file_size': ep.get('file_size', 0),
                        'size_formatted': get_human_size(ep.get('file_size', 0)),
                        'duration': ep.get('duration', 0),
                        'duration_formatted': ep.get('duration_formatted', 'N/A'),
                        'stream_url': f"{Server.BASE_URL}/stream/{code}",
                        'download_url': f"{Server.BASE_URL}/dl/{code}",
                        'code': code
                    })

                results.append({
                    'type': 'batch',
                    'category': cat_name,
                    'batch_id': batch_id,
                    'title': batch_doc.get('title') or f"{cat_name.upper()} Batch ({len(episodes)} episodes)",
                    'total_episodes': len(episodes),
                    'total_size': total_size,
                    'size_formatted': get_human_size(total_size),
                    'api_url': f"{Server.BASE_URL}/api/batch/{batch_id}",
                    'episodes': formatted_episodes
                })

    return results[:limit]


