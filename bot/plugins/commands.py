from hydrogram import filters
from hydrogram.types import Message
from bot.clients import TelegramBot, worker_clients
from bot.config import Telegram
from bot.database.files import get_stats
from bot.modules.static import WelcomeText, PrivacyText
from bot.modules.decorators import verify_user, verify_admin

@TelegramBot.on_message(filters.command(['start', 'help']) & filters.private)
@verify_user
async def start_command(_, msg: Message):
    await msg.reply(
        text=WelcomeText % {'first_name': msg.from_user.first_name},
        quote=True,
        disable_web_page_preview=True
    )

@TelegramBot.on_message(filters.command('privacy') & filters.private)
@verify_user
async def privacy_command(_, msg: Message):
    await msg.reply(text=PrivacyText, quote=True, disable_web_page_preview=True)

@TelegramBot.on_message(filters.command('stats') & filters.private)
@verify_user
@verify_admin
async def stats_command(_, msg: Message):
    stats = await get_stats()
    total = sum(stats.values())
    
    text = (
        "📊 **OmniArchiver Database Stats**\n\n"
        f"🎬 **Movies Indexed:** `{stats.get('movies', 0)}`\n"
        f"📺 **Anime Files:** `{stats.get('anime', 0)}`\n"
        f"🍿 **Web Series Files:** `{stats.get('webseries', 0)}`\n"
        f"📁 **Direct Files:** `{stats.get('direct_files', 0)}`\n"
        f"{'─'*25}\n"
        f"📦 **Total Indexed Files:** `{total}`\n"
        f"🤖 **Active Worker Bots:** `{len(worker_clients)}`\n"
        f"👑 **Admins Registered:** `{len(Telegram.ADMIN_IDS)}`\n"
    )
    await msg.reply(text, quote=True)

@TelegramBot.on_message(filters.command('log') & filters.private)
@verify_user
@verify_admin
async def log_command(_, msg: Message):
    try:
        await msg.reply_document('event-log.txt', quote=True)
    except Exception as e:
        await msg.reply(f"❌ Failed to send log file: `{e}`", quote=True)
