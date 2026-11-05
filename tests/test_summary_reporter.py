"""Tests for SummaryReporter and GitHub Actions Step Summary generation."""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from config.settings import Settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from engine.grounding import GroundingEngine, FactCheckResult, DraftVariation
from engine.orchestrator import BotOrchestrator
from engine.radar import DiscoveryRadar
from engine.telegram_dispatcher import TelegramDispatcher, mask_chat_id_for_display
from engine.link_validator import LinkValidator
from engine.summary_reporter import SummaryReporter


@pytest.fixture
def test_env(tmp_path):
    db_file = str(tmp_path / "test_summary.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=True,
        virality_threshold=5.0,
        monthly_max_replies=30,
        telegram_review_enabled=True,
        telegram_bot_token="123456:TEST_TOKEN",
        telegram_chat_id="999000",
        search_keywords=["Israel", "Gaza", "إسرائيل"],
    )
    # Register subscribers
    repo.upsert_subscriber(chat_id="999000", username="operator_admin", tier="admin", daily_limit=100)
    repo.upsert_subscriber(chat_id="8703905871", username="advocate_user", tier="free", daily_limit=5)
    return repo, settings


def test_mask_chat_id_for_display():
    """Verify chat IDs are masked so GitHub Actions secret regex does not censor to '***'."""
    admin_display = mask_chat_id_for_display("999000", username="operator_admin", tier="admin")
    assert admin_display == "Admin (..9000)"

    user_display = mask_chat_id_for_display("8703905871", username="advocate_user", tier="free")
    assert user_display == "@advocate_user (..5871)"

    anon_display = mask_chat_id_for_display("12345", username="", tier="free")
    assert anon_display == "User (..2345)"


def test_generate_markdown_structure(test_env):
    """Verify all 5 required dashboard sections, Mermaid diagram, and tables are generated."""
    repo, settings = test_env

    # Seed mock link cache
    LinkValidator._cache = {
        "https://www.idf.mil": (False, 0),
        "https://www.gov.il/cogat": (False, 403),
        "https://govextra.gov.il/cogat/home": (True, 200),
    }

    sample_report = {
        "status": "SUCCESS",
        "discovered_count": 15,
        "processed": 10,
        "replies_sent": 8,
        "subscribers_served": 12,
        "demand": {"total": 2, "en": 2, "ar": 0},
        "radar_scan_stats": {
            "queries": [
                {
                    "query": '("Israel" OR "Gaza")',
                    "raw_count": 20,
                    "skipped_age": 2,
                    "skipped_already_processed": 8,
                    "skipped_low_virality": 1,
                    "enqueued_count": 9,
                },
                {
                    "query": '("إسرائيل")',
                    "raw_count": 14,
                    "skipped_age": 1,
                    "skipped_already_processed": 5,
                    "skipped_low_virality": 2,
                    "enqueued_count": 6,
                },
            ],
            "total_raw": 34,
            "total_skipped_age": 3,
            "total_skipped_already_processed": 13,
            "total_skipped_low_virality": 3,
            "total_enqueued": 15,
        },
        "evaluations": [
            {
                "tweet_id": "2117623231855181863",
                "author": "ABO_Watan9",
                "virality_score": 44.56,
                "tier": "Mega-Viral",
                "decision": "APPROVED",
                "claim": "IDF soldiers target unarmed civilians for amusement",
                "facts": ["Hamas systematically uses civilian infrastructure"],
                "link": "https://govextra.gov.il/cogat/home",
                "status": "DISPATCHED_TELEGRAM",
            },
            {
                "tweet_id": "2117690620869247264",
                "author": "critic_user",
                "virality_score": 30.52,
                "tier": "Viral",
                "decision": "SKIPPED",
                "reason": "Factual claim missing or unsupported",
                "claim": "General political rant",
                "facts": [],
                "link": None,
                "status": "SKIPPED",
            },
        ],
        "pending_before_count": 15,
        "pending_after_count": 5,
        "pending_after_items": [
            {
                "tweet_id": "2117999999",
                "author_handle": "queued_author",
                "virality_score": 10.5,
                "tweet_text": "Sample queued tweet text waiting in database",
            }
        ],
        "dispatches": [
            {
                "tweet_id": "2117623231855181863",
                "author_handle": "ABO_Watan9",
                "chat_id": "999000",
                "username": "operator_admin",
                "tier": "admin",
                "preferred_lang": "en",
                "style": "factual",
                "draft_reply": "Hamas systematically uses civilian infrastructure.",
                "link": "https://govextra.gov.il/cogat/home",
                "is_fallback": False,
            },
            {
                "tweet_id": "2117623231855181863",
                "author_handle": "ABO_Watan9",
                "chat_id": "8703905871",
                "username": "advocate_user",
                "tier": "free",
                "preferred_lang": "en",
                "style": "sharp",
                "draft_reply": "Claiming zero aid enters while 25,000+ trucks crossed ignores basic records.",
                "link": None,
                "is_fallback": False,
            },
        ],
    }

    markdown = SummaryReporter.generate_markdown(sample_report, settings, repo)

    # 1. Header & Badges
    assert "# 📊 zioX Pipeline Execution Report" in markdown
    assert "🟢 **SUCCESS**" in markdown
    assert "Turso Cloud" in markdown or "Local SQLite" in markdown

    # 2. Key Metrics Cards
    assert "| 📡 Discovered Tweets | ⚙️ Tweets Evaluated | 🚀 Dispatched Waves |" in markdown
    assert "**`15`**" in markdown
    assert "**`10`**" in markdown
    assert "**`8`**" in markdown
    assert "**`12`**" in markdown

    # 3. Parameters
    assert "### 🎛️ 1. Execution Parameters & Dynamic Sizing" in markdown
    assert "Available Demand" in markdown
    assert "Dynamic Search Limit" in markdown

    # 4. Radar Funnel
    assert "### 📡 2. Radar Discovery & Ingestion Funnel" in markdown
    assert "```mermaid" in markdown
    assert "flowchart LR" in markdown
    assert "Raw X Posts" in markdown
    assert '("Israel" OR "Gaza")' in markdown

    # 5. Queue State & AI Decisions
    assert "### 🧠 3. Queue State & AI Fact-Checking Decisions" in markdown
    assert "2117623231855181863" in markdown
    assert "✅ **Approved**" in markdown
    assert "❌ **Skipped**" in markdown
    assert "Factual claim missing or unsupported" in markdown
    assert "<details>" in markdown
    assert "Candidate Tweets Preserved in Queue" in markdown

    # 6. Dispatches
    assert "### 📬 4. Telegram Community Dispatch Matrix" in markdown
    assert "Admin (..9000)" in markdown
    assert "@advocate_user (..5871)" in markdown
    assert "🎯 `factual`" in markdown
    assert "⚡ `sharp`" in markdown

    # 7. Link Audit
    assert "### 🌐 5. Link Health & Whitelist Audit" in markdown
    assert "https://www.idf.mil" in markdown
    assert "https://www.gov.il/cogat" in markdown
    assert "HTTP 403" in markdown
    assert "Healthy (Substantive Article)" in markdown


