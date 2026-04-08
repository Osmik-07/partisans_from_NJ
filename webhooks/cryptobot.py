"""
CryptoBot webhook handler.
Подключается к основному aiohttp app при работе в webhook-режиме.
При polling — запускается отдельным маршрутом через aiohttp.
"""
import json
import hashlib
import hmac
import logging

from aiohttp import web
from bot.config import settings
from bot.services import cryptobot as crypto_svc
from bot.services import subscription as sub_svc
from db.base import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def cryptobot_webhook_handler(request: web.Request) -> web.Response:
    body = await request.read()
    signature = request.headers.get("crypto-pay-api-signature", "")

    if not crypto_svc.verify_webhook(body, signature):
        logger.warning("CryptoBot webhook: invalid signature")
        return web.Response(status=403, text="Invalid signature")

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return web.Response(status=400, text="Bad JSON")

    update_type = data.get("update_type")
    if update_type != "invoice_paid":
        return web.Response(text="ok")

    payload_obj = data.get("payload", {})
    invoice_id = str(payload_obj.get("invoice_id", ""))
    invoice_payload = payload_obj.get("payload", "")  # наш payment.id

    logger.info(f"CryptoBot paid: invoice_id={invoice_id} payload={invoice_payload}")

    try:
        async with AsyncSessionLocal() as session:
            payment = await sub_svc.get_payment_by_external_id(session, invoice_id)
            if not payment:
                # Ищем по payload (payment.id)
                from sqlalchemy import select
                from db.models import Payment
                result = await session.execute(
                    select(Payment).where(Payment.id == int(invoice_payload))
                )
                payment = result.scalar_one_or_none()

            if not payment:
                logger.warning(f"Payment not found: {invoice_id}")
                return web.Response(text="ok")

            from db.models import PaymentStatus
            if payment.status == PaymentStatus.PAID:
                return web.Response(text="ok")  # уже обработан

            sub = await sub_svc.confirm_payment(session, payment)

        # Уведомляем пользователя
        bot = request.app["bot"]
        expires = sub.expires_at.strftime("%d.%m.%Y")
        await bot.send_message(
            payment.user_id,
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"Подписка активна до <b>{expires}</b>.\n\n"
            f"Подключи бота: Настройки → Telegram для бизнеса → Чат-боты",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception(f"CryptoBot webhook error: {e}")

    return web.Response(text="ok")


def register_cryptobot_webhook(app: web.Application):
    app.router.add_post("/cryptobot/webhook", cryptobot_webhook_handler)
