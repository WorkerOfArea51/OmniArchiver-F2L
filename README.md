<div align="center">

# ⚡ OmniArchiver F2L
### 🚀 High-Performance Telegram File-to-Link & Video Streaming Gateway

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/Mayuri-Chan/pyrofork"><img src="https://img.shields.io/badge/Pyrofork-MTProto%20v2.2-8A2BE2?style=for-the-badge&logo=telegram&logoColor=white" alt="Pyrofork"></a>
  <a href="https://docs.aiohttp.org/"><img src="https://img.shields.io/badge/aiohttp-Async%20Server-2C5BB4?style=for-the-badge&logo=aiohttp&logoColor=white" alt="aiohttp"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <b>A production-grade, low-latency Telegram MTProto streaming proxy built for extreme throughput and low memory.</b><br>
  Engineered specifically for media streaming apps (<b>StreamHub</b>, ExoPlayer, VLC, mpv, and Web browsers).
</p>

---

[Key Features](#-key-features) | [Architecture](#-system-architecture) | [Deploy to Alwaysdata](#-deploy-on-alwaysdata-free--unlimited-bandwidth) | [Docker Setup](#-docker--docker-compose-deployment) | [API Reference](#-rest-api--streaming-endpoints) | [License](#-license)

---

</div>

## 🌟 Highlights & Key Features

<table>
  <tr>
    <td width="50%">
      <h3>🚀 Multi-Client Worker Pooling</h3>
      Distributes MTProto chunk download streams across multiple auxiliary bot tokens (<code>MULTI_TOKENS</code>) to smash Telegram single-session bandwidth limits and achieve <b>20–30+ MB/s playback</b>.
    </td>
    <td width="50%">
      <h3>⏩ RFC 7233 Range Seeking</h3>
      Native <b>HTTP 206 Partial Content</b> handling allows instant scrub/seeking across timestamps without connection drops or buffer lag in ExoPlayer, VLC, and iOS/Android players.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🧠 In-Memory LRU Ring Buffer</h3>
      Caches media container header chunks (first 5MB & last 2MB) directly in memory, reducing video probing and startup delays to <b>0 ms</b>.
    </td>
    <td width="50%">
      <h3>💾 Ultra-Low RAM Footprint</h3>
      Direct generator chunk piping operates at <b>~60 MB – 90 MB RAM</b>, running flawlessly inside low-memory servers (like Alwaysdata's 256MB free tier).
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🗄️ Hybrid Database Layer</h3>
      Zero-configuration embedded <b>SQLite</b> (<code>omni_archiver.db</code>) with automatic fallback, plus plug-and-play <b>MongoDB</b> support for cloud scaling.
    </td>
    <td width="50%">
      <h3>🎬 Responsive Web Video Player</h3>
      Includes a built-in dark glassmorphic HTML5 web player powered by <b>Plyr.js</b> with picture-in-picture, speed control, and keyboard shortcuts.
    </td>
  </tr>
</table>

---

## 🏛️ System Architecture

```mermaid
graph LR
    User[📱 StreamHub App / ExoPlayer / VLC] -->|HTTP 206 Range Stream| WebServer[🌐 aiohttp Async Server]
    WebServer --> LRU[🧠 In-Memory LRU Cache]
    LRU -.->|Cache Miss| Pool[⚡ Multi-Client Pyrofork Pool]
    Pool -->|Parallel MTProto Chunks| TG[(☁️ Telegram DC Servers)]
    TG -->|Binary Stream| WebServer
    WebServer -->|Byte Chunks| User
```

---

## 📂 Project Tree

```
OmniArchiver-F2L/
├── bot/
│   ├── core/
│   │   ├── config.py           # Validated environment loader & URL generator
│   │   ├── client_pool.py      # Multi-session MTProto connection balancer
│   │   ├── database.py         # Async SQLite (omni_archiver.db) & MongoDB repository
│   │   ├── cache.py            # In-memory LRU ring buffer for 0ms header probing
│   │   └── file_properties.py  # Media metadata & MIME resolver
│   ├── server/
│   │   ├── routes.py           # HTTP endpoints (/stream, /dl, /watch, /api/v1/info)
│   │   ├── stream_handler.py   # RFC 7233 Range request & MTProto chunk streamer
│   │   ├── web_server.py       # aiohttp app factory with universal CORS
│   │   └── templates/          # Modern Plyr.js dark web player & status dashboard
│   ├── plugins/
│   │   ├── start.py            # /start, /help, /about, /ping handlers
│   │   ├── upload.py           # Channel auto-sync, file forwarding & link generator
│   │   └── admin.py            # /stats, /status, /ban, /unban, /del, /restart
│   ├── __init__.py
│   └── __main__.py             # Unified async orchestrator
├── main.py                     # Root entry point wrapper
├── requirements.txt            # Pyrofork, TgCrypto, aiohttp, aiosqlite, Motor
├── .env.example                # Environment configuration template
├── Dockerfile                  # Production container definition
├── docker-compose.yml          # One-click Docker deployment
├── Procfile                    # PaaS deployment runner
├── LICENSE                     # MIT License
└── README.md                   # Documentation
```

---

## 🚀 Quickstart & Deployment Guides

### 1️⃣ Deploy on Alwaysdata (Free & Unlimited Bandwidth)

Alwaysdata provides **1 GB SSD and unmetered bandwidth** without requiring a credit card:

1. In your **Alwaysdata Admin Dashboard** → **Web** → **Sites**:
   - **Type:** `Custom program`
   - **Command:** `python3 main.py`
   - **Working directory:** `/home/your_username/OmniArchiver-F2L`
2. Connect via SSH:
   ```bash
   ssh your_username@ssh-your_username.alwaysdata.net
   ```
3. Clone and install dependencies:
   ```bash
   git clone https://github.com/WorkerOfArea51/OmniArchiver-F2L.git
   cd OmniArchiver-F2L
   pip install -r requirements.txt
   ```
4. Create `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```
5. Restart your site from the dashboard—your streaming server is live at `https://your_username.alwaysdata.net`!

---

### 2️⃣ Docker / Docker Compose Deployment

```bash
# Clone the repository
git clone https://github.com/WorkerOfArea51/OmniArchiver-F2L.git
cd OmniArchiver-F2L

# Configure environment
cp .env.example .env
nano .env

# Run with Docker Compose
docker compose up -d --build
```

---

### 3️⃣ Linux VPS (Ubuntu / Debian)

```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies & fast C-crypto
pip install --upgrade pip
pip install -r requirements.txt

# Run
python3 main.py
```

---

## ⚙️ Environment Variables Reference

| Variable | Required | Description | Default |
| :--- | :---: | :--- | :--- |
| `API_ID` | **Yes** | Telegram API ID from [my.telegram.org](https://my.telegram.org) | — |
| `API_HASH` | **Yes** | Telegram API Hash from [my.telegram.org](https://my.telegram.org) | — |
| `BOT_TOKEN` | **Yes** | Primary Telegram Bot Token from [@BotFather](https://t.me/BotFather) | — |
| `BIN_CHANNEL_ID` | **Yes** | Storage Channel ID (must start with `-100`) | — |
| `MULTI_TOKENS` | *No* | Comma-separated auxiliary bot tokens for multi-worker parallel speed | `""` |
| `BASE_URL` | *No* | Public domain/host (e.g. `streamhub69.alwaysdata.net`) | `0.0.0.0:8080` |
| `PORT` | *No* | Internal web server port | `8080` |
| `BIND_ADDRESS` | *No* | Internal bind IP address | `0.0.0.0` |
| `OWNER_ID` | *No* | Numeric Telegram user ID for admin command authorization | `0` |
| `AUTH_USERS` | *No* | Comma-separated list of allowed user IDs (leave empty for public) | `""` |
| `DATABASE_URL` | *No* | MongoDB URI (leave empty to use embedded SQLite) | `""` |
| `CHUNK_SIZE` | *No* | MTProto streaming chunk size in bytes | `524288` (512 KB) |
| `CACHE_SIZE_MB` | *No* | Max in-memory LRU header cache in Megabytes | `32` |

---

## 📡 REST API & Streaming Endpoints

| Endpoint | Method | Description |
| :--- | :---: | :--- |
| `/stream/{id}` | `GET` | Raw binary stream with full **HTTP 206 Range seeking** (ExoPlayer/VLC/mpv) |
| `/watch/{id}` | `GET` | Embedded **Plyr.js** dark glassmorphic web player |
| `/dl/{id}` | `GET` | Direct attachment download link |
| `/api/v1/info/{id}` | `GET` | JSON metadata endpoint for **StreamHub** Android app integration |
| `/health` | `GET` | Uptime and active worker pool liveness monitor |

---

## 📜 Bot Commands

- `/start` — Launch the interactive bot control panel.
- `/help` — View available commands and usage guide.
- `/stats` — Real-time RAM, CPU, worker sessions, and indexed file statistics *(Admin)*.
- `/status` — Quick operational health check.
- `/ban <user_id>` — Ban a user from generating stream links *(Admin)*.
- `/unban <user_id>` — Unban a user *(Admin)*.
- `/del <msg_id>` — Delete a media file from the storage archive *(Admin)*.
- `/ping` — Measure bot latency and server response time.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

<div align="center">
  <sub>Built with ❤️ by <a href="https://github.com/WorkerOfArea51">MidNight Hawk (WorkerOfArea51)</a> for high-speed Telegram streaming.</sub>
</div>
