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
    api_token: SecretStr | None = None
    worker_timeout_seconds: int = Field(default=600, ge=10, le=1800)

    nebius_api_key: SecretStr | None = Field(default=None, validation_alias="NEBIUS_API_KEY")
    nebius_base_url: HttpUrl | None = Field(default=None, validation_alias="NEBIUS_BASE_URL")
    nebius_model: str | None = Field(default=None, min_length=1, validation_alias="NEBIUS_MODEL")

    model_config = SettingsConfigDict(
        env_file=API_DIRECTORY / ".env",
        env_file_encoding="utf-8",
        env_prefix="CI_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
