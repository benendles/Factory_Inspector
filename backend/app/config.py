"""Configuration for Factory Inspector."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    app_name: str = "Factory Inspector API"
    app_version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()