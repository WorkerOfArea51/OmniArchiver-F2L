import asyncio
from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot
from bot.database.files import search_records
from bot.modules.decorators import verify_user

@TelegramBot.on_message(filters.command(['search', 'find']) & filters.private)
@verify_user
async def search_command(_, msg: Message):
    """Searches MongoDB database and outputs comprehensive interactive cards with stream & download links."""
    if len(msg.command) < 2:
        return await msg.reply(
            "🔍 **Search Usage:**\n"
            "• `/search <name>`\n\n"
            "**Examples:**\n"
            "• `/search 86`\n"
            "• `/search undertaker`\n"
            "• `/search attack on titan`",
            quote=True
        )

    query = msg.text.split(maxsplit=1)[1].strip()
    status_msg = await msg.reply(f"🔎 *Searching for* `{query}`...", quote=True)

    results = await search_records(query, limit=10)

    if not results:
        return await status_msg.edit_text(f"❌ **No results found for:** `{query}`\nMake sure the spelling is correct!")

    header = (
        f"🔍 **Search Results for:** `{query}`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 **Found:** `{len(results)} matching titles`\n\n"
    )

    message_chunks = []
    current_chunk = header

    for item in results:
        if item['type'] == 'movie':
            title = item.get('title') or item.get('file_name')
            dur = item.get('duration_formatted', 'N/A')
            size = item.get('size_formatted', '0 B')
            stream_url = item['stream_url']
            download_url = item['download_url']
            api_url = item['api_url']

            card = (
                f"🎬 **{title}**\n"
                f"📁 `MOVIE` • ⏱️ `{dur}` • 💾 `{size}`\n"
                f"> ▶️ [Stream Online]({stream_url})  •  📥 [Direct Download]({download_url})\n"
                f"> ⚡ **API:** `{api_url}`\n\n"
            )
        else:
            # Batch item (Anime or Web Series)
            title = item.get('title', 'Batch')
            cat = item.get('category', 'ANIME').upper()
            total_eps = item.get('total_episodes', 0)
            total_size = item.get('size_formatted', '0 B')
            api_url = item['api_url']
            episodes = item.get('episodes', [])

            card = (
                f"📺 **{title}**\n"
                f"📁 `{cat}` • 📦 `{total_eps} Episodes` • 💾 `{total_size}`\n"
                f"⚡ **API:** `{api_url}`\n"
            )

            # Render all episodes in the batch
            for ep in episodes:
                ep_num = ep.get('episode_num', 1)
                ep_dur = ep.get('duration_formatted', 'N/A')
                ep_size = ep.get('size_formatted', '0 B')
                ep_name = ep.get('file_name', f'Episode {ep_num}')
                if ep_name.endswith(('.mkv', '.mp4', '.avi', '.webm', '.ts')):
                    ep_name = ep_name.rsplit('.', 1)[0]
                card += (
                    f"> 🎬 **EP {ep_num:02d}** • `⏱️ {ep_dur}` • `💾 {ep_size}`\n"
                    f"> 📝 **{ep_name}**\n"
                    f"> ▶️ [Stream Online]({ep['stream_url']})  •  📥 [Direct Download]({ep['download_url']})\n"
                    f">\n"
                )

            card += "\n"

        if len(current_chunk) + len(card) > 3800:
            message_chunks.append(current_chunk.strip())
            current_chunk = card
        else:
            current_chunk += card

    if current_chunk.strip():
        message_chunks.append(current_chunk.strip())

    await status_msg.edit_text(message_chunks[0], disable_web_page_preview=True)

    for follow_up in message_chunks[1:]:
        await msg.reply(follow_up, quote=False, disable_web_page_preview=True)
        await asyncio.sleep(0.5)

