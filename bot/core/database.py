import time
import logging
from typing import Optional, Dict, Any
import aiosqlite
from bot.core.config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Async Database Layer supporting SQLite (default) or MongoDB (Motor)."""

    def __init__(self):
        self.is_mongo = bool(Config.DATABASE_URL.startswith("mongodb"))
        self._mongo_client = None
        self._mongo_db = None
        self.sqlite_path = Config.SQLITE_PATH

    async def init(self):
        """Initializes database tables / collections."""
        if self.is_mongo:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
                self._mongo_client = AsyncIOMotorClient(Config.DATABASE_URL)
                self._mongo_db = self._mongo_client.get_default_database()
                logger.info("Successfully connected to MongoDB.")
            except Exception as e:
                logger.error(f"MongoDB connection failed: {e}. Falling back to SQLite.", exc_info=True)
                self.is_mongo = False

        if not self.is_mongo:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        message_id INTEGER PRIMARY KEY,
                        file_name TEXT,
                        file_size INTEGER,
                        mime_type TEXT,
                        unique_hash TEXT,
                        views INTEGER DEFAULT 0,
                        downloads INTEGER DEFAULT 0,
                        created_at REAL
                    )
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

    async def add_file(self, message_id: int, file_name: str, file_size: int, mime_type: str, unique_hash: str):
        """Stores a newly generated file record."""
        now = time.time()
        if self.is_mongo:
            await self._mongo_db.files.update_one(
                {"message_id": message_id},
                {"$set": {
                    "message_id": message_id,
                    "file_name": file_name,
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "unique_hash": unique_hash,
                    "created_at": now
                }},
                upsert=True
            )
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO files (message_id, file_name, file_size, mime_type, unique_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (message_id, file_name, file_size, mime_type, unique_hash, now))
                await db.commit()

    async def get_file(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Fetches file metadata by message_id."""
        if self.is_mongo:
            return await self._mongo_db.files.find_one({"message_id": message_id})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT * FROM files WHERE message_id = ?", (message_id,)) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None

    async def increment_views(self, message_id: int):
        """Increments view/stream counter."""
        if self.is_mongo:
            await self._mongo_db.files.update_one({"message_id": message_id}, {"$inc": {"views": 1}})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("UPDATE files SET views = views + 1 WHERE message_id = ?", (message_id,))
                await db.commit()

    async def increment_downloads(self, message_id: int):
        """Increments download counter."""
        if self.is_mongo:
            await self._mongo_db.files.update_one({"message_id": message_id}, {"$inc": {"downloads": 1}})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                await db.execute("UPDATE files SET downloads = downloads + 1 WHERE message_id = ?", (message_id,))
                await db.commit()

    async def is_user_banned(self, user_id: int) -> bool:
        """Checks if a user is banned."""
        if self.is_mongo:
            user = await self._mongo_db.users.find_one({"user_id": user_id})
            return bool(user and user.get("is_banned"))
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    return bool(row and row[0] == 1)

    async def ban_user(self, user_id: int, ban: bool = True):
        """Bans or unbans a user."""
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
        """Returns count of indexed files."""
        if self.is_mongo:
            return await self._mongo_db.files.count_documents({})
        else:
            async with aiosqlite.connect(self.sqlite_path) as db:
                async with db.execute("SELECT COUNT(*) FROM files") as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else 0

db = DatabaseManager()
