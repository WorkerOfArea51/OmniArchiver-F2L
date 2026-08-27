import time
import logging
from typing import Optional, Dict, Any, List
import aiosqlite
from bot.core.config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Async Database Layer supporting multi-channel indexing, arc/saga grouping, and full-text search."""

    def __init__(self):
        self.is_mongo = bool(Config.DATABASE_URL.startswith("mongodb"))
        self._mongo_client = None
        self._mongo_db = None
        self.sqlite_path = Config.SQLITE_PATH

    async def init(self):
        if self.is_mongo:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                self._mongo_client = AsyncIOMotorClient(Config.DATABASE_URL)
                self._mongo_db = self._mongo_client.get_default_database()
                logger.info("Successfully connected to MongoDB.")
            except Exception as e:
                logger.error(f"MongoDB connection failed: {e}. Falling back to SQLite.")
                self.is_mongo = False

        if not self.is_mongo:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id INTEGER,
                        message_id INTEGER,
                        file_name TEXT,
                        file_size INTEGER,
                        mime_type TEXT,
                        caption TEXT,
                        series_name TEXT,
                        arc_name TEXT,
                        episode_num TEXT,
                        created_at REAL,
                        views INTEGER DEFAULT 0,
                        downloads INTEGER DEFAULT 0,
                        UNIQUE(channel_id, message_id)
                    )
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_search ON files (file_name, series_name, arc_name, caption)
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        is_banned INTEGER DEFAULT 0,
                        created_at REAL
                    )
                """)
                await db.commit()
            logger.info(f"SQLite database initialized at: {self.sqlite_path}")

    async def add_file(
        self,
        channel_id: int,
        message_id: int,
        file_name: str,
        file_size: int,
        mime_type: str,
        caption: str = "",
        series_name: str = "",
        arc_name: str = "",
        episode_num: str = ""
    ):
        now = time.time()
        if self.is_mongo:
            await self._mongo_db.files.update_one(
                {"channel_id": channel_id, "message_id": message_id},
                {"$set": {
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "file_name": file_name,
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "caption": caption,
                    "series_name": series_name,
                    "arc_name": arc_name,
                    "episode_num": episode_num,
                    "created_at": now
                }},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO files (
                        channel_id, message_id, file_name, file_size, mime_type, caption, series_name, arc_name, episode_num, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (channel_id, message_id, file_name, file_size, mime_type, caption, series_name, arc_name, episode_num, now))
                await db.commit()

    async def get_file(self, message_id: int, channel_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if self.is_mongo:
            query = {"message_id": message_id}
            if channel_id: query["channel_id"] = channel_id
            return await self._mongo_db.files.find_one(query)
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                if channel_id:
                    cursor = await db.execute("SELECT * FROM files WHERE channel_id = ? AND message_id = ?", (channel_id, message_id))
                else:
                    cursor = await db.execute("SELECT * FROM files WHERE message_id = ? LIMIT 1", (message_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def search_files(self, query: str, limit: int = 60) -> List[Dict[str, Any]]:
        clean_q = f"%{query.strip()}%"
        if self.is_mongo:
            cursor = self._mongo_db.files.find({
                "$or": [
                    {"file_name": {"$regex": query, "$options": "i"}},
                    {"series_name": {"$regex": query, "$options": "i"}},
                    {"arc_name": {"$regex": query, "$options": "i"}},
                    {"caption": {"$regex": query, "$options": "i"}}
                ]
            }).limit(limit)
            return await cursor.to_list(length=limit)
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM files 
                    WHERE file_name LIKE ? OR series_name LIKE ? OR arc_name LIKE ? OR caption LIKE ?
                    ORDER BY id ASC LIMIT ?
                """, (clean_q, clean_q, clean_q, clean_q, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def get_series_arcs(self, series_name: str) -> List[str]:
        clean_name = f"%{series_name.strip()}%"
        if self.is_mongo:
            arcs = await self._mongo_db.files.distinct("arc_name", {"series_name": {"$regex": series_name, "$options": "i"}})
            return [a for a in arcs if a]
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                async with db.execute("""
                    SELECT DISTINCT arc_name FROM files 
                    WHERE (series_name LIKE ? OR arc_name LIKE ?) AND arc_name != ''
                    ORDER BY id ASC
                """, (clean_name, clean_name)) as cursor:
                    rows = await cursor.fetchall()
                    return [r[0] for r in rows if r[0]]

    async def get_arc_files(self, arc_name: str) -> List[Dict[str, Any]]:
        clean_name = f"%{arc_name.strip()}%"
        if self.is_mongo:
            cursor = self._mongo_db.files.find({"arc_name": {"$regex": arc_name, "$options": "i"}}).sort("id", 1)
            return await cursor.to_list(length=150)
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM files 
                    WHERE arc_name LIKE ? OR caption LIKE ?
                    ORDER BY id ASC LIMIT 150
                """, (clean_name, clean_name)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def increment_views(self, channel_id: int, message_id: int):
        if self.is_mongo:
            await self._mongo_db.files.update_one({"channel_id": channel_id, "message_id": message_id}, {"$inc": {"views": 1}})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("UPDATE files SET views = views + 1 WHERE channel_id = ? AND message_id = ?", (channel_id, message_id))
                await db.commit()

    async def increment_downloads(self, channel_id: int, message_id: int):
        if self.is_mongo:
            await self._mongo_db.files.update_one({"channel_id": channel_id, "message_id": message_id}, {"$inc": {"downloads": 1}})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("UPDATE files SET downloads = downloads + 1 WHERE channel_id = ? AND message_id = ?", (channel_id, message_id))
                await db.commit()

    async def is_user_banned(self, user_id: int) -> bool:
        if self.is_mongo:
            user = await self._mongo_db.users.find_one({"user_id": user_id})
            return bool(user and user.get("is_banned"))
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return bool(row and row[0] == 1)

    async def ban_user(self, user_id: int, ban: bool = True):
        if self.is_mongo:
            await self._mongo_db.users.update_one(
                {"user_id": user_id},
                {"$set": {"is_banned": 1 if ban else 0, "created_at": time.time()}},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO users (user_id, is_banned, created_at) VALUES (?, ?, ?)",
                    (user_id, 1 if ban else 0, time.time())
                )
                await db.commit()

    async def get_total_files(self) -> int:
        if self.is_mongo:
            return await self._mongo_db.files.count_documents({})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                async with db.execute("SELECT COUNT(*) FROM files") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

db = DatabaseManager()
