import asyncio
from collections import OrderedDict
import logging
from bot.core.config import Config

logger = logging.getLogger(__name__)

class LRUChunkCache:
    """
    In-memory LRU Ring Buffer Chunk Cache.
    Maintains fast access to media headers (first 5MB & last 2MB)
    so media player probing and initial playback starts instantly without MTProto lag.
    """

    def __init__(self, max_size_mb: int = 32):
        self.max_bytes = max_size_mb * 1024 * 1024
        self.current_bytes = 0
        self.cache: OrderedDict[str, bytes] = OrderedDict()
        self._lock = asyncio.Lock()

    def _make_key(self, message_id: int, offset: int, limit: int) -> str:
        return f"{message_id}:{offset}:{limit}"

    async def get(self, message_id: int, offset: int, limit: int) -> bytes | None:
        key = self._make_key(message_id, offset, limit)
        async with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    async def put(self, message_id: int, offset: int, limit: int, data: bytes):
        key = self._make_key(message_id, offset, limit)
        data_len = len(data)
        if data_len > self.max_bytes:
            return

        async with self._lock:
            if key in self.cache:
                self.current_bytes -= len(self.cache[key])
                del self.cache[key]

            # Evict oldest until space is available
            while self.current_bytes + data_len > self.max_bytes and self.cache:
                _, old_val = self.cache.popitem(last=False)
                self.current_bytes -= len(old_val)

            self.cache[key] = data
            self.current_bytes += data_len

    async def clear(self):
        async with self._lock:
            self.cache.clear()
            self.current_bytes = 0

chunk_cache = LRUChunkCache(max_size_mb=Config.CACHE_SIZE_MB)
