"""Tests for Step 8B: Targeted Action and Queue Processing Responder."""

import pytest
from unittest.mock import MagicMock, patch
from config.settings import Settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from engine.grounding import GroundingEngine, FactCheckResult
from engine.orchestrator import BotOrchestrator
from engine.radar import DiscoveryRadar


@pytest.fixture
def mock_grounding():
    engine = MagicMock(spec=GroundingEngine)
    engine.evaluate_and_draft.return_value = FactCheckResult(
        claim_identified="Israel blocking all aid trucks to Gaza",
        is_worth_replying=True,
        verified_facts=["Over 25,000 aid trucks entered via COGAT coordinates"],
        draft_reply="Official records confirm over 25,000 aid trucks have entered through Kerem Shalom and Erez.",
        recommended_link="https://gaza-aid-data.gov.il"
    )
    return engine


@pytest.fixture
def test_setup(tmp_path, mock_grounding):
    db_file = str(tmp_path / "test_responder.db")
    repo = Repository(db_file)
    settings = Settings(
        gemini_api_key="test_key",
        database_path=db_file,
        dry_run=True,
        virality_threshold=5.0
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


def test_process_queue_dry_run(test_setup):
    """Verify processing candidate tweets from queue in dry-run mode."""
    repo, settings, provider, orchestrator, radar = test_setup

    # Enqueue a viral tweet
    radar.enqueue_manual(
        url_or_id="88889999",
        author_handle="claim_spreader",
        tweet_text="Israel blocking aid trucks into Gaza completely",
        likes=1000,
        retweets=400,
        replies=150
    )

    pending_before = repo.get_pending_tweets()
    assert len(pending_before) == 1

    report = orchestrator.process_queue(interactive=False)
    assert report["status"] == "SUCCESS"
    assert report["processed"] == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["tweet_id"] == "88889999"
    assert report["results"][0]["published"] is False  # dry-run

    # Pending queue should now be empty (status transitioned to PROCESSED_DRY_RUN)
    pending_after = repo.get_pending_tweets()
    assert len(pending_after) == 0


def test_process_specific_target_tweet(test_setup):
    """Verify targeting a single specific tweet directly via process_queue."""
    repo, settings, provider, orchestrator, radar = test_setup

    radar.enqueue_manual(
        url_or_id="77771111",
        author_handle="specific_poster",
        tweet_text="Another aid obstruction claim",
        likes=800,
        retweets=200,
        replies=90
    )

    report = orchestrator.process_queue(interactive=False, target_tweet_id="77771111")
    assert report["status"] == "SUCCESS"
    assert report["processed"] == 1
    assert report["results"][0]["tweet_id"] == "77771111"


def test_process_queue_live_publishing(test_setup):
    """Verify live reply publishing updates database status to PUBLISHED."""
    repo, settings, provider, orchestrator, radar = test_setup
    settings.dry_run = False  # Enable live mode

    radar.enqueue_manual(
        url_or_id="55554444",
        author_handle="user_live",
        tweet_text="Direct live test claim",
        likes=900,
        retweets=300,
        replies=100
    )

    report = orchestrator.process_queue(interactive=False, target_tweet_id="55554444")
    assert report["status"] == "SUCCESS"
    assert report["replies_sent"] == 1
    assert report["results"][0]["published"] is True
    assert len(provider.posted_replies) == 1
