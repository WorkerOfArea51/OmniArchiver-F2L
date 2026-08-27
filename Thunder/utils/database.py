# -*- coding: utf-8 -*-
# Thunder/utils/database.py - OmniArchiver Async Database Layer

import re
import time
import logging
from typing import Optional, Dict, Any, List
import aiosqlite
from Thunder.vars import Var

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Async Database Layer supporting MongoDB Atlas & SQLite WAL mode."""

    def __init__(self):
        self.is_mongo = bool(Var.DATABASE_URL.startswith("mongodb"))
        self._mongo_client = None
        self._mongo_db = None
        self.sqlite_path = Var.SQLITE_PATH

    async def init(self):
        if self.is_mongo:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                self._mongo_client = AsyncIOMotorClient(Var.DATABASE_URL)
                try:
                    self._mongo_db = self._mongo_client.get_default_database()
                except Exception:
                    self._mongo_db = self._mongo_client["omni_archiver"]
                
                await self._mongo_db.command("ping")
                logger.info("Successfully connected and authenticated to MongoDB Atlas.")
            except Exception as e:
                logger.error(f"MongoDB connection failed: {e}. Falling back to SQLite.")
                self.is_mongo = False

        if not self.is_mongo:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                await db.execute("PRAGMA journal_mode=WAL;")
                await db.execute("PRAGMA busy_timeout=30000;")
                await db.execute("PRAGMA synchronous=NORMAL;")
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
                await db.commit()
                logger.info(f"SQLite WAL database initialized at: {self.sqlite_path}")

    async def ensure_indexes(self, raise_on_error: bool = False):
        if self.is_mongo and self._mongo_db is not None:
            try:
                await self._mongo_db.files.create_index([("channel_id", 1), ("message_id", 1)], unique=True)
                await self._mongo_db.files.create_index([("file_name", "text"), ("series_name", "text"), ("arc_name", "text")])
                return True
            except Exception as e:
                logger.warning(f"Index creation note: {e}")
                if raise_on_error:
                    raise e
        return True

    async def insert_file(
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
            doc = {
                "channel_id": channel_id,
                "message_id": message_id,
                "file_name": file_name,
                "file_size": file_size,
                "mime_type": mime_type,
                "caption": caption,
                "series_name": series_name,
                "arc_name": arc_name,
                "episode_num": episode_num,
                "created_at": now,
                "views": 0,
                "downloads": 0
            }
            await self._mongo_db.files.update_one(
                {"channel_id": channel_id, "message_id": message_id},
                {"$set": doc},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
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
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                db.row_factory = aiosqlite.Row
                if channel_id:
                    cursor = await db.execute("SELECT * FROM files WHERE channel_id = ? AND message_id = ?", (channel_id, message_id))
                else:
                    cursor = await db.execute("SELECT * FROM files WHERE message_id = ? LIMIT 1", (message_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def search_files(self, query: str, limit: int = 60) -> List[Dict[str, Any]]:
        words = [re.escape(w) for w in query.strip().split() if w]
        if not words:
            return []
        
        regex_pattern = ".*".join(words)
        sqlite_like = "%" + "%".join(query.strip().split()) + "%"

        if self.is_mongo:
            cursor = self._mongo_db.files.find({
                "$or": [
                    {"file_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"series_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"arc_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"caption": {"$regex": regex_pattern, "$options": "i"}}
                ]
            }).limit(limit)
            return await cursor.to_list(length=limit)
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("""
                    SELECT * FROM files 
                    WHERE file_name LIKE ? OR series_name LIKE ? OR arc_name LIKE ? OR caption LIKE ?
                    ORDER BY id ASC LIMIT ?
                """, (sqlite_like, sqlite_like, sqlite_like, sqlite_like, limit)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def get_series_arcs(self, series_name: str) -> List[str]:
        clean_name = f"%{series_name.strip()}%"
        if self.is_mongo:
            arcs = await self._mongo_db.files.distinct("arc_name", {"series_name": {"$regex": series_name, "$options": "i"}})
            return [a for a in arcs if a]
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                async with db.execute("""
                    SELECT DISTINCT arc_name FROM files 
                    WHERE (series_name LIKE ? OR arc_name LIKE ?) AND arc_name != ''
                    ORDER BY id ASC
                """, (clean_name, clean_name)) as cursor:
                    rows = await cursor.fetchall()
                    return [r[0] for r in rows if r[0]]

    async def get_arc_files(self, arc_name: str) -> List[Dict[str, Any]]:
        clean_arc = f"%{arc_name.strip()}%"
        if self.is_mongo:
            cursor = self._mongo_db.files.find({"arc_name": {"$regex": arc_name, "$options": "i"}}).sort("id", 1).limit(200)
            return await cursor.to_list(length=200)
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM files WHERE arc_name LIKE ? ORDER BY id ASC LIMIT 200", (clean_arc,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

    async def get_total_files(self) -> int:
        if self.is_mongo:
            return await self._mongo_db.files.count_documents({})
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                async with db.execute("SELECT COUNT(*) FROM files") as cursor:
                    res = await cursor.fetchone()
                    return res[0] if res else 0

    async def increment_views(self, channel_id: int, message_id: int):
        if self.is_mongo:
            await self._mongo_db.files.update_one({"channel_id": channel_id, "message_id": message_id}, {"$inc": {"views": 1}})

    async def increment_downloads(self, channel_id: int, message_id: int):
        if self.is_mongo:
            await self._mongo_db.files.update_one({"channel_id": channel_id, "message_id": message_id}, {"$inc": {"downloads": 1}})

    async def delete_file(self, message_id: int, channel_id: Optional[int] = None):
        if self.is_mongo:
            q = {"message_id": message_id}
            if channel_id: q["channel_id"] = channel_id
            await self._mongo_db.files.delete_many(q)
        else:
            async with aiosqlite.connect(self.sqlite_path, timeout=30.0) as db:
                if channel_id:
                    await db.execute("DELETE FROM files WHERE channel_id = ? AND message_id = ?", (channel_id, message_id))
                else:
                    await db.execute("DELETE FROM files WHERE message_id = ?", (message_id,))
                await db.commit()

    async def get_restart_message(self) -> Optional[Dict[str, Any]]:
        return None

    async def delete_restart_message(self, message_id: int):
        pass

    async def close(self):
        if self._mongo_client:
            self._mongo_client.close()

db = DatabaseManager()
