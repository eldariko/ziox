import os
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and configuration."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API Keys & Models
    gemini_api_key: str = Field(default="", description="Google Gemini API Key")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", description="Gemini Model Name")
    zernio_api_key: str = Field(default="", description="Zernio API Key")
    zernio_twitter_account_id: str = Field(default="", description="Zernio connected X Account ID")

    # Bot Execution Mode
    dry_run: bool = Field(default=True, description="When True, no live posts are sent to X")
    twitter_provider: str = Field(default="mock", description="'mock' or 'zernio'")
    database_path: str = Field(default="ziox.db", description="Path to SQLite database file")

    # Scoring & Quotas
    virality_threshold: float = Field(default=5.0, description="Minimum virality score to trigger evaluation")
    monthly_max_replies: int = Field(default=30, description="Maximum total replies per month")
    max_thread_turns: int = Field(default=2, description="Maximum turns per thread before disengaging")

    # Keywords for X search (English and Arabic)
    search_keywords: List[str] = Field(
        default=[
            "Israel",
            "Gaza",
            "IDF",
            "Zionism",
            "Hostages",
            "Middle East",
            "إسرائيل",
            "غزة",
            "مساعدات غزة"
        ]
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()
