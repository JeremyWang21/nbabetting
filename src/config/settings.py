from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ─── Database ──────────────────────────────────────────────────────────────
    database_url: str = Field(..., validation_alias="DATABASE_URL")

    # ─── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")

    # ─── API Keys ──────────────────────────────────────────────────────────────
    odds_api_key: str = Field("", validation_alias="ODDS_API_KEY")
    tank01_api_key: str = Field("", validation_alias="TANK01_API_KEY")

    # ─── App ───────────────────────────────────────────────────────────────────
    environment: str = Field("local", validation_alias="ENVIRONMENT")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    # ─── Scheduler ─────────────────────────────────────────────────────────────
    odds_poll_interval_seconds: int = Field(
        180, validation_alias="ODDS_POLL_INTERVAL_SECONDS"
    )

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
