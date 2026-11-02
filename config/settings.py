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

    # Telegram Review & Web Intent Dispatcher
    telegram_bot_token: str = Field(default="", description="Telegram Bot API token for review alerts")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID, channel ID (-100...), or comma-separated list of IDs")
    telegram_review_enabled: bool = Field(default=False, description="When True, send review cards to Telegram")

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
    max_replies_per_cycle: int = Field(default=2, description="Maximum direct replies published per single scan or queue run")
    min_reply_delay_seconds: float = Field(default=35.0, description="Minimum human hesitation pause in seconds")
    max_reply_delay_seconds: float = Field(default=85.0, description="Maximum human hesitation pause in seconds")
    link_cooldown_minutes: int = Field(default=60, description="Minutes to wait before reusing the exact same proof URL")
    start_jitter_max_minutes: float = Field(default=15.0, description="Maximum random start delay in minutes for external schedulers")

    # Phase A: Scanner Safety Shield & Boolean OR Query Consolidation
    combine_search_queries: bool = Field(
        default=True,
        description="When True, group search keywords into combined Boolean OR queries by script"
    )
    max_keywords_per_query: int = Field(
        default=6,
        description="Maximum keywords combined into a single Boolean OR search query"
    )
    min_search_delay_seconds: float = Field(
        default=6.0,
        description="Minimum Gaussian jitter delay in seconds between consecutive X search queries"
    )
    max_search_delay_seconds: float = Field(
        default=15.0,
        description="Maximum Gaussian jitter delay in seconds between consecutive X search queries"
    )
    search_min_faves: int = Field(
        default=0,
        description="Minimum likes filter in search query (e.g. 5) to filter out 0-engagement noise"
    )
    max_tweet_age_hours: float = Field(
        default=24.0,
        description="Maximum age in hours for discovered candidate tweets (default 24h)"
    )
    scanner_cooldown_minutes: int = Field(
        default=720,
        description="Minutes to quarantine the X scanner account if a rate-limit (429) or auth challenge (401/403) occurs"
    )

    # Phase B & Scale-1000: Multi-Variation AI Grounding & Horizontal Cohort Sharding
    variations_per_tweet: int = Field(
        default=4,
        description="Default number of distinct reply variations generated per viral tweet"
    )
    max_variations_per_gemini_call: int = Field(
        default=10,
        description="Maximum distinct reply variations requested in a single Gemini structured JSON call"
    )
    target_cohort_size_per_tweet: int = Field(
        default=25,
        description="Maximum eligible subscribers assigned to a single viral tweet wave per cycle (Horizontal Cohort Sharding)"
    )
    telegram_tweets_per_cycle: int = Field(
        default=10,
        description="Maximum viral tweets processed and sharded across Telegram subscribers in a single cycle"
    )
    no_link_variation_ratio: float = Field(
        default=0.4,
        description="Proportion of cohort reply variations (0.0 to 1.0) formatted as pure text without an attached URL"
    )
    max_user_daily_limit: int = Field(
        default=5,
        description="Central ceiling for a regular subscriber's self-configured daily quota (/limit <number>)"
    )
    max_unconfirmed_dispatches: int = Field(
        default=5,
        description="Maximum consecutive unconfirmed dispatches before auto-pausing an unresponsive subscriber"
    )

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
