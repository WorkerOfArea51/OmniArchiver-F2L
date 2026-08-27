import os
import io
import asyncio
from hydrogram import filters
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot.clients import TelegramBot
from bot.config import Server
from bot.database.files import save_file
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

    indexed_items = []
    numeric_chat_id = channel_id

    for idx, curr_id in enumerate(range(start_id, end_id + 1), start=1):
        try:
            target_msg = await get_message(channel_id, curr_id)
            if target_msg and is_media_message(target_msg):
                file_name, file_size, mime_type = get_file_properties(target_msg)
                numeric_chat_id = target_msg.chat.id if target_msg.chat else channel_id
                
                doc = await save_file(
                    channel_id=numeric_chat_id,
                    message_id=curr_id,
                    file_name=file_name,
                    file_size=file_size,
                    mime_type=mime_type,
                    user_id=msg.from_user.id,
                    category=category,
                    episode=len(indexed_items) + 1
                )
                
                code = doc['code']
                dl_link = f"{Server.BASE_URL}/dl/{code}"
                stream_link = f"{Server.BASE_URL}/stream/{code}"
                
                indexed_items.append({
                    'message_id': curr_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'dl_link': dl_link,
                    'stream_link': stream_link,
                    'code': code
                })

            # Update progress every 10 messages
            if idx % 10 == 0 or idx == total_msgs:
                try:
                    await status_msg.edit_text(
                        f"⏳ **Batch Indexing in Progress...**\n\n"
                        f"📁 Category: `{category.upper()}`\n"
                        f"🔄 Progress: `{idx}/{total_msgs}` messages scanned\n"
                        f"✅ Files Found: `{len(indexed_items)}`"
                    )
                except Exception:
                    pass

            await asyncio.sleep(0.3)  # Small delay to avoid FloodWait

        except Exception as e:
            continue

    if not indexed_items:
        return await status_msg.edit_text("❌ No media files were found in the specified range.")

    # Prepare response
    summary_text = (
        f"✅ **Batch Indexing Completed!**\n\n"
        f"📁 **Category:** `{category.upper()}`\n"
        f"📦 **Total Files Indexed:** `{len(indexed_items)}`\n\n"
    )

    # Build text file content with all links
    txt_content = f"=== OmniArchiver Batch Links ({category.upper()}) ===\nTotal Files: {len(indexed_items)}\n\n"
    for item in indexed_items:
        human_size = get_human_size(item['file_size'])
        txt_content += (
            f"File: {item['file_name']} ({human_size})\n"
            f"Stream: {item['stream_link']}\n"
            f"Download: {item['dl_link']}\n"
            f"{'-'*50}\n"
        )

    # If small number of items, show in message
    if len(indexed_items) <= 10:
        for item in indexed_items:
            human_size = get_human_size(item['file_size'])
            summary_text += (
                f"🎬 **{item['file_name']}** ({human_size})\n"
                f"▶️ [Stream]({item['stream_link']}) | 📥 [Download]({item['dl_link']})\n\n"
            )
    else:
        summary_text += "📄 *All links have been compiled into the attached file below for easy access.*"

    await status_msg.edit_text(summary_text, disable_web_page_preview=True)

    # Send .txt file with complete link list
    file_bytes = io.BytesIO(txt_content.encode('utf-8'))
    file_bytes.name = f"batch_{category}_{start_id}_to_{end_id}.txt"
    
    await msg.reply_document(
        document=file_bytes,
        caption=f"📁 **Batch Links List** ({category.upper()}) - `{len(indexed_items)} files`",
        quote=True
    )
