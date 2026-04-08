from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import list


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Telegram
    bot_token: str
    admin_ids: list[int] = []

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "notspybot"
    db_user: str = "notspybot"
    db_pass: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CryptoBot
    cryptobot_token: str = ""
    cryptobot_webhook_secret: str = ""

    # Webhook
    webhook_host: str = ""
    webhook_path: str = "/webhook"
    webhook_port: int = 8443

    # Prices USD
    price_trial_days: int = 1
    price_week_usd: float = 1.50
    price_month_usd: float = 3.00
    price_year_usd: float = 15.00

    # Prices Stars
    price_week_stars: int = 75
    price_month_stars: int = 150
    price_year_stars: int = 750

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_pass}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def use_webhook(self) -> bool:
        return bool(self.webhook_host)


settings = Settings()
