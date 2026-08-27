# -*- coding: utf-8 -*-
from pyrogram.types import BotCommand
from Thunder.bot import StreamBot
from Thunder.utils.logger import logger
from Thunder.vars import Var

def get_commands():
    command_descriptions = {
        "start": "Start the bot & get features overview",
        "search": "Search anime or movie by name",
        "help": "How to search & import M3U playlists",
        "ping": "Check streaming latency & uptime",
        "about": "Bot & Streaming Engine details",
        "index": "(Admin) Index configured storage channels into MongoDB",
        "stats": "(Admin) View indexed files, storage & stream workload",
        "status": "(Admin) Check online worker status",
        "del": "(Admin) Delete a file from archive",
        "restart": "(Admin) Restart bot & web server"
    }
    return [BotCommand(name, desc) for name, desc in command_descriptions.items()]

async def set_commands():
    try:
        commands = get_commands()
        if commands:
            await StreamBot.set_bot_commands(commands)
    except Exception as e:
        logger.debug(f"Failed to set bot commands: {e}")
