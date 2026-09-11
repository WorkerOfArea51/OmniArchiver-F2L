import os
import sys
import io
import asyncio
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot
from bot.modules.decorators import verify_user, verify_admin

@TelegramBot.on_message(filters.command(['sh', 'shell', 'exec']) & filters.private)
@verify_user
@verify_admin
async def shell_command(_, msg: Message):
    """Executes a terminal shell command directly from Telegram and returns the output."""
    if len(msg.command) < 2:
        return await msg.reply(
            "💻 **Shell Terminal Command**\n\n"
            "**Usage:**\n"
            "• `/sh git pull origin main`\n"
            "• `/sh pip install -r requirements.txt`\n"
            "• `/sh ls -la`",
            quote=True
        )

    cmd = msg.text.split(maxsplit=1)[1]
    status_msg = await msg.reply(f"⏳ **Executing:** `{cmd}`", quote=True)

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
        output = (stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')).strip()

        if not output:
            output = "Command finished with exit code 0 (no output)."

        if len(output) > 3800:
            file_bytes = io.BytesIO(output.encode('utf-8'))
            file_bytes.name = "output.txt"
            await status_msg.delete()
            await msg.reply_document(
                document=file_bytes,
                caption=f"📄 **Output for:** `{cmd[:60]}`",
                quote=True
            )
        else:
            await status_msg.edit_text(f"💻 **Output:**\n```bash\n{output}\n```")

    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ **Execution Timed Out** (limit: 120 seconds).")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error executing command:** `{e}`")

@TelegramBot.on_message(filters.command(['restart', 'reboot']) & filters.private)
@verify_user
@verify_admin
async def restart_command(_, msg: Message):
    """Restarts the bot process smoothly and notifies user upon coming back online."""
    import time
    restart_msg = await msg.reply("🔄 **Restarting OmniArchiver Bot...**\nPlease wait ~5-10 seconds.", quote=True)

    # Save state to edit message after reboot
    try:
        with open('.restart_state.txt', 'w') as f:
            f.write(f"{msg.chat.id} {restart_msg.id} {time.time()}")
    except Exception:
        pass

    # Touch start.sh to update timestamp if present
    try:
        if os.path.exists("start.sh"):
            os.utime("start.sh", None)
    except Exception:
        pass

    await asyncio.sleep(1.5)

    # Replace current python process
    os.execl(sys.executable, sys.executable, "-m", "bot")

@TelegramBot.on_message(filters.command(['purge', 'clear']) & (filters.private | filters.group))
@verify_user
@verify_admin
async def purge_command(client, msg: Message):
    """Purges messages from the chat with fallback for Telegram's 48h limit."""
    if msg.reply_to_message:
        start_id = msg.reply_to_message.id
        end_id = msg.id
        message_ids = list(range(start_id, end_id + 1))
    elif len(msg.command) > 1 and msg.command[1].isdigit():
        count = min(int(msg.command[1]), 100)
        message_ids = list(range(msg.id - count, msg.id + 1))
    else:
        return await msg.reply(
            "🧹 **Purge Usage:**\n"
            "• Reply to a message with `/purge` to delete everything from that message downwards.\n"
            "• Send `/purge 20` to delete the last 20 messages.\n\n"
            "ℹ️ **Telegram Limitation:** Telegram API strictly forbids bots from deleting user messages older than 48 hours. To wipe older chat history completely, use Telegram's **Clear History** feature.",
            quote=True
        )

    deleted_count = 0
    # Try batch delete in chunks of 100
    for i in range(0, len(message_ids), 100):
        chunk = message_ids[i:i + 100]
        try:
            await client.delete_messages(chat_id=msg.chat.id, message_ids=chunk)
            deleted_count += len(chunk)
        except Exception:
            # If batch delete fails (e.g. contains user messages > 48 hours old),
            # delete individually so bot's own messages still get deleted!
            for mid in chunk:
                try:
                    await client.delete_messages(chat_id=msg.chat.id, message_ids=[mid])
                    deleted_count += 1
                except Exception:
                    pass

    status = await client.send_message(
        chat_id=msg.chat.id,
        text=(
            f"🧹 **Purge Complete!** Deleted `{deleted_count}` messages.\n\n"
            f"ℹ️ *Note: Telegram does not allow bots to delete user messages older than 48 hours. "
            f"To delete everything including old messages, use Telegram's **Clear History** option.*"
        )
    )
    await asyncio.sleep(4)
    try:
        await status.delete()
    except Exception:
        pass

