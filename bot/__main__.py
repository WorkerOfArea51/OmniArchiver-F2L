import asyncio
from hydrogram import idle
from bot.clients import start_all_clients, stop_all_clients, TelegramBot, MultiClients
from bot.server import server
from bot.modules.memory import flush_ram

async def keep_alive_heartbeat():
    """Keeps all Telegram MTProto worker sockets warm and auto-compacts RAM every 2 minutes."""
    while True:
        try:
            await asyncio.sleep(120)  # Every 2 minutes
            for client in MultiClients.values():
                if client and client.is_connected:
                    try:
                        # Light ping to Telegram DC to keep TCP socket warm & active
                        await client.get_me()
                    except Exception:
                        pass
            # Auto-compact RAM
            flush_ram()
        except asyncio.CancelledError:
            break
        except Exception:
            pass

async def main():
    await start_all_clients()
    server_task = TelegramBot.loop.create_task(server.serve())
    heartbeat_task = TelegramBot.loop.create_task(keep_alive_heartbeat())
    await idle()
    heartbeat_task.cancel()
    await stop_all_clients()

if __name__ == '__main__':
    TelegramBot.loop.run_until_complete(main())
