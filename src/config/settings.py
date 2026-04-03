from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ─── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(..., validation_alias="DATABASE_URL")

    # ─── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")

    # ─── API Keys ──────────────────────────────────────────────────────────────
    tank01_api_key: str = Field("", validation_alias="TANK01_API_KEY")

    # ─── App ───────────────────────────────────────────────────────────────────
    environment: str = Field("local", validation_alias="ENVIRONMENT")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
