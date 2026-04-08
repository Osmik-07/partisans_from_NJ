from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
import redis.asyncio as aioredis
from bot.config import settings

RATE_LIMIT = 1  # секунд между запросами


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self):
        self.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        key = f"throttle:{user_id}"
        result = await self.redis.set(key, "1", ex=RATE_LIMIT, nx=True)
        if not result:
            await event.answer("⏳ Не так быстро! Подожди секунду.")
            return

        return await handler(event, data)
