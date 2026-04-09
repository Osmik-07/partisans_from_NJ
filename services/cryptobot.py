import hashlib
import hmac
import json
import aiohttp
from bot.config import settings
from db.models import SubscriptionPlan

CRYPTOBOT_API = "https://pay.crypt.bot/api"

PLAN_NAMES = {
    SubscriptionPlan.WEEK: "Подписка на 7 дней",
    SubscriptionPlan.MONTH: "Подписка на 30 дней",
    SubscriptionPlan.YEAR: "Подписка на 1 год",
}


async def create_invoice(
    plan: SubscriptionPlan,
    amount: float,
    payload: str,
) -> dict:
    """Создаёт инвойс в CryptoBot и возвращает {invoice_id, pay_url}."""
    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{CRYPTOBOT_API}/createInvoice",
            headers={"Crypto-Pay-API-Token": settings.cryptobot_token},
            json={
                "currency_type": "fiat",
                "fiat": "USD",
                "amount": str(amount),
                "description": PLAN_NAMES.get(plan, "Подписка NotSpyBot"),
                "payload": payload,
                "paid_btn_name": "callback",
                "paid_btn_url": "https://t.me/notspybot",
                "expires_in": 3600,  # 1 час
            },
        )
        data = await resp.json()
        if not data.get("ok"):
            raise ValueError(f"CryptoBot error: {data}")
        result = data["result"]
        return {
            "invoice_id": str(result["invoice_id"]),
            "pay_url": result["pay_url"],
        }


def verify_webhook(body: bytes, signature: str) -> bool:
    """Проверяет подпись вебхука от CryptoBot."""
    secret = hashlib.sha256(settings.cryptobot_token.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook(body: bytes) -> dict:
    return json.loads(body)
