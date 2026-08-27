# -*- coding: utf-8 -*-
# Thunder/utils/custom_dl.py - High-Performance MTProto ByteStreamer

import asyncio
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional
from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message
from Thunder.server.exceptions import FileNotFound
from Thunder.utils.file_properties import get_media
from Thunder.utils.logger import logger
from Thunder.vars import Var

class ByteStreamer:
    __slots__ = ('client', 'chat_id')

    def __init__(self, client: Client, chat_id: Optional[int] = None) -> None:
        self.client = client
        self.chat_id = int(chat_id or Var.BIN_CHANNEL or 0)

    async def get_message(self, message_id: int, channel_id: Optional[int] = None) -> Message:
        target_chat = channel_id or self.chat_id
        while True:
            try:
                message = await self.client.get_messages(target_chat, message_id)
                break
            except FloodWait as e:
                logger.debug(f"FloodWait: get_message, sleep {e.value}s")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.debug(f"Error fetching message {message_id} from {target_chat}: {e}", exc_info=True)
                raise FileNotFound(f"Message {message_id} not found in channel {target_chat}") from e

        if not message or not message.media:
            raise FileNotFound(f"Message {message_id} not found or has no media")
        return message

    async def stream_file(
        self,
        media_ref: int | Message,
        channel_id: Optional[int] = None,
        offset: int = 0,
        limit: int = 0,
        fallback_message_id: int | None = None,
        on_fallback_message: Optional[Callable[[Message], Awaitable[None]]] = None
    ) -> AsyncGenerator[bytes, None]:
        chunk_offset = offset // (1024 * 1024)
        chunk_limit = 0
        if limit > 0:
            chunk_limit = ((limit + (1024 * 1024) - 1) // (1024 * 1024)) + 1

        target_chat = channel_id or self.chat_id
        refs: list[int | Message] = [media_ref]
        media_id = media_ref if isinstance(media_ref, int) else None
        if isinstance(media_ref, Message):
            media_id = getattr(media_ref, "id", getattr(media_ref, "message_id", None))
        if fallback_message_id is not None and (media_id is None or fallback_message_id != media_id):
            refs.append(fallback_message_id)

        last_error: Exception | None = None
        for ref in refs:
            started_stream = False
            while True:
                try:
                    target = await self.get_message(ref, target_chat) if isinstance(ref, int) else ref
                    if (
                        on_fallback_message is not None and
                        fallback_message_id is not None and
                        ref == fallback_message_id and
                        isinstance(target, Message)
                    ):
                        await on_fallback_message(target)

                    async for chunk in self.client.stream_media(
                        target, offset=chunk_offset, limit=chunk_limit
                    ):
                        started_stream = True
                        yield chunk
                    return
                except FloodWait as e:
                    logger.debug(f"FloodWait: stream_file, sleep {e.value}s")
                    await asyncio.sleep(e.value)
                except Exception as e:
                    last_error = e
                    logger.debug(f"Error streaming media ref {ref}: {e}", exc_info=True)
                    if started_stream:
                        raise
                    break

        raise FileNotFound(f"Unable to stream file: {last_error}")
