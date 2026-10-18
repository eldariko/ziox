"""Tests for Step 10: External Scheduler & Unified Pipeline Architecture."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from config.settings import Settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from providers.base import Tweet
from engine.grounding import GroundingEngine, FactCheckResult
from engine.orchestrator import BotOrchestrator
from engine.radar import DiscoveryRadar


@pytest.fixture
def mock_grounding():
    engine = MagicMock(spec=GroundingEngine)
    engine.evaluate_and_draft.return_value = FactCheckResult(
        claim_identified="False blockade claim",
        is_worth_replying=True,
        verified_facts=["Over 28,000 aid trucks crossed into Gaza."],
        draft_reply="Official records confirm over 28,000 aid trucks entered Gaza through Kerem Shalom and Erez.",
        recommended_link="https://gaza-aid-data.gov.il"
    )
    return engine


@pytest.fixture
def test_setup(tmp_path, mock_grounding):
    db_file = str(tmp_path / "test_scheduler.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=True,
        virality_threshold=5.0,
        monthly_max_replies=30,
        max_replies_per_cycle=2,
        min_reply_delay_seconds=0.0,
        max_reply_delay_seconds=0.0,
        start_jitter_max_minutes=10.0,
        search_keywords=["Gaza", "Israel"]
    )
    provider = MockTwitterProvider()
    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding
    )
    radar = DiscoveryRadar(repo)
    return repo, settings, provider, orchestrator, radar


def test_pipeline_executes_radar_then_responder(test_setup):
    """Verify run_full_pipeline drives Discovery Radar and then processes candidate queue."""
    repo, settings, provider, orchestrator, radar = test_setup
    now = datetime.now(timezone.utc)

    # Populate provider with candidate viral tweets for radar
    provider.search_results = [
        Tweet(
            id="pipe_tweet_101",
            text="Breaking: Complete aid cutoff reported in Gaza",
            author_handle="news_source_1",
            created_at=now - timedelta(minutes=15),
            likes=2000, retweets=800, replies=300,
            conversation_id="pipe_tweet_101"
        ),
        Tweet(
            id="pipe_tweet_102",
            text="Another viral post regarding Gaza food supply",
            author_handle="news_source_2",
            created_at=now - timedelta(minutes=20),
            likes=1500, retweets=600, replies=200,
            conversation_id="pipe_tweet_102"
        )
    ]

    report = orchestrator.run_full_pipeline(
        radar=radar,
        start_jitter_minutes=0.0,
        interactive=False
    )

    assert report["status"] == "SUCCESS"
    assert report["discovered_count"] >= 1
    assert report["replies_sent"] >= 1
    assert report["processed"] >= 1
    assert len(report["results"]) >= 1

    # Verify audit log was recorded in database
    recent_logs = repo.get_recent_logs(limit=1)
    assert len(recent_logs) == 1
    assert recent_logs[0]["status"] == "SUCCESS"


def test_pipeline_respects_monthly_reply_ceiling(test_setup):
    """Verify run_full_pipeline halts immediately without calling radar when monthly quota is reached."""
    repo, settings, provider, orchestrator, radar = test_setup
    settings.monthly_max_replies = 10

    # Simulate 10 published replies already recorded in DB this month
    for i in range(10):
        repo.save_processed_tweet(
            tweet_id=f"past_published_{i}",
            author_handle=f"user_{i}",
            tweet_text="Past tweet",
            virality_score=10.0,
            reply_generated="Past reply",
            was_published=True,
            status="PUBLISHED"
        )

    assert repo.get_monthly_reply_count() == 10

    mock_radar = MagicMock(spec=DiscoveryRadar)

    report = orchestrator.run_full_pipeline(
        radar=mock_radar,
        start_jitter_minutes=0.0
    )

    assert report["status"] == "QUOTA_EXCEEDED"
    assert report["replies_sent"] == 0
    assert report["processed"] == 0
    # Radar should NOT even have been called
    assert mock_radar.scan_keywords.call_count == 0

    # Verify audit log
    logs = repo.get_recent_logs(limit=1)
    assert len(logs) == 1
    assert logs[0]["status"] == "ABORTED_QUOTA_EXCEEDED"


def test_pipeline_applies_start_jitter(tmp_path):
    """Verify start jitter pause is applied in live mode and skipped in dry-run mode."""
    db_file = str(tmp_path / "jitter_test.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=False,  # Live mode
        start_jitter_max_minutes=5.0
    )
    provider = MockTwitterProvider()
    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=MagicMock()
    )
    radar = MagicMock()
    radar.scan_keywords.return_value = []

    # In live mode with 5 min jitter, sleep should be called with 0 <= sleep_sec <= 300
    with patch("time.sleep") as mock_sleep:
        orchestrator.run_full_pipeline(radar=radar, start_jitter_minutes=5.0)
        assert mock_sleep.call_count == 1
        sleep_sec = mock_sleep.call_args[0][0]
        assert 0.0 <= sleep_sec <= 300.0

    # In dry_run mode, sleep should NOT be called
    settings.dry_run = True
    with patch("time.sleep") as mock_sleep:
        orchestrator.run_full_pipeline(radar=radar, start_jitter_minutes=5.0)
        assert mock_sleep.call_count == 0


def test_pipeline_handles_radar_exception_gracefully(test_setup):
    """Verify exceptions during Discovery Radar scan are safely logged to DB and do not crash."""
    repo, settings, provider, orchestrator, radar = test_setup

    mock_radar = MagicMock(spec=DiscoveryRadar)
    mock_radar.scan_keywords.side_effect = ConnectionError("X search rate limit 429")

    report = orchestrator.run_full_pipeline(
        radar=mock_radar,
        start_jitter_minutes=0.0
    )

    assert report["status"] == "RADAR_ERROR"
    assert "429" in report["details"]

    logs = repo.get_recent_logs(limit=1)
    assert len(logs) == 1
    assert logs[0]["status"] == "RADAR_ERROR"
    assert "429" in logs[0]["error_message"]
