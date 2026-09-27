import os
import asyncio
from collections import OrderedDict
from logging import getLogger
from math import ceil

logger = getLogger('cache')

# Cache storage directory on local VPS SSD
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "cache", "media")

# Maximum disk cache size: 150 MB (stores Head 2MB + Tail 1MB for ~50 active videos)
MAX_CACHE_BYTES = 150 * 1024 * 1024

_CACHE_INDEX: OrderedDict[tuple[str, int], int] = OrderedDict()
_TOTAL_CACHE_SIZE = 0
_CACHE_LOCK = asyncio.Lock()
_INITIALIZED = False

def is_head_or_tail(chunk_idx: int, total_chunks: int) -> bool:
    """
    Returns True if chunk_idx belongs to the head (first 2 MB: EBML header/codecs)
    or tail (last 1-2 MB: Matroska Cues seek index / MP4 moov atom).
    Only these critical seek chunks are cached to protect disk space.
    """
    if chunk_idx in (0, 1):
        return True
    if total_chunks > 0 and chunk_idx >= max(0, total_chunks - 2):
        return True
    return False

def init_cache():
    """Initializes the local SSD chunk cache directory and scans existing chunks into LRU index."""
    global _INITIALIZED, _TOTAL_CACHE_SIZE
    if _INITIALIZED:
        return

    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        total = 0
        for fname in os.listdir(CACHE_DIR):
            if fname.endswith(".chunk"):
                fpath = os.path.join(CACHE_DIR, fname)
                try:
                    fsize = os.path.getsize(fpath)
                    # Expected format: {file_code}_{chunk_idx}.chunk
                    parts = fname[:-6].rsplit('_', 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        code = parts[0]
                        c_idx = int(parts[1])
                        _CACHE_INDEX[(code, c_idx)] = fsize
                        total += fsize
                except Exception:
                    pass
        _TOTAL_CACHE_SIZE = total
        _INITIALIZED = True
        logger.info("Initialized Head & Tail disk cache: %d chunk(s) loaded (%.2f MB total).", len(_CACHE_INDEX), total / (1024 * 1024))
    except Exception as e:
        logger.warning("Failed to initialize chunk cache directory: %s", e)

async def get_cached_chunk(file_code: str, chunk_idx: int) -> bytes | None:
    """
    Retrieves a cached chunk from local SSD in ~0.5ms.
    Returns bytes if present, or None if not cached.
    """
    if not _INITIALIZED:
        init_cache()

    key = (file_code, chunk_idx)
    async with _CACHE_LOCK:
        if key not in _CACHE_INDEX:
            return None
        _CACHE_INDEX.move_to_end(key)

    filename = f"{file_code}_{chunk_idx}.chunk"
    path = os.path.join(CACHE_DIR, filename)

    try:
        def _read():
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    return f.read()
            return None

        data = await asyncio.to_thread(_read)
        if data is not None and len(data) > 0:
            return data
    except Exception as e:
        logger.warning("Error reading cached chunk %s_%d: %s", file_code, chunk_idx, e)

    # If file was missing or corrupt, evict key from index
    async with _CACHE_LOCK:
        if key in _CACHE_INDEX:
            _CACHE_INDEX.pop(key, None)
    return None

async def put_cached_chunk(file_code: str, chunk_idx: int, data: bytes, total_chunks: int):
    """
    Persists a critical head/tail chunk to local SSD with automatic LRU eviction.
    """
    if not _INITIALIZED:
        init_cache()

    if not is_head_or_tail(chunk_idx, total_chunks):
        return
    if not data:
        return

    key = (file_code, chunk_idx)
    chunk_len = len(data)
    filename = f"{file_code}_{chunk_idx}.chunk"
    path = os.path.join(CACHE_DIR, filename)

    try:
        def _write():
            with open(path, 'wb') as f:
                f.write(data)

        await asyncio.to_thread(_write)

        global _TOTAL_CACHE_SIZE
        async with _CACHE_LOCK:
            old_size = _CACHE_INDEX.pop(key, 0)
            _TOTAL_CACHE_SIZE -= old_size

            _CACHE_INDEX[key] = chunk_len
            _TOTAL_CACHE_SIZE += chunk_len

            # Evict oldest chunks if exceeding MAX_CACHE_BYTES
            while _TOTAL_CACHE_SIZE > MAX_CACHE_BYTES and _CACHE_INDEX:
                evict_key, evict_size = _CACHE_INDEX.popitem(last=False)
                _TOTAL_CACHE_SIZE -= evict_size
                evict_file = os.path.join(CACHE_DIR, f"{evict_key[0]}_{evict_key[1]}.chunk")
                try:
                    if os.path.exists(evict_file):
                        os.remove(evict_file)
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Error saving cached chunk %s_%d: %s", file_code, chunk_idx, e)

def clear_media_cache():
    """Removes all cached chunks from disk to free space immediately."""
    global _TOTAL_CACHE_SIZE
    try:
        if os.path.exists(CACHE_DIR):
            for fname in os.listdir(CACHE_DIR):
                if fname.endswith(".chunk"):
                    try:
                        os.remove(os.path.join(CACHE_DIR, fname))
                    except Exception:
                        pass
        _CACHE_INDEX.clear()
        _TOTAL_CACHE_SIZE = 0
        logger.info("Cleared all media cache chunks from disk.")
    except Exception as e:
        logger.warning("Error clearing media cache: %s", e)
