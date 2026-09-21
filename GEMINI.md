# OmniArchiver-F2L — Memory, Architecture & Workflow Rules

This document serves as the permanent memory and architectural reference for **OmniArchiver-F2L**.

---

## 1. Project Overview & Owner Context
* **Owner:** MidNight Hawk (Personal bot, single admin/owner).
* **Purpose:** High-performance Telegram File-to-Link (F2L) streaming server and media indexer powering the **StreamHub Android App** and browser Web Player.
* **Server Host:** Serv00 VPS (FreeBSD) at `https://midnighthawk.serv00.net`.
* **Database:** MongoDB Atlas (collections: `movies`, `anime`, `webseries`, `direct_files`, `deletion_queue`).
* **Framework:** Python Hydrogram (Pyrogram v2 fork) + Quart ASGI Web Server + Uvicorn.

---

## 2. The Exact Media & API Workflow (CRITICAL MEMORY)
The owner and StreamHub app operate on a **per-title / per-release indexing model** (NOT a giant catalog feed):

### A. Movies / Single Files:
1. User posts or forwards the file in their private channel.
2. User sends:
   ```
   /link <channel_message_link>
   ```
3. The bot indexes the file into MongoDB `movies` collection and outputs the **Single-File API**:
   ```
   https://midnighthawk.serv00.net/api/file/<file_code>
   ```
4. StreamHub uses this JSON endpoint to retrieve title, duration, formatted size, and stream/download URLs.

### B. Anime & Web Series (Multi-Episode Batches):
1. User posts episodes sequentially in their private channel.
2. User sends:
   ```
   /batch <start_channel_link> <end_channel_link>
   # Or with explicit category / custom title:
   /batch anime <start_link> <end_link> [Custom Title]
   /batch series <start_link> <end_link> [Custom Title]
   ```
3. The bot indexes all episodes into MongoDB `anime` or `webseries` collection and outputs the **Batch API**:
   ```
   https://midnighthawk.serv00.net/api/batch/<batch_id>
   ```
4. StreamHub uses this JSON endpoint to render the complete episode list (`EP 01`, `EP 02`, etc.) with individual stream URLs, durations, and sizes.

---

## 3. Server & Memory Constraints (Serv00 FreeBSD)
* **Hard Memory Limit:** **512 MB RAM** per account. If breached, the FreeBSD kernel terminates the process with `SIGKILL`.
* **RAM Management (`bot/modules/memory.py`):**
  - Uses FreeBSD `libc.mallctl(b"arenas.purge", None, None, None, 0)` to release unused heap pages back to the OS.
  - Calls `gc.collect()` and `flush_ram()` after each streaming session finishes.
  - Chunks are yielded on the fly (`1 MB` MTProto slices) with immediate `del chunk`.

---

## 4. MTProto Multi-Bot Streaming Architecture
* **Worker Pool (`bot/clients.py`):**
  - Rotates auxiliary bot tokens from `MULTI_BOT_TOKENS` (`worker_1`, `worker_2`, etc.) via round-robin to avoid Telegram DC rate limits and distribute bandwidth across multiple streaming clients.
* **Cryptographic Session Rule (DO NOT BREAK):**
  - In MTProto, `file_reference` is cryptographically bound to the bot session that queried the message.
  - The streaming worker bot **must fetch the message itself** (`get_message(..., client=worker)`).
  - Cache entries in `_MESSAGE_CACHE` must always be scoped per client: `(client_name, chat_id, message_id)`.
  - **Auto-Recovery on Chunk 0:** If chunk 0 fails with `FileReferenceExpired` or invalid token, the server catches the exception, force-refreshes the message directly from Telegram (`get_message(..., client=TelegramBot, force_refresh=True)`), and retries via `TelegramBot` without closing the client socket.

---

## 5. Web Player 2.0 (`bot/server/templates/player.html`)
* **Cinema Dark Glassmorphism UI:** Displays clean file name, size badge, and duration pill.
* **External Players:**
  - 🟠 **VLC Player:** Launches via Android Intent (`intent:...#Intent;package=org.videolan.vlc;type=video/*;end`) or universal `vlc://`.
  - 🔵 **MX Player:** Launches via Android Intent (`intent:...#Intent;package=com.mxtech.videoplayer.ad;type=video/*;end`).
  - 📋 **Copy Stream Link:** Direct clipboard copy with animated toast notification.
  - 📥 **Download:** Direct download link.
* **Smart Resume:** Stores playback timestamps in browser `localStorage` and displays a floating prompt to resume playback upon reopening.

---

## 6. Admin Commands & Tools (`bot/plugins/admin.py`)
* `/purge [count]` (or reply with `/purge`):
  - Bi-directional safety (`min()` / `max()`).
  - 100-chunk batching with 1s pacing delay.
  - Native `FloodWait` auto-pause & resume.
  - 48-hour Telegram limit fallback (deletes bot messages individually if bulk fails).
  - 100% self-cleaning (deletes command, status, and confirmation).
* `/backup`: Creates a gzipped `.json.gz` snapshot of all collections and sends it via Telegram DM.
* `/restore`: Reply to any `.json.gz` or `.json` backup file to safely restore and upsert all collections into MongoDB.
* `/clean`: Manually triggers garbage collection, arena purge, and RAM compaction.
* `/sync_duration`: Scans MongoDB records and backfills exact durations from channel messages.
* `/revoke <code>`: Revokes/deletes an existing file link or whole batch from the database.
* `/sh <cmd>`: Executes shell commands on Serv00 (e.g. `/sh git pull origin main`).
* `/restart`: Reboots the Python bot and web server cleanly.

---

## 7. Deployment Policy
* Repository: `https://github.com/WorkerOfArea51/OmniArchiver-F2L.git` on branch `main`.
* When updates are pushed, the live Serv00 server is updated via Telegram:
  1. `/sh git pull origin main`
  2. `/restart`