@TelegramBot.on_message(filters.command(['search_api', 'api_search', 'get_api']) & filters.private)
@verify_user
async def search_api_command(_, msg: Message):
    """Searches MongoDB database and outputs ONLY the clean 1-tap copyable API endpoints."""
    if len(msg.command) < 2:
        return await msg.reply(
            "⚡ **StreamHub API Search Usage:**\n"
            "• `/search_api <name>`\n\n"
            "**Examples:**\n"
            "• `/search_api 86`\n"
            "• `/search_api undertaker`",
            quote=True
        )

    query = msg.text.split(maxsplit=1)[1].strip()
    status_msg = await msg.reply(f"⚡ *Fetching API endpoints for* `{query}`...", quote=True)

    results = await search_records(query, limit=15)

    if not results:
        return await status_msg.edit_text(f"❌ **No API endpoints found for:** `{query}`")

    text = (
        f"⚡ **StreamHub API Search Results**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 **Query:** `{query}`\n"
        f"📦 **Matches Found:** `{len(results)}`\n\n"
    )

    for item in results:
        if item['type'] == 'movie':
            title = item.get('title') or item.get('file_name')
            dur = item.get('duration_formatted', 'N/A')
            api_url = item['api_url']
            text += (
                f"🎬 **{title}** `[MOVIE • {dur}]`\n"
                f"🔗 `{api_url}`\n\n"
            )
        else:
            title = item.get('title', 'Batch')
            cat = item.get('category', 'ANIME').upper()
            total_eps = item.get('total_episodes', 0)
            api_url = item['api_url']
            text += (
                f"📺 **{title}** `[{cat} • {total_eps} eps]`\n"
                f"🔗 `{api_url}`\n\n"
            )

    await status_msg.edit_text(text, disable_web_page_preview=True)

@TelegramBot.on_message(filters.command(['set_title', 'rename', 'name']) & filters.private)
@verify_user
async def set_title_command(_, msg: Message):
    """Updates or sets the title for an existing anime/series batch or movie in MongoDB."""
    from bot.database import db
    from bot.config import Server

    if len(msg.command) < 3:
        return await msg.reply(
            "🏷️ **Set / Rename Title Usage:**\n"
            "• `/set_title <batch_id_or_keyword> <New Title Name>`\n\n"
            "**Examples:**\n"
            "• `/set_title 9af0276c 86: Eighty Six (Season 1)`\n"
            "• `/set_title undertaker 86: Eighty Six`\n"
            "• `/set_title first love First Love (Season 1)`",
            quote=True
        )

    target_key = msg.command[1].strip()
    new_title = msg.text.split(maxsplit=2)[2].strip()

    status_msg = await msg.reply(f"⏳ *Searching and renaming to* **{new_title}**...", quote=True)

    for col, cat_name in ((db.anime, 'ANIME'), (db.webseries, 'WEB SERIES'), (db.movies, 'MOVIE')):
        if col is not None:
            batch_doc = await col.find_one({
                '$or': [
                    {'_id': target_key},
                    {'_id': {'$regex': f"^{target_key}", '$options': 'i'}},
                    {'title': {'$regex': target_key, '$options': 'i'}},
                    {'episodes.file_name': {'$regex': target_key, '$options': 'i'}},
                    {'file_name': {'$regex': target_key, '$options': 'i'}}
                ]
            })

            if batch_doc:
                doc_id = batch_doc['_id']
                await col.update_one({'_id': doc_id}, {'$set': {'title': new_title}})
                
                if cat_name in ('ANIME', 'WEB SERIES'):
                    api_url = f"{Server.BASE_URL}/api/batch/{doc_id}"
                else:
                    api_url = f"{Server.BASE_URL}/api/file/{doc_id}"

                return await status_msg.edit_text(
                    f"✅ **Title Updated Successfully!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏷️ **New Title:** **{new_title}**\n"
                    f"📁 **Category:** `{cat_name}`\n"
                    f"⚡ **API Endpoint:** `{api_url}`\n\n"
                    f"Now searching `/search {new_title}` will find it immediately! 🍿✨"
                )

    await status_msg.edit_text(f"❌ Could not find any batch or movie matching `{target_key}` in database.")
