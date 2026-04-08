from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bot.config import settings


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 Купить подписку", callback_data="sub:plans")
    builder.button(text="📊 Мой статус", callback_data="sub:status")
    builder.button(text="❓ Как подключить", callback_data="help:connect")
    builder.adjust(1)
    return builder.as_markup()


def plans_kb(trial_available: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if trial_available:
        builder.button(text="🎁 Пробный день — БЕСПЛАТНО", callback_data="buy:trial")
    builder.button(
        text=f"⚡️ 7 дней — ${settings.price_week_usd}",
        callback_data="buy:week",
    )
    builder.button(
        text=f"🔥 30 дней — ${settings.price_month_usd}",
        callback_data="buy:month",
    )
    builder.button(
        text=f"👑 1 год — ${settings.price_year_usd} (скидка 37%)",
        callback_data="buy:year",
    )
    builder.button(text="« Назад", callback_data="back:main")
    builder.adjust(1)
    return builder.as_markup()


def payment_method_kb(plan: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💎 Крипта (CryptoBot)", callback_data=f"pay:crypto:{plan}")
    builder.button(text="⭐️ Telegram Stars", callback_data=f"pay:stars:{plan}")
    builder.button(text="« Назад", callback_data="sub:plans")
    builder.adjust(1)
    return builder.as_markup()


def pay_crypto_kb(pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", url=pay_url)
    builder.button(text="✅ Я оплатил", callback_data="pay:check")
    builder.button(text="« Отмена", callback_data="sub:plans")
    builder.adjust(1)
    return builder.as_markup()


def back_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="« Главное меню", callback_data="back:main")
    return builder.as_markup()


# ── ADMIN ──────────────────────────────────────────────────────────
def admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin:stats")
    builder.button(text="👥 Пользователи", callback_data="admin:users")
    builder.button(text="📢 Рассылка", callback_data="admin:broadcast")
    builder.button(text="🔨 Бан / разбан", callback_data="admin:ban")
    builder.adjust(2)
    return builder.as_markup()
