from os import environ as env

class Telegram:
    API_ID = int(env.get("TELEGRAM_API_ID", env.get("API_ID", 12345)))
    API_HASH = env.get("TELEGRAM_API_HASH", env.get("API_HASH", "xyz"))
    
    # Primary Bot
    BOT_TOKEN = env.get("TELEGRAM_BOT_TOKEN", env.get("BOT_TOKEN", "1234567:xyz"))
    BOT_USERNAME = env.get("TELEGRAM_BOT_USERNAME", env.get("BOT_USERNAME", "BotFather"))
    
    # Multi-client worker tokens (comma, space, or newline separated)
    _raw_multi_tokens = env.get("MULTI_BOT_TOKENS", env.get("BOT_TOKENS", ""))
    MULTI_BOT_TOKENS = [
        tok.strip() for tok in _raw_multi_tokens.replace(",", " ").split() if tok.strip()
    ]
    # Worker pool combining primary + worker tokens (preserving order, removing duplicates)
    WORKER_TOKENS = list(dict.fromkeys([BOT_TOKEN] + MULTI_BOT_TOKENS)) if MULTI_BOT_TOKENS else [BOT_TOKEN]

    # Owner & Auth/Admin Users
    OWNER_ID = int(env.get("OWNER_ID", 5530237028))
    _raw_auth_users = env.get("AUTH_USERS", "")
    AUTH_USERS = [
        int(uid.strip()) for uid in _raw_auth_users.replace(",", " ").split() if uid.strip().lstrip("-").isdigit()
    ]
    ADMIN_IDS = set([OWNER_ID] + AUTH_USERS)

    # Allowed Users for general usage (empty = everyone allowed)
    ALLOWED_USER_IDS = env.get("ALLOWED_USER_IDS", "").split()
    
    # Storage / Bin Channel ID (for direct user file uploads in DM)
    CHANNEL_ID = int(env.get("TELEGRAM_CHANNEL_ID", env.get("CHANNEL_ID", env.get("BIN_CHANNEL_ID", -100123456789))))
    SECRET_CODE_LENGTH = int(env.get("SECRET_CODE_LENGTH", 24))

class Database:
    DATABASE_URL = env.get("DATABASE_URL", env.get("MONGODB_URI", "mongodb://localhost:27017"))
    DATABASE_NAME = env.get("DATABASE_NAME", "OmniArchiver")

class Server:
    BASE_URL = env.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    BIND_ADDRESS = env.get("BIND_ADDRESS", env.get("IP", "0.0.0.0"))
    PORT = int(env.get("PORT", 8080))

# LOGGING CONFIGURATION
LOGGER_CONFIG_JSON = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '[%(asctime)s][%(name)s][%(levelname)s] -> %(message)s',
            'datefmt': '%d/%m/%Y %H:%M:%S'
        },
    },
    'handlers': {
        'file_handler': {
            'class': 'logging.FileHandler',
            'filename': 'event-log.txt',
            'formatter': 'default'
        },
        'stream_handler': {
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        }
    },
    'loggers': {
        'uvicorn': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        },
        'uvicorn.error': {
            'level': 'WARNING',
            'handlers': ['file_handler', 'stream_handler']
        },
        'bot': {
            'level': 'INFO',
            'handlers': ['file_handler', 'stream_handler']
        },
        'hydrogram': {
            'level': 'WARNING',
            'handlers': ['file_handler', 'stream_handler']
        }
    }
}
