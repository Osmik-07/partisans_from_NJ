from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.subscription import get_or_create_user
from bot.keyboards.main import main_menu_kb, plans_kb, back_main_kb

router = Router()

WELCOME_TEXT = (
    "👁 <b>NotSpyBot</b> — знай всё, что скрывают\n\n"
    "Бот перехватывает:\n"
    "• 🗑 <b>Удалённые сообщения</b> — читай то, что удалили\n"
    "• ✏️ <b>Правки сообщений</b> — сравни оригинал и изменённый текст\n"
    "• 📸 <b>Исчезающие фото/видео</b> — сохраняются навсегда\n\n"
    "⚠️ Для работы нужен <b>Telegram Premium</b> и подключение через "
    "<b>Настройки → Telegram для бизнеса → Чат-боты</b>.\n\n"
    "Выбери действие:"
)

HELP_CONNECT_TEXT = (
    "📌 <b>Как подключить бота:</b>\n\n"
    "1. Убедись, что у тебя активен <b>Telegram Premium</b>\n"
    "2. Открой <b>Настройки</b> в Telegram\n"
    "3. Перейди в <b>Telegram для бизнеса</b>\n"
    "4. Выбери <b>Чат-боты</b>\n"
    "5. Найди <b>@{bot_username}</b> и подключи\n"
    "6. Разреши доступ ко <b>всем чатам</b> или нужным\n\n"
    "После подключения бот начнёт отслеживать сообщения в реальном времени. "
    "История сообщений до подключения недоступна."
)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession):
    user = await get_or_create_user(session, message.from_user)
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "back:main")
async def cb_back_main(call: CallbackQuery):
    await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "help:connect")
async def cb_help_connect(call: CallbackQuery):
    from aiogram import Bot
    bot: Bot = call.bot
    me = await bot.get_me()
    text = HELP_CONNECT_TEXT.format(bot_username=me.username)
    await call.message.edit_text(text, reply_markup=back_main_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "sub:status")
async def cb_status(call: CallbackQuery, session: AsyncSession):
    from datetime import datetime, timezone
    from bot.services.subscription import get_user

    user = await get_user(session, call.from_user.id)
    sub = user.active_subscription if user else None

    if sub:
        expires = sub.expires_at.strftime("%d.%m.%Y %H:%M")
        plan_names = {"trial": "Пробный", "week": "7 дней", "month": "30 дней", "year": "1 год"}
        text = (
            f"✅ <b>Подписка активна</b>\n\n"
            f"Тариф: <b>{plan_names.get(sub.plan.value, sub.plan.value)}</b>\n"
            f"Действует до: <b>{expires} UTC</b>\n\n"
            f"Бизнес-бот: {'🟢 подключён' if user.business_connection_id else '🔴 не подключён'}"
        )
    else:
        text = (
            "❌ <b>Подписка не активна</b>\n\n"
            "Купи подписку, чтобы начать отслеживание."
        )

    await call.message.edit_text(text, reply_markup=plans_kb(not user.trial_used if user else True), parse_mode="HTML")
    await call.answer()