@TelegramBot.on_message(filters.command(['clean', 'gc', 'flush']) & filters.private)
@verify_user
@verify_admin
async def clean_memory_command(_, msg: Message):
    """Manually cleans memory, runs cyclic garbage collection and releases freed heap back to OS."""
    import psutil
    from bot.modules.memory import flush_ram
    from bot.modules.static import get_human_size

    before_ram = psutil.Process(os.getpid()).memory_info().rss
    flush_ram()
    after_ram = psutil.Process(os.getpid()).memory_info().rss

    freed = before_ram - after_ram
    freed_str = get_human_size(max(0, freed))
    current_str = get_human_size(after_ram)

    await msg.reply(
        f"🧹 **RAM Cleaned & Compaction Finished!**\n\n"
        f"📉 **Freed Memory:** `{freed_str}`\n"
        f"🧠 **Current Bot Process RAM:** `{current_str}`",
        quote=True
    )

@TelegramBot.on_message(filters.command(['sync_duration', 'backfill', 'sync_metadata']) & filters.private)
@verify_user
@verify_admin
async def sync_duration_command(_, msg: Message):
    """Automatically scans all existing files/batches in MongoDB and backfills exact duration."""
    from bot.database import db
    from bot.modules.telegram import get_message, get_file_properties

    status = await msg.reply("⏳ **Syncing duration for all existing database records...**\nPlease wait...", quote=True)
    synced_files = 0
    synced_batches = 0

    try:
        # 1. Sync movies and direct files
        for col in (db.movies, db.direct_files):
            if col is not None:
                async for doc in col.find({'duration': {'$in': [None, 0, '']}}):
                    chan_id = doc.get('channel_id')
                    msg_id = doc.get('message_id')
                    if chan_id and msg_id:
                        try:
                            t_msg = await get_message(chan_id, msg_id)
                            if t_msg:
                                _, _, _, dur, dur_fmt = get_file_properties(t_msg)
                                await col.update_one(
                                    {'_id': doc['_id']},
                                    {'$set': {'duration': dur, 'duration_formatted': dur_fmt}}
                                )
                                synced_files += 1
                        except Exception:
                            pass
                    await asyncio.sleep(0.1)

        # 2. Sync anime and webseries batches
        for col in (db.anime, db.webseries):
            if col is not None:
                async for batch_doc in col.find():
                    chan_id = batch_doc.get('channel_id')
                    episodes = batch_doc.get('episodes', [])
                    updated = False

                    for ep in episodes:
                        if not ep.get('duration'):
                            msg_id = ep.get('message_id')
                            if chan_id and msg_id:
                                try:
                                    t_msg = await get_message(chan_id, msg_id)
                                    if t_msg:
                                        _, _, _, dur, dur_fmt = get_file_properties(t_msg)
                                        ep['duration'] = dur
                                        ep['duration_formatted'] = dur_fmt
                                        updated = True
                                        synced_files += 1
                                except Exception:
                                    pass
                                await asyncio.sleep(0.1)

                    if updated:
                        await col.update_one(
                            {'_id': batch_doc['_id']},
                            {'$set': {'episodes': episodes}}
                        )
                        synced_batches += 1

        await status.edit_text(
            f"✅ **Duration Backfill Completed Successfully!**\n\n"
            f"🎬 **Total Episodes/Files Updated:** `{synced_files}`\n"
            f"📁 **Batches Updated:** `{synced_batches}`\n\n"
            f"All your existing MongoDB records and REST API endpoints now include exact durations! ⏱️"
        )
    except Exception as e:
        await status.edit_text(f"❌ Error during sync: `{e}`")

