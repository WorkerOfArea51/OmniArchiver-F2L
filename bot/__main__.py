import asyncio
from hydrogram import idle
from bot.clients import start_all_clients, stop_all_clients, TelegramBot
from bot.server import server

async def main():
    await start_all_clients()
    server_task = TelegramBot.loop.create_task(server.serve())
    await idle()
    await stop_all_clients()

if __name__ == '__main__':
    TelegramBot.loop.run_until_complete(main())
