from motor.motor_asyncio import AsyncIOMotorClient
from bot.config import Database
from logging import getLogger

logger = getLogger('bot')

class MongoDatabase:
    def __init__(self):
        self._client = None
        self.db = None
        self.movies = None
        self.anime = None
        self.webseries = None
        self.direct_files = None

    def connect(self):
        try:
            self._client = AsyncIOMotorClient(Database.DATABASE_URL)
            self.db = self._client[Database.DATABASE_NAME]
            self.movies = self.db['movies']
            self.anime = self.db['anime']
            self.webseries = self.db['webseries']
            self.direct_files = self.db['direct_files']
            logger.info("Connected to MongoDB database: %s", Database.DATABASE_NAME)
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", e)
            raise e

    def get_collection(self, category: str):
        cat = category.lower()
        if cat in ('movie', 'movies'):
            return self.movies
        elif cat in ('anime', 'animes'):
            return self.anime
        elif cat in ('series', 'webseries', 'tv'):
            return self.webseries
        else:
            return self.direct_files

db = MongoDatabase()
