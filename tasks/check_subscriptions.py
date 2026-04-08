"""
Скрипт для проверки истёкших подписок и уведомления пользователей.
Запускать через cron каждый час:
  0 * * * * cd /app && python -m bot.tasks.check_subscriptions
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from sqlalchemy import select, update

from bot.config import settings
from db.base import AsyncSessionLocal
from db.models import Subscription, User

logger = logging.getLogger(__name__)


async def notify_expiring():
    """Уведомляем пользователей за 24 часа до истечения."""
    bot = Bot(token=settings.bot_token)
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.expires_at > now,
                Subscription.expires_at <= soon,
            )
        )
        expiring = result.scalars().all()

        for sub in expiring:
            user = await session.get(User, sub.user_id)
            if not user:
                continue
            try:
                expires = sub.expires_at.strftime("%d.%m.%Y %H:%M")
                await bot.send_message(
                    user.id,
                    f"⚠️ <b>Подписка истекает через 24 часа</b>\n\n"
                    f"Срок действия: до <b>{expires} UTC</b>\n\n"
                    f"Продли подписку, чтобы не прерывать отслеживание.",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Cannot notify {user.id}: {e}")

    await bot.session.close()


async def deactivate_expired():
    """Деактивируем истёкшие подписки."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(Subscription.is_active == True, Subscription.expires_at <= now)
            .values(is_active=False)
            .returning(Subscription.user_id)
        )
        expired_users = result.scalars().all()
        await session.commit()
        logger.info(f"Deactivated subscriptions for {len(expired_users)} users")


async def main():
    logging.basicConfig(level=logging.INFO)
    await notify_expiring()
    await deactivate_expired()


if __name__ == "__main__":
    asyncio.run(main())
