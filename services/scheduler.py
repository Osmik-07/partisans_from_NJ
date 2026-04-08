"""
Планировщик задач — запускается в фоне вместе с ботом.
Задачи:
  1. Деактивация просроченных подписок (каждые 10 мин)
  2. Напоминание об истечении подписки за 24 часа (каждый час)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update
from aiogram import Bot

from db.base import AsyncSessionLocal
from db.models import Subscription, User

logger = logging.getLogger(__name__)


async def deactivate_expired_subscriptions():
    """Деактивирует подписки, у которых вышел срок."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Subscription)
            .where(
                Subscription.is_active == True,
                Subscription.expires_at <= now,
            )
            .values(is_active=False)
            .returning(Subscription.user_id, Subscription.plan)
        )
        expired = result.all()
        await session.commit()

    if expired:
        logger.info(f"Deactivated {len(expired)} expired subscriptions")

    return expired


async def send_expiry_reminders(bot: Bot):
    """Отправляет напоминание пользователям, у которых подписка истекает через ~24 часа."""
    now = datetime.now(timezone.utc)
    remind_window_start = now + timedelta(hours=23)
    remind_window_end = now + timedelta(hours=25)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Subscription.user_id, Subscription.plan, Subscription.expires_at)
            .where(
                Subscription.is_active == True,
                Subscription.expires_at >= remind_window_start,
                Subscription.expires_at <= remind_window_end,
            )
        )
        rows = result.all()

    for user_id, plan, expires_at in rows:
        expires_str = expires_at.strftime("%d.%m.%Y %H:%M UTC")
        try:
            await bot.send_message(
                user_id,
                f"⏰ <b>Подписка истекает через 24 часа</b>\n\n"
                f"Срок действия: до <b>{expires_str}</b>\n\n"
                f"Продли сейчас, чтобы не потерять доступ 👇",
                reply_markup=_renew_kb(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not remind user {user_id}: {e}")


async def notify_expired_users(bot: Bot, expired: list):
    """Уведомляет пользователей об истечении подписки."""
    for user_id, plan in expired:
        try:
            await bot.send_message(
                user_id,
                "😔 <b>Ваша подписка истекла</b>\n\n"
                "Для продолжения отслеживания сообщений продлите подписку.",
                reply_markup=_renew_kb(),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Could not notify expired user {user_id}: {e}")


def _renew_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    b = InlineKeyboardBuilder()
    b.button(text="💎 Продлить подписку", callback_data="sub:plans")
    return b.as_markup()


# ── Основной loop планировщика ────────────────────────────────────────

async def scheduler_loop(bot: Bot):
    logger.info("Scheduler started")
    reminder_tick = 0

    while True:
        try:
            # Каждые 10 минут — деактивация просроченных
            expired = await deactivate_expired_subscriptions()
            if expired:
                await notify_expired_users(bot, expired)

            # Каждый час (6 тиков × 10 мин) — напоминания
            reminder_tick += 1
            if reminder_tick >= 6:
                await send_expiry_reminders(bot)
                reminder_tick = 0

        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)

        await asyncio.sleep(600)  # 10 минут


def start_scheduler(bot: Bot):
    """Запускает планировщик как фоновую asyncio задачу."""
    asyncio.create_task(scheduler_loop(bot))
