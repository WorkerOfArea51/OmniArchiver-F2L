# -*- coding: utf-8 -*-
# Thunder/vars.py - OmniArchiver F2L Configuration

import os
from typing import Set, List, Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
    load_dotenv("config.env")
except ImportError:
    pass
from Thunder.utils.logger import logger

def str_to_bool(val: str) -> bool:
    return str(val).lower() in ("true", "1", "t", "y", "yes")

def parse_int_list(val: str) -> List[int]:
    if not val:
        return []
    res = []
    for x in str(val).replace(",", " ").split():
        x = x.strip()
        if x.lstrip("-").isdigit():
            res.append(int(x))
    return res

class Var:
    # --- Telegram Credentials ---
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "").strip()
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    @classmethod
    def validate(cls):
        if not all([cls.API_ID, cls.API_HASH, cls.BOT_TOKEN]):
            logger.critical("Missing required Telegram API configuration (API_ID, API_HASH, BOT_TOKEN)")
            raise ValueError("Missing required Telegram API configuration")

    NAME: str = os.getenv("NAME", "OmniArchiver-F2L")
    SLEEP_THRESHOLD: int = int(os.getenv("SLEEP_THRESHOLD", "60"))
    WORKERS: int = int(os.getenv("WORKERS", "6"))

    # Multi-client worker pool tokens
    raw_multi_tokens = os.getenv("MULTI_TOKENS", "").strip()
    MULTI_TOKENS: List[str] = [t.strip() for t in raw_multi_tokens.split(",") if t.strip()]

    # Multiple Storage Channels (Anime, Movies, Series)
    raw_channels = os.getenv("CHANNELS", "").strip()
    CHANNELS: List[int] = parse_int_list(raw_channels)

    BIN_CHANNEL: int = int(os.getenv("BIN_CHANNEL", os.getenv("BIN_CHANNEL_ID", "0")))
    if BIN_CHANNEL and BIN_CHANNEL not in CHANNELS:
        CHANNELS.append(BIN_CHANNEL)
    if not BIN_CHANNEL and CHANNELS:
        BIN_CHANNEL = CHANNELS[0]

    # --- Server Settings ---
    PORT: int = int(os.getenv("PORT", "8100"))
    BIND_ADDRESS: str = os.getenv("IP") or os.getenv("BIND_ADDRESS") or "0.0.0.0"
    NO_PORT: bool = str_to_bool(os.getenv("NO_PORT", "True"))

    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    raw_auth = os.getenv("AUTH_USERS", "").strip()
    AUTH_USERS: List[int] = parse_int_list(raw_auth)
    if OWNER_ID and OWNER_ID not in AUTH_USERS:
        AUTH_USERS.append(OWNER_ID)

    FQDN: str = os.getenv("FQDN", os.getenv("BASE_URL", "")).strip().replace("https://", "").replace("http://", "").rstrip("/")
    if not FQDN:
        FQDN = f"{BIND_ADDRESS}:{PORT}"
    HAS_SSL: bool = str_to_bool(os.getenv("HAS_SSL", "True"))
    PROTOCOL: str = "https" if HAS_SSL else "http"
    PORT_SEGMENT: str = "" if NO_PORT else f":{PORT}"
    URL: str = f"{PROTOCOL}://{FQDN}{PORT_SEGMENT}/".rstrip("/") + "/"
    BASE_URL: str = URL.rstrip("/")

    # --- Database ---
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()
    SQLITE_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "omni_archiver.db")

    MULTI_CLIENT: bool = len(MULTI_TOKENS) > 0
    MAX_BATCH_FILES: int = int(os.getenv("MAX_BATCH_FILES", "100"))
    WORKDIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
