<div align="center">

# ? OmniArchiver F2L
### High-Performance Telegram File-to-Link & Video Streaming Gateway

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Pyrofork](https://img.shields.io/badge/Pyrofork-MTProto%20v2.2-purple.svg)](https://github.com/Mayuri-Chan/pyrofork)
[![aiohttp](https://img.shields.io/badge/aiohttp-Async%20Server-green.svg)](https://docs.aiohttp.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**OmniArchiver F2L** is a production-grade Telegram File-to-Link (F2L) and Video Streaming Bot built for maximum throughput, low latency, and low memory consumption. It acts as an ultra-fast streaming proxy between Telegram MTProto servers and client media players.

</div>

---

## ? Key Features

- **?? Multi-Client Worker Pooling (`MULTI_TOKENS`):** Distributes MTProto chunk download streams across multiple Telegram bot sessions to bypass Telegram's single-connection bandwidth limits and achieve 20–30+ MB/s playback.
- **? RFC 7233 HTTP 206 Partial Content (Range Seeking):** Full support for instant video scrub/seeking across timestamps without connection drops in **StreamHub, ExoPlayer, VLC, mpv, iOS, and Web players**.
- **?? In-Memory LRU Ring Buffer:** Caches initial metadata header chunks (first 5MB & last 2MB) so video probing and playback starts in **0 ms**.
- **?? Low-Memory Footprint:** Operates under **~60–90 MB RAM**, making it run flawlessly even on low-spec hosting tiers (like Alwaysdata's 256MB free plan).
- **??? Pluggable Database (SQLite + MongoDB):** Uses zero-config async SQLite (`omni_archiver.db`) out-of-the-box, with optional seamless MongoDB (`motor`) support for distributed clustering.
- **?? Responsive Web Player:** Built-in dark UI web player powered by **Plyr.js** with fullscreen, picture-in-picture, speed control, and keyboard shortcuts.
- **?? RESTful JSON API:** Clean metadata API (`/api/v1/info/{id}`) for frontend integration into custom streaming apps.

---

## ??? Project Architecture

```
OmniArchiver-F2L/
+-- bot/
¦   +-- core/
¦   ¦   +-- config.py           # Validated environment loader
¦   ¦   +-- client_pool.py      # Multi-session MTProto load balancer
¦   ¦   +-- database.py         # Async SQLite & MongoDB repository
¦   ¦   +-- cache.py            # In-memory LRU ring buffer
¦   ¦   +-- file_properties.py  # Media metadata & MIME resolver
¦   +-- server/
¦   ¦   +-- routes.py           # HTTP endpoints & API routes
¦   ¦   +-- stream_handler.py   # Range request & chunk streamer engine
¦   ¦   +-- web_server.py       # aiohttp app factory with CORS
¦   ¦   +-- templates/          # Modern Plyr.js web player & status dashboard
¦   +-- plugins/
¦   ¦   +-- start.py            # /start, /help, /about, /ping handlers
¦   ¦   +-- upload.py           # Forwarding, storage channel sync & link gen
¦   ¦   +-- admin.py            # /stats, /status, /ban, /unban, /del, /restart
¦   +-- __init__.py
¦   +-- __main__.py             # Unified async orchestrator
+-- main.py                     # Entry point wrapper
+-- requirements.txt            # Python dependencies
+-- .env.example                # Environment configuration template
+-- Dockerfile                  # Production container definition
+-- docker-compose.yml          # One-click Docker deployment
+-- README.md
```

---

## ?? Quick Deployment Guides

### 1. Deploying on Alwaysdata (Free 1GB / Unlimited Bandwidth)

1. Go to your **Alwaysdata Admin Dashboard** $\rightarrow$ **`Web`** $\rightarrow$ **`Sites`**.
2. Edit your site:
   - **Type:** `Custom program`
   - **Command:** `python3 main.py`
   - **Working directory:** `/home/your_username/OmniArchiver-F2L`
3. Connect via SSH to your Alwaysdata account:
   ```bash
   ssh your_username@ssh-your_username.alwaysdata.net
   git clone <YOUR_REPO_URL> OmniArchiver-F2L
   cd OmniArchiver-F2L
   pip install -r requirements.txt
   cp .env.example .env
   nano .env  # Fill in your API_ID, API_HASH, BOT_TOKEN, BIN_CHANNEL_ID, BASE_URL
   ```
4. Restart your site from the dashboard—your streaming gateway is live!

---

### 2. Deploying with Docker / Docker Compose

1. Clone the repository and navigate into the folder:
   ```bash
   git clone <YOUR_REPO_URL> OmniArchiver-F2L
   cd OmniArchiver-F2L
   ```
2. Copy and configure your `.env` file:
   ```bash
   cp .env.example .env
   nano .env
   ```
3. Start the container:
   ```bash
   docker compose up -d --build
   ```

---

### 3. Deploying on Linux VPS (Ubuntu / Debian)

```bash
# 1. Clone repo
git clone <YOUR_REPO_URL> OmniArchiver-F2L
cd OmniArchiver-F2L

# 2. Setup Virtual Environment
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 3. Configure .env
cp .env.example .env
nano .env

# 4. Run with PM2 or systemd
python3 main.py
```

---

## ?? Environment Variables Reference

| Variable | Required | Description | Default |
| :--- | :---: | :--- | :--- |
| `API_ID` | **Yes** | Telegram API ID from [my.telegram.org](https://my.telegram.org) | — |
| `API_HASH` | **Yes** | Telegram API Hash from [my.telegram.org](https://my.telegram.org) | — |
| `BOT_TOKEN` | **Yes** | Primary Telegram Bot Token from [@BotFather](https://t.me/BotFather) | — |
| `BIN_CHANNEL_ID` | **Yes** | Storage Channel ID (must start with `-100`) | — |
| `MULTI_TOKENS` | *No* | Comma-separated auxiliary bot tokens for multi-part worker speed | `""` |
| `BASE_URL` | *No* | Public domain/host (e.g. `streamhub69.alwaysdata.net`) | `0.0.0.0:8080` |
| `PORT` | *No* | Internal web server port | `8080` |
| `BIND_ADDRESS` | *No* | Internal bind IP address | `0.0.0.0` |
| `OWNER_ID` | *No* | Telegram user ID for admin command authorization | `0` |
| `AUTH_USERS` | *No* | Comma-separated list of allowed user IDs (leave empty for public) | `""` |
| `DATABASE_URL` | *No* | MongoDB URI (leaves empty to use embedded SQLite) | `""` |
| `CHUNK_SIZE` | *No* | MTProto streaming chunk size in bytes | `524288` (512 KB) |
| `CACHE_SIZE_MB` | *No* | Max in-memory LRU header cache in Megabytes | `32` |

---

## ?? REST API & Streaming Endpoints

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/stream/{message_id}` | `GET` | Raw binary stream with full HTTP 206 Range seeking support |
| `/dl/{message_id}` | `GET` | Direct attachment download link |
| `/watch/{message_id}` | `GET` | Embedded HTML5 Plyr.js responsive video player |
| `/api/v1/info/{message_id}` | `GET` | JSON metadata endpoint for StreamHub app integration |
| `/health` | `GET` | Liveness health check endpoint |

---

## ?? License

Distributed under the **MIT License**.
