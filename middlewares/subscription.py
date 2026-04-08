from typing import Callable, Awaitable, Any
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from db.base import AsyncSessionLocal
from bot.services.subscription import get_user

# Команды/колбэки, доступные без подписки
FREE_COMMANDS = {"/start", "/help"}
FREE_CALLBACKS = {"sub:", "buy:", "pay:", "back:", "help:"}


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        # Проверяем только Message и CallbackQuery
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        # Пропускаем свободные команды
        if isinstance(event, Message) and event.text:
            cmd = event.text.split()[0].lower()
            if cmd in FREE_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery) and event.data:
            for prefix in FREE_CALLBACKS:
                if event.data.startswith(prefix):
                    return await handler(event, data)

        # Проверяем подписку
        async with AsyncSessionLocal() as session:
            user = await get_user(session, user_id)

        if not user:
            return await handler(event, data)

        if user.is_banned:
            if isinstance(event, Message):
                await event.answer("⛔️ Ваш аккаунт заблокирован.")
            elif isinstance(event, CallbackQuery):
                await event.answer("⛔️ Ваш аккаунт заблокирован.", show_alert=True)
            return

        # Business-события не требуют проверки (они проверяются внутри хэндлера)
        return await handler(event, data)
