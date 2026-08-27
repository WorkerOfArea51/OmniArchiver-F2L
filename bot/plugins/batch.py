import os
import io
import asyncio
from secrets import token_hex
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot
from bot.config import Telegram, Server
from bot.database.files import save_batch
from bot.modules.decorators import verify_user, verify_admin
from bot.modules.parser import parse_telegram_link
from bot.modules.telegram import get_message, get_file_properties, is_media_message
from bot.modules.static import InvalidBatchUsageText, get_human_size

@TelegramBot.on_message(filters.command(['batch', 'batch_anime', 'batch_series']) & filters.private)
@verify_user
@verify_admin
async def batch_command(_, msg: Message):
    cmd = msg.command
    category = 'anime'
    start_link = None
    end_link = None

    if cmd[0] == 'batch_anime':
        category = 'anime'
        if len(cmd) >= 3:
            start_link, end_link = cmd[1], cmd[2]
    elif cmd[0] == 'batch_series':
        category = 'webseries'
        if len(cmd) >= 3:
            start_link, end_link = cmd[1], cmd[2]
    else:
        # /batch <category> <start> <end> OR /batch <start> <end>
        if len(cmd) == 4:
            cat_arg = cmd[1].lower()
            if cat_arg in ('anime', 'animes'):
                category = 'anime'
            elif cat_arg in ('series', 'webseries', 'tv'):
                category = 'webseries'
            elif cat_arg in ('movie', 'movies'):
                category = 'movies'
            else:
                category = 'anime'
            start_link, end_link = cmd[2], cmd[3]
        elif len(cmd) == 3:
            category = 'anime'
            start_link, end_link = cmd[1], cmd[2]
        else:
            return await msg.reply(InvalidBatchUsageText, quote=True)

    # Parse Telegram links
    parsed_start = parse_telegram_link(start_link)
    parsed_end = parse_telegram_link(end_link)

    if not parsed_start or not parsed_end:
        return await msg.reply("❌ Invalid start or end Telegram message link!", quote=True)

    chan_start, id_start = parsed_start
    chan_end, id_end = parsed_end

    if str(chan_start) != str(chan_end):
        return await msg.reply("❌ Both start and end links must belong to the **same channel**!", quote=True)

    channel_id = chan_start
    start_id = min(id_start, id_end)
    end_id = max(id_start, id_end)
    total_msgs = end_id - start_id + 1

    if total_msgs > 200:
        return await msg.reply("⚠️ Maximum batch limit is **200 messages** at once to prevent Telegram FloodWait.", quote=True)

    status_msg = await msg.reply(
        f"⏳ **Batch Indexing Started ({category.upper()})**\n\n"
        f"📍 Channel: `{channel_id}`\n"
        f"🔢 Range: `{start_id}` ➔ `{end_id}` ({total_msgs} messages)\n\n"
        f"Please wait...",
        quote=True
    )

    episodes_list = []
    numeric_chat_id = channel_id

    for idx, curr_id in enumerate(range(start_id, end_id + 1), start=1):
        try:
            target_msg = await get_message(channel_id, curr_id)
            if target_msg and is_media_message(target_msg):
                file_name, file_size, mime_type = get_file_properties(target_msg)
                numeric_chat_id = target_msg.chat.id if target_msg.chat else channel_id
                
                code = token_hex(Telegram.SECRET_CODE_LENGTH)
                dl_link = f"{Server.BASE_URL}/dl/{code}"
                stream_link = f"{Server.BASE_URL}/stream/{code}"

                episodes_list.append({
                    'code': code,
                    'message_id': curr_id,
                    'episode_num': len(episodes_list) + 1,
                    'file_name': file_name,
                    'file_size': file_size,
                    'mime_type': mime_type,
                    'dl_link': dl_link,
                    'stream_link': stream_link
                })

            # Update progress every 10 messages
            if idx % 10 == 0 or idx == total_msgs:
                try:
                    await status_msg.edit_text(
                        f"⏳ **Batch Indexing in Progress...**\n\n"
                        f"📁 Category: `{category.upper()}`\n"
                        f"🔄 Progress: `{idx}/{total_msgs}` messages scanned\n"
                        f"✅ Files Found: `{len(episodes_list)}`"
                    )
                except Exception:
                    pass

            await asyncio.sleep(0.3)  # Small delay to avoid FloodWait

        except Exception:
            continue

    if not episodes_list:
        return await status_msg.edit_text("❌ No media files were found in the specified range.")

    # Save the entire batch as a SINGLE unified document in MongoDB
    batch_doc = await save_batch(
        channel_id=numeric_chat_id,
        start_id=start_id,
        end_id=end_id,
        category=category,
        user_id=msg.from_user.id,
        episodes=episodes_list
    )

    # Use the episodes from batch_doc in case it was already indexed
    final_episodes = batch_doc.get('episodes', episodes_list)

    # Format output with quote blocks directly in Telegram chat
    message_chunks = []
    current_chunk = (
        f"✅ **Batch Indexing Completed!**\n\n"
        f"📁 **Category:** `{category.upper()}`\n"
        f"📦 **Total Episodes:** `{len(final_episodes)}`\n"
        f"🗄️ **Saved as 1 Unified Batch Document in MongoDB**\n\n"
    )

    for item in final_episodes:
        human_size = get_human_size(item['file_size'])
        code = item['code']
        dl_link = f"{Server.BASE_URL}/dl/{code}"
        stream_link = f"{Server.BASE_URL}/stream/{code}"
        
        entry = (
            f"🎬 **{item['file_name']}** `({human_size})`\n"
            f"> ▶️ [Stream Link]({stream_link})\n"
            f"> 📥 [Download Link]({dl_link})\n\n"
        )

        # Telegram message limit is 4096 chars; split if approaching limit
        if len(current_chunk) + len(entry) > 3800:
            message_chunks.append(current_chunk)
            current_chunk = entry
        else:
            current_chunk += entry

    if current_chunk.strip():
        message_chunks.append(current_chunk)

    # Edit the initial status message with the first batch chunk
    await status_msg.edit_text(message_chunks[0], disable_web_page_preview=True)

    # If there are additional chunks (for large batches), send as follow-up messages
    for follow_up in message_chunks[1:]:
        await msg.reply(follow_up, quote=False, disable_web_page_preview=True)
        await asyncio.sleep(0.5)

    # Build and send text file list as backup
    txt_content = f"=== OmniArchiver Batch Links ({category.upper()}) ===\nTotal Files: {len(final_episodes)}\n\n"
    for item in final_episodes:
        human_size = get_human_size(item['file_size'])
        code = item['code']
        dl_link = f"{Server.BASE_URL}/dl/{code}"
        stream_link = f"{Server.BASE_URL}/stream/{code}"
        txt_content += (
            f"File: {item['file_name']} ({human_size})\n"
            f"Stream: {stream_link}\n"
            f"Download: {dl_link}\n"
            f"{'-'*50}\n"
        )

    file_bytes = io.BytesIO(txt_content.encode('utf-8'))
    file_bytes.name = f"batch_{category}_{start_id}_to_{end_id}.txt"
    
    await msg.reply_document(
        document=file_bytes,
        caption=f"📁 **Batch Text List** ({category.upper()}) - `{len(final_episodes)} files`",
        quote=False
    )