@TelegramBot.on_message(filters.command(['revoke', 'del', 'delete_link', 'rm']) & filters.private)
@verify_user
@verify_admin
async def revoke_command(_, msg: Message):
    """Revokes an existing file link or batch from MongoDB so it can be re-indexed cleanly."""
    from bot.config import Server
    from bot.database.files import get_file, delete_file

    if len(msg.command) < 2:
        return await msg.reply(
            "🗑️ **Revoke / Delete Link Command**\n\n"
            "**Usage for Single Files:**\n"
            "• `/revoke <file_code>`\n"
            f"• `/revoke {Server.BASE_URL}/dl/<file_code>`\n"
            f"• `/revoke {Server.BASE_URL}/stream/<file_code>`\n\n"
            "**Usage for Whole Batches (Anime / Series):**\n"
            "• `/revoke <batch_id>`\n"
            f"• `/revoke {Server.BASE_URL}/api/batch/<batch_id>`\n\n"
            "*(You can also simply click the `[🗑️ Revoke]` button under any link card)*",
            quote=True
        )

    raw_input = msg.command[1].strip()
    # Extract code/id from URL if full URL is pasted
    code = raw_input.rstrip('/').split('/')[-1].strip()

    doc = await get_file(code)
    if not doc:
        return await msg.reply("❌ Record not found in database or was already revoked.", quote=True)

    file_title = doc.get('title') or doc.get('file_name', 'N/A')
    episodes = doc.get('episodes')
    await delete_file(code)

    if episodes is not None:
        batch_info = f"📦 **Type:** `Entire Batch ({len(episodes)} episodes removed)`\n"
    elif doc.get('batch_id'):
        batch_info = "🎬 **Type:** `Single episode removed from batch`\n"
    else:
        batch_info = "🎬 **Type:** `Single Movie / Direct File`\n"

    await msg.reply(
        f"🗑️ **Revoked Successfully!**\n\n"
        f"🎬 **Title:** `{file_title}`\n"
        f"🔑 **Code / ID:** `{code}`\n"
        f"{batch_info}\n"
        f"✨ Database record has been cleared cleanly. You can now re-index anytime!",
        quote=True
    )

@TelegramBot.on_message(filters.command(['backup', 'db_dump', 'dump_db']) & filters.private)
@verify_user
@verify_admin
async def backup_database_command(client, msg: Message):
    """Creates a compressed full JSON backup of the MongoDB database and sends it directly via Telegram DM."""
    import json
    import gzip
    from datetime import datetime
    from bot.database import db
    from bot.modules.static import get_human_size

    status = await msg.reply("📦 **Generating database backup...**\nReading collections...", quote=True)

    try:
        backup_data = {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "version": "1.0",
                "database_name": db.db.name if db.db is not None else "OmniArchiver"
            },
            "collections": {}
        }

        total_records = 0
        summary_lines = []

        for name, col in (
            ("movies", db.movies),
            ("anime", db.anime),
            ("webseries", db.webseries),
            ("direct_files", db.direct_files),
        ):
            if col is not None:
                docs = []
                async for doc in col.find():
                    doc_copy = {}
                    for k, v in doc.items():
                        if isinstance(v, datetime):
                            doc_copy[k] = v.isoformat()
                        else:
                            doc_copy[k] = v
                    docs.append(doc_copy)

                backup_data["collections"][name] = docs
                count = len(docs)
                total_records += count
                summary_lines.append(f"• **{name.capitalize()}**: `{count}` documents")

        # Serialize to JSON and compress with gzip
        json_str = json.dumps(backup_data, ensure_ascii=False, indent=2)
        json_bytes = json_str.encode('utf-8')
        raw_size = get_human_size(len(json_bytes))

        gz_buf = io.BytesIO()
        with gzip.GzipFile(fileobj=gz_buf, mode='wb', compresslevel=9) as gz_file:
            gz_file.write(json_bytes)
        gz_buf.seek(0)
        gz_size = get_human_size(len(gz_buf.getvalue()))

        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        file_name = f"OmniArchiver_Backup_{timestamp_str}.json.gz"
        gz_buf.name = file_name

        caption = (
            f"📦 **OmniArchiver MongoDB Backup**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 **Date:** `{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}`\n"
            f"📊 **Total Records:** `{total_records}`\n"
            + "\n".join(summary_lines) + "\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💾 **File Size:** `{gz_size}` *(uncompressed: {raw_size})*\n"
            f"🔒 Keep this backup safe in your Telegram Saved Messages!"
        )

        await status.delete()
        await client.send_document(
            chat_id=msg.chat.id,
            document=gz_buf,
            file_name=file_name,
            caption=caption
        )
    except Exception as e:
        await status.edit_text(f"❌ **Failed to create database backup:** `{e}`")

