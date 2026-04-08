import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import settings
from bot.handlers import start, subscription, business, admin
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.services.scheduler import start_scheduler
from bot.services.webhook_cryptobot import register_cryptobot_webhook
from db.base import create_tables

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await create_tables()
    start_scheduler(bot)   # фоновый планировщик
    if settings.use_webhook:
        await bot.set_webhook(
            url=f"{settings.webhook_host}{settings.webhook_path}",
            allowed_updates=[
                "message",
                "callback_query",
                "pre_checkout_query",
                "business_connection",
                "business_message",
                "edited_business_message",
                "deleted_business_messages",
            ],
        )
        logger.info(f"Webhook set: {settings.webhook_host}{settings.webhook_path}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Polling mode")


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Middlewares
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(ThrottlingMiddleware())
    dp.update.middleware(SubscriptionMiddleware())

    # Routers
    dp.include_router(admin.router)      # первым — чтобы /admin не блокировался
    dp.include_router(start.router)
    dp.include_router(subscription.router)
    dp.include_router(business.router)

    return dp


async def main_polling():
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(lambda: on_startup(bot))
    await dp.start_polling(bot)


async def main_webhook():
    bot = create_bot()
    dp = create_dispatcher()
    await on_startup(bot)

    app = web.Application()
    app["bot"] = bot
    handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    handler.register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)
    from bot.webhooks.cryptobot import register_cryptobot_webhook
    register_cryptobot_webhook(app)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.webhook_port)
    await site.start()
    logger.info(f"Webhook server started on port {settings.webhook_port}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    if settings.use_webhook:
        asyncio.run(main_webhook())
    else:
        asyncio.run(main_polling())