def test_write_step_summary_file(tmp_path, test_env):
    """Verify write_step_summary writes properly to a file target and GITHUB_STEP_SUMMARY."""
    repo, settings = test_env
    out_file = str(tmp_path / "step_summary.md")

    sample_report = {"status": "SUCCESS", "discovered_count": 0, "processed": 0, "replies_sent": 0}
    written = SummaryReporter.generate_and_publish(
        run_report=sample_report,
        settings=settings,
        repository=repo,
        target_file=out_file,
    )

    assert written == out_file
    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "# 📊 zioX Pipeline Execution Report" in content


def test_pipeline_e2e_generates_summary(tmp_path, monkeypatch, test_env):
    """Verify run_full_pipeline automatically writes to GITHUB_STEP_SUMMARY when configured."""
    repo, settings = test_env
    summary_file = str(tmp_path / "github_summary.md")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", summary_file)

    mock_grounding = MagicMock(spec=GroundingEngine)
    sample_res = FactCheckResult(
        claim_identified="Fake test claim",
        is_worth_replying=True,
        verified_facts=["Documented fact"],
        draft_reply="Clear factual response.",
        draft_variations=[DraftVariation(style="factual", text="Clear factual response.")],
    )
    mock_grounding.evaluate_and_draft.return_value = sample_res
    mock_grounding.generate_variations_batch.return_value = sample_res

    provider = MockTwitterProvider()
    mock_dispatcher = MagicMock(spec=TelegramDispatcher)
    mock_dispatcher.is_configured = True
    mock_dispatcher.sync_subscribers.return_value = 0
    mock_dispatcher.get_last_dispatches.return_value = [
        {
            "tweet_id": "999111",
            "author_handle": "critic",
            "chat_id": "999000",
            "username": "operator_admin",
            "tier": "admin",
            "preferred_lang": "en",
            "style": "factual",
            "draft_reply": "Clear factual response.",
            "link": None,
            "is_fallback": True,
        }
    ]

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding,
        telegram_dispatcher=mock_dispatcher,
    )

    radar = DiscoveryRadar(repo)
    # Enqueue a tweet
    radar.enqueue_manual(
        url_or_id="999111",
        author_handle="critic",
        tweet_text="False aid assertion",
        likes=500,
        retweets=200,
        replies=100
    )

    report = orchestrator.run_full_pipeline(radar=radar, start_jitter_minutes=0.0, interactive=False)
    assert report["status"] == "SUCCESS"
    assert "evaluations" in report
    assert "pending_after_count" in report

    # Verify GITHUB_STEP_SUMMARY file was generated and populated
    assert os.path.exists(summary_file)
    with open(summary_file, "r", encoding="utf-8") as f:
        summary_content = f.read()

    assert "# 📊 zioX Pipeline Execution Report" in summary_content
    assert "Admin (..9000)" in summary_content
    assert "999111" in summary_content
