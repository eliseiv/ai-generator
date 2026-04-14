from pydantic import computed_field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ai-generator"
    debug: bool = False
    secret_key: str = "change-me"

    # Database (individual fields assembled into URL)
    db_name: str = "ai_generator"
    db_user: str = "postgres"
    db_password: str = "postgres"
    db_host: str = "postgres"
    db_port: int = 5432

    # Redis (individual fields assembled into URL)
    redis_host: str = "redis"
    redis_pass: str = ""
    redis_port: int = 6379

    # Fal.ai
    fal_key: str = ""
    fal_webhook_base_url: str = "http://localhost:8000"

    # Rate Limiting
    rate_limit_max_requests: int = 10
    rate_limit_window_seconds: int = 60
    rate_limit_block_seconds: int = 60

    # Webhook delivery
    webhook_max_retries: int = 5
    webhook_retry_interval_seconds: int = 15

    # Circuit breaker
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60

    # Logging
    log_level: str = "INFO"
    log_retention_days: int = 7

    # Payment webhook authentication
    payment_webhook_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_tokens_per_dollar: int = 100

    # Fallback Fal.ai provider
    fal_key_fallback: str = ""

    # When True, generation endpoints skip Celery dispatch (for load testing)
    dry_run: bool = False

    # Ngrok
    ngrok_authtoken: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_pass}@" if self.redis_pass else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker_url(self) -> str:
        auth = f":{self.redis_pass}@" if self.redis_pass else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/1"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_result_backend(self) -> str:
        auth = f":{self.redis_pass}@" if self.redis_pass else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/2"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
