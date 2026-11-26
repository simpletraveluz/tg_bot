from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_customer_bot_token: str = ""
    telegram_staff_bot_token: str = ""
    telegram_customer_webhook_secret: str = ""
    telegram_staff_webhook_secret: str = ""

    backend_url: str = "http://localhost:8000/api/v1"
    bot_service_token: str = ""

    redis_url: str = "redis://localhost:6379/0"

    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
