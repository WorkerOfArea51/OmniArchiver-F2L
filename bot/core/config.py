import os
import sys
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --- Telegram Credentials ---
    API_ID = int(os.environ.get("API_ID", "0"))
    API_HASH = os.environ.get("API_HASH", "").strip()
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

    # Multi-client worker pool tokens
    raw_multi_tokens = os.environ.get("MULTI_TOKENS", "").strip()
    MULTI_TOKENS = [t.strip() for t in raw_multi_tokens.split(",") if t.strip()]

    # Multiple Channel IDs (Anime, Movie, Web Series, etc.)
    # Comma-separated list of channel IDs (e.g. -10012345,-10067890,-100112233)
    raw_channels = os.environ.get("CHANNELS", "").strip()
    CHANNELS = [int(c.strip()) for c in raw_channels.split(",") if c.strip().lstrip("-").isdigit()]

    # Optional legacy fallback
    BIN_CHANNEL_ID = int(os.environ.get("BIN_CHANNEL_ID", "0"))
    if BIN_CHANNEL_ID and BIN_CHANNEL_ID not in CHANNELS:
        CHANNELS.append(BIN_CHANNEL_ID)

    # --- Server Settings ---
    # Alwaysdata provides $IP (IPv6/IPv4) and $PORT (e.g. 8100)
    BIND_ADDRESS = os.environ.get("IP") or os.environ.get("BIND_ADDRESS") or "::"
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

    # --- Admin & Permissions ---
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
    raw_auth = os.environ.get("AUTH_USERS", "").strip()
    AUTH_USERS = [int(x.strip()) for x in raw_auth.split(",") if x.strip().isdigit()]
    if OWNER_ID and OWNER_ID not in AUTH_USERS:
        AUTH_USERS.append(OWNER_ID)

    # --- Database ---
    DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
    SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "omni_archiver.db")

    # --- Performance, Streaming & Caching ---
    CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 512 * 1024))
    CACHE_SIZE_MB = int(os.environ.get("CACHE_SIZE_MB", 32))
    SLEEP_THRESHOLD = int(os.environ.get("SLEEP_THRESHOLD", 60))
    WORKERS = int(os.environ.get("WORKERS", 6))

    WORKDIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    @classmethod
    def validate(cls):
        missing = []
        if not cls.API_ID: missing.append("API_ID")
        if not cls.API_HASH: missing.append("API_HASH")
        if not cls.BOT_TOKEN: missing.append("BOT_TOKEN")
        if not cls.CHANNELS: missing.append("CHANNELS")

        if missing:
            print(f"[FATAL] Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
            print("[INFO] Please configure your .env file with your credentials and channel IDs.", file=sys.stderr)
            sys.exit(1)
