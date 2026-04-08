from aiogram import Router, F
from aiogram.types import CallbackQuery, LabeledPrice, PreCheckoutQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards.main import plans_kb, payment_method_kb, pay_crypto_kb, back_main_kb
from bot.services import subscription as sub_svc
from bot.services import cryptobot as crypto_svc
from db.models import SubscriptionPlan, PaymentMethod

router = Router()

PLAN_MAP = {
    "trial": SubscriptionPlan.TRIAL,
    "week": SubscriptionPlan.WEEK,
    "month": SubscriptionPlan.MONTH,
    "year": SubscriptionPlan.YEAR,
}

PLAN_LABELS = {
    "trial": "Пробный день",
    "week": "7 дней",
    "month": "30 дней",
    "year": "1 год",
}


# ── Показать планы ──────────────────────────────────────────────────
@router.callback_query(F.data == "sub:plans")
async def cb_plans(call: CallbackQuery, session: AsyncSession):
    user = await sub_svc.get_user(session, call.from_user.id)
    trial_ok = not user.trial_used if user else True
    await call.message.edit_text(
        "💎 <b>Выбери тариф:</b>",
        reply_markup=plans_kb(trial_ok),
        parse_mode="HTML",
    )
    await call.answer()


# ── Пробный период ──────────────────────────────────────────────────
@router.callback_query(F.data == "buy:trial")
async def cb_trial(call: CallbackQuery, session: AsyncSession):
    user = await sub_svc.get_user(session, call.from_user.id)
    if user and user.trial_used:
        await call.answer("Пробный период уже использован.", show_alert=True)
        return

    await sub_svc.activate_subscription(session, call.from_user.id, SubscriptionPlan.TRIAL)
    await call.message.edit_text(
        "🎁 <b>Пробный период активирован!</b>\n\n"
        "У тебя есть <b>1 день</b> для проверки бота.\n\n"
        "Не забудь подключить бота через Telegram для бизнеса ➜ /start",
        reply_markup=back_main_kb(),
        parse_mode="HTML",
    )
    await call.answer()


# ── Выбор плана (неделя/месяц/год) → выбор метода оплаты ───────────
@router.callback_query(F.data.startswith("buy:"))
async def cb_buy_plan(call: CallbackQuery):
    plan_key = call.data.split(":")[1]
    if plan_key == "trial":
        return  # обрабатывается выше

    label = PLAN_LABELS.get(plan_key, plan_key)
    await call.message.edit_text(
        f"💳 <b>Оплата тарифа «{label}»</b>\n\nВыбери способ оплаты:",
        reply_markup=payment_method_kb(plan_key),
        parse_mode="HTML",
    )
    await call.answer()


# ── Оплата крипто ───────────────────────────────────────────────────
@router.callback_query(F.data.startswith("pay:crypto:"))
async def cb_pay_crypto(call: CallbackQuery, session: AsyncSession):
    plan_key = call.data.split(":")[2]
    plan = PLAN_MAP.get(plan_key)
    if not plan:
        await call.answer("Неверный тариф", show_alert=True)
        return

    amounts = {
        "week": settings.price_week_usd,
        "month": settings.price_month_usd,
        "year": settings.price_year_usd,
    }
    amount = amounts[plan_key]

    payment = await sub_svc.create_payment(
        session,
        user_id=call.from_user.id,
        plan=plan,
        method=PaymentMethod.CRYPTOBOT,
        amount_usd=amount,
    )

    try:
        invoice = await crypto_svc.create_invoice(
            plan=plan,
            amount=amount,
            payload=str(payment.id),
        )
    except Exception as e:
        await call.answer(f"Ошибка создания инвойса: {e}", show_alert=True)
        return

    payment.external_id = invoice["invoice_id"]
    payment.invoice_url = invoice["pay_url"]
    await session.commit()

    await call.message.edit_text(
        f"💎 <b>Оплата через CryptoBot</b>\n\n"
        f"Тариф: <b>{PLAN_LABELS[plan_key]}</b>\n"
        f"Сумма: <b>${amount}</b>\n\n"
        f"Нажми «Оплатить», затем вернись и нажми «Я оплатил».",
        reply_markup=pay_crypto_kb(invoice["pay_url"]),
        parse_mode="HTML",
    )
    await call.answer()


# ── Проверка оплаты крипто ──────────────────────────────────────────
@router.callback_query(F.data == "pay:check")
async def cb_pay_check(call: CallbackQuery, session: AsyncSession):
    from sqlalchemy import select
    from db.models import Payment, PaymentStatus
    # Ищем последний pending платёж пользователя
    result = await session.execute(
        select(Payment)
        .where(Payment.user_id == call.from_user.id, Payment.status == PaymentStatus.PENDING)
        .order_by(Payment.created_at.desc())
        .limit(1)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        await call.answer("Платёж не найден.", show_alert=True)
        return

    # Проверяем через CryptoBot API
    import aiohttp
    async with aiohttp.ClientSession() as http:
        resp = await http.get(
            f"{crypto_svc.CRYPTOBOT_API}/getInvoices",
            headers={"Crypto-Pay-API-Token": settings.cryptobot_token},
            params={"invoice_ids": payment.external_id},
        )
        data = await resp.json()

    if data.get("ok"):
        items = data["result"].get("items", [])
        if items and items[0]["status"] == "paid":
            sub = await sub_svc.confirm_payment(session, payment)
            expires = sub.expires_at.strftime("%d.%m.%Y")
            await call.message.edit_text(
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"Подписка активна до <b>{expires}</b>.\n\n"
                f"Подключи бота: Настройки → Telegram для бизнеса → Чат-боты",
                reply_markup=back_main_kb(),
                parse_mode="HTML",
            )
            await call.answer("Оплата подтверждена! ✅")
            return

    await call.answer("Платёж ещё не найден. Попробуй через минуту.", show_alert=True)


# ── Telegram Stars ──────────────────────────────────────────────────
@router.callback_query(F.data.startswith("pay:stars:"))
async def cb_pay_stars(call: CallbackQuery, session: AsyncSession):
    plan_key = call.data.split(":")[2]
    plan = PLAN_MAP.get(plan_key)
    if not plan:
        await call.answer("Неверный тариф", show_alert=True)
        return

    stars_map = {
        "week": settings.price_week_stars,
        "month": settings.price_month_stars,
        "year": settings.price_year_stars,
    }
    stars = stars_map[plan_key]

    payment = await sub_svc.create_payment(
        session,
        user_id=call.from_user.id,
        plan=plan,
        method=PaymentMethod.STARS,
        amount_stars=stars,
    )

    await call.message.answer_invoice(
        title=f"NotSpyBot — {PLAN_LABELS[plan_key]}",
        description="Доступ к отслеживанию удалённых сообщений, правок и исчезающих фото",
        payload=str(payment.id),
        currency="XTR",
        prices=[LabeledPrice(label="Stars", amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars_payment(message: Message, session: AsyncSession):
    payload = message.successful_payment.invoice_payload
    from sqlalchemy import select
    from db.models import Payment
    result = await session.execute(select(Payment).where(Payment.id == int(payload)))
    payment = result.scalar_one_or_none()
    if payment:
        sub = await sub_svc.confirm_payment(session, payment)
        expires = sub.expires_at.strftime("%d.%m.%Y")
        await message.answer(
            f"⭐️ <b>Оплата звёздами подтверждена!</b>\n\n"
            f"Подписка активна до <b>{expires}</b>.\n\n"
            f"Подключи бота: Настройки → Telegram для бизнеса → Чат-боты",
            reply_markup=back_main_kb(),
            parse_mode="HTML",
        )
