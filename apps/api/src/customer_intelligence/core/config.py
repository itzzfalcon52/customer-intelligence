from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIRECTORY = Path(__file__).resolve().parents[3]
PROJECT_DIRECTORY = API_DIRECTORY.parent.parent


class Settings(BaseSettings):
    app_name: str = "Customer Intelligence API"
    service_name: str = "customer-intelligence-api"
    environment: Literal["development", "test", "production"] = "development"
    data_directory: Path = PROJECT_DIRECTORY / ".data"

    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "testserver"]
    auth_mode: Literal["account", "private"] = "account"
    auth_public_origin: str = Field(default="http://127.0.0.1:5173", validation_alias="APP_ORIGIN")
    auth_service_url: str = "http://127.0.0.1:3001"
    auth_bridge_secret: SecretStr | None = Field(
        default=None, validation_alias="INTERNAL_API_SECRET"
    )
    api_token: SecretStr | None = None
    # Large datasets train for longer; the worker stops a job after this budget.
    worker_timeout_seconds: int = Field(default=1800, ge=10, le=4 * 3600)
    # Upload limits. Bigger files cost only time, RAM and disk; rows never reach the AI provider.
    max_upload_mb: int = Field(default=200, ge=1, le=2048)
    max_rows: int = Field(default=1_000_000, ge=100, le=10_000_000)
    max_columns: int = Field(default=500, ge=2, le=5000)
    # openpyxl holds a workbook in memory, so Excel stays smaller than CSV.
    max_excel_mb: int = Field(default=50, ge=1, le=500)

    nebius_timeout_seconds: int = Field(default=60, ge=5, le=120)
    nebius_trust_env: bool = False
    nebius_enable_thinking: bool = False
    # Retries apply only to timeouts, connection failures, 429 and 5xx responses.
    nebius_max_retries: int = Field(default=1, ge=0, le=3)
    # Optional USD prices per million input/output tokens, e.g. {"model-id": [0.1, 0.4]}.
    # Costs stay unknown (null) for models without a configured price; nothing is guessed.
    model_prices: dict[str, tuple[float, float]] = Field(default_factory=dict)

    nebius_api_key: SecretStr | None = Field(default=None, validation_alias="NEBIUS_API_KEY")
    nebius_base_url: HttpUrl | None = Field(default=None, validation_alias="NEBIUS_BASE_URL")
    nebius_model: str | None = Field(default=None, min_length=1, validation_alias="NEBIUS_MODEL")
    # Optional cheaper model for tool routing; the primary model writes final answers.
    nebius_fast_model: str | None = Field(
        default=None, min_length=1, validation_alias="NEBIUS_FAST_MODEL"
    )

    # Fernet key (urlsafe base64, 32 bytes) that encrypts connector credentials at rest.
    # Connectors stay disabled until it is set. Generate one with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_key: SecretStr | None = None
    stripe_api_base: str = "https://api.stripe.com"
    hubspot_api_base: str = "https://api.hubapi.com"
    razorpay_api_base: str = "https://api.razorpay.com"
    # Zoho: normally derived from the connection's region and the token's api_domain; set these
    # only to point every Zoho call at one host (tests, local fakes).
    zoho_accounts_base: str | None = None
    zoho_api_base: str | None = None

    # Email digests through Resend. Both are needed; without them email stays off.
    # The sender must be on a domain verified in Resend, e.g. "Holdfast <brief@yourdomain.com>".
    resend_api_key: SecretStr | None = None
    email_from: str | None = Field(default=None, max_length=200)
    resend_api_base: str = "https://api.resend.com"

    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIRECTORY / "apps/backend/.env", API_DIRECTORY / ".env"),
        env_file_encoding="utf-8",
        env_prefix="CI_",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
