import os
import sys
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Telegram Credentials ---
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "").strip()
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
    
    # Auxiliary multi-token worker pool
    raw_multi_tokens = os.environ.get("MULTI_TOKENS", "").strip()
    MULTI_TOKENS = [t.strip() for t in raw_multi_tokens.split(",") if t.strip()]

    # Private Storage Channel ID
    BIN_CHANNEL_ID = int(os.environ.get("BIN_CHANNEL_ID", "0"))

    # --- Server Settings ---
    BIND_ADDRESS = os.environ.get("BIND_ADDRESS", "0.0.0.0").strip()
    PORT = int(os.environ.get("PORT", 8080))
    HAS_SSL = os.environ.get("HAS_SSL", "True").lower() in ("true", "1", "yes")

    raw_base_url = os.environ.get("BASE_URL", "").strip().rstrip("/")
    if not raw_base_url:
        raw_base_url = f"{BIND_ADDRESS}:{PORT}"
    
    SCHEME = "https" if HAS_SSL else "http"
    if not raw_base_url.startswith(("http://", "https://")):
        BASE_URL = f"{SCHEME}://{raw_base_url}"
    else:
        BASE_URL = raw_base_url

    # --- Access Control & Permissions ---
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    raw_auth = os.environ.get("AUTH_USERS", "").strip()
    AUTH_USERS = [int(x.strip()) for x in raw_auth.split(",") if x.strip().isdigit()]
    if OWNER_ID and OWNER_ID not in AUTH_USERS:
        AUTH_USERS.append(OWNER_ID)

    # --- Database ---
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
    SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "omni_archiver.db")

    # --- Performance, Streaming & Caching ---
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 512 * 1024))  # 512 KB
    CACHE_SIZE_MB = int(os.environ.get("CACHE_SIZE_MB", 32))    # 32 MB LRU cache
    SLEEP_THRESHOLD = int(os.environ.get("SLEEP_THRESHOLD", 60))
    WORKERS = int(os.environ.get("WORKERS", 6))

    # Working Directory
    WORKDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    @classmethod
    def validate(cls):
        missing = []
        if not cls.API_ID: missing.append("API_ID")
        if not cls.API_HASH: missing.append("API_HASH")
        if not cls.BOT_TOKEN: missing.append("BOT_TOKEN")
        if not cls.BIN_CHANNEL_ID: missing.append("BIN_CHANNEL_ID")

        if missing:
            print(f"[FATAL] Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
            print("[INFO] Please create a .env file based on .env.example", file=sys.stderr)
            sys.exit(1)
