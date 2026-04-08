"""
CryptoBot Webhook — отдельный aiohttp-роут для приёма подтверждений оплаты.
Подключается к основному aiohttp-приложению в main.py (webhook-режим)
или запускается отдельно (polling-режим).
"""
import json
import logging

from aiohttp import web
from bot.config import settings
from bot.services.cryptobot import verify_webhook
from bot.services.subscription import get_payment_by_external_id, confirm_payment
from db.base import AsyncSessionLocal

logger = logging.getLogger(__name__)

CRYPTOBOT_ROUTE = "/cryptobot/webhook"


async def cryptobot_webhook_handler(request: web.Request) -> web.Response:
    body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature", "")

    if not verify_webhook(body, signature):
        logger.warning("CryptoBot webhook: invalid signature")
        return web.Response(status=403, text="Invalid signature")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return web.Response(status=400, text="Bad JSON")

    # CryptoBot отправляет update_type = "invoice_paid"
    if data.get("update_type") != "invoice_paid":
        return web.Response(status=200, text="ok")

    invoice = data.get("payload", {})
    invoice_id = str(invoice.get("invoice_id", ""))
    status = invoice.get("status", "")

    if status != "paid":
        return web.Response(status=200, text="ok")

    async with AsyncSessionLocal() as session:
        payment = await get_payment_by_external_id(session, invoice_id)
        if not payment:
            logger.warning(f"CryptoBot webhook: payment not found for invoice {invoice_id}")
            return web.Response(status=200, text="ok")

        from db.models import PaymentStatus
        if payment.status == PaymentStatus.PAID:
            return web.Response(status=200, text="already processed")

        sub = await confirm_payment(session, payment)
        logger.info(f"Payment {payment.id} confirmed, sub until {sub.expires_at}")

        # Уведомляем пользователя
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode
            bot = Bot(
                token=settings.bot_token,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            expires = sub.expires_at.strftime("%d.%m.%Y")
            await bot.send_message(
                payment.user_id,
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"Подписка активна до <b>{expires}</b>.\n\n"
                f"Подключи бота: Настройки → Telegram для бизнеса → Чат-боты",
            )
            await bot.session.close()
        except Exception as e:
            logger.error(f"Failed to notify user {payment.user_id}: {e}")

    return web.Response(status=200, text="ok")


def register_cryptobot_webhook(app: web.Application):
    """Регистрирует роут в существующем aiohttp приложении."""
    app.router.add_post(CRYPTOBOT_ROUTE, cryptobot_webhook_handler)
    logger.info(f"CryptoBot webhook registered at {CRYPTOBOT_ROUTE}")
