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
    gemini_search_grounding: bool = Field(default=False, description="Enable Google Search Grounding (requires billing/quota)")
    zernio_api_key: str = Field(default="", description="Zernio API Key")
    zernio_twitter_account_id: str = Field(default="", description="Zernio connected X Account ID")

    # X / Twitter Session Authentication
    x_auth_token: str = Field(default="", description="X session auth_token cookie")
    x_ct0: str = Field(default="", description="X session ct0 CSRF token cookie")
    x_cookies_file: str = Field(default="cookies.json", description="Path to saved X cookies JSON file")

    # Bot Execution Mode
    dry_run: bool = Field(default=True, description="When True, no live posts are sent to X")
    twitter_provider: str = Field(default="mock", description="'mock', 'zernio', or 'twikit'")
    database_path: str = Field(default="ziox.db", description="Path to local SQLite database file")

    # Turso Cloud SQLite Configuration
    turso_database_url: str = Field(default="", description="Turso database URL (e.g. libsql://... or https://...)")
    turso_auth_token: str = Field(default="", description="Turso auth token for remote database connection")

    # Scoring & Quotas
    virality_threshold: float = Field(default=5.0, description="Minimum virality score to trigger evaluation")
    monthly_max_replies: int = Field(default=30, description="Maximum total replies per month")
    max_thread_turns: int = Field(default=2, description="Maximum turns per thread before disengaging")

    # Anti-Ban Stealth Pacing & Rate Limits
    max_replies_per_cycle: int = Field(default=2, description="Maximum replies dispatched per single scan or queue run")
    min_reply_delay_seconds: float = Field(default=35.0, description="Minimum human hesitation pause in seconds")
    max_reply_delay_seconds: float = Field(default=85.0, description="Maximum human hesitation pause in seconds")
    link_cooldown_minutes: int = Field(default=60, description="Minutes to wait before reusing the exact same proof URL")
    start_jitter_max_minutes: float = Field(default=15.0, description="Maximum random start delay in minutes for external schedulers")

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
