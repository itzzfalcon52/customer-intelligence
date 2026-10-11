from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIRECTORY = Path(__file__).resolve().parents[3]
PROJECT_DIRECTORY = API_DIRECTORY.parent.parent


class Settings(BaseSettings):
    app_name: str = "Customer Intelligence API"
    service_name: str = "customer-intelligence-api"
    environment: Literal["development", "test", "production"] = "development"
    data_directory: Path = PROJECT_DIRECTORY / ".data"

    model_config = SettingsConfigDict(
        env_file=API_DIRECTORY / ".env",
        env_file_encoding="utf-8",
        env_prefix="CI_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()