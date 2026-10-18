"""Tests for Step 9: Anti-Ban Stealth Pacing, Rate Limiting, and Link Diversity."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from config.settings import Settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from providers.base import Tweet
from engine.grounding import GroundingEngine, FactCheckResult
from engine.orchestrator import BotOrchestrator, calculate_gaussian_jitter
from engine.radar import DiscoveryRadar


@pytest.fixture
def mock_grounding():
    engine = MagicMock(spec=GroundingEngine)
    engine.evaluate_and_draft.return_value = FactCheckResult(
        claim_identified="False aid blockade claim",
        is_worth_replying=True,
        verified_facts=["Over 30,000 trucks entered Gaza via Kerem Shalom."],
        draft_reply="Verified aid records show over 30,000 trucks entered Gaza via Kerem Shalom.",
        recommended_link="https://gaza-aid-data.gov.il"
    )
    return engine


@pytest.fixture
def test_setup(tmp_path, mock_grounding):
    db_file = str(tmp_path / "test_stealth.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=True,
        virality_threshold=5.0,
        max_replies_per_cycle=2,
        min_reply_delay_seconds=35.0,
        max_reply_delay_seconds=85.0,
        link_cooldown_minutes=60
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


def test_calculate_gaussian_jitter_bounds_and_distribution():
    """Verify Gaussian jitter generates values bounded within min and max, centered near mean."""
    min_delay = 35.0
    max_delay = 85.0
    samples = [calculate_gaussian_jitter(min_delay, max_delay) for _ in range(200)]

    for val in samples:
        assert min_delay <= val <= max_delay

    avg = sum(samples) / len(samples)
    expected_mid = (min_delay + max_delay) / 2.0
    assert abs(avg - expected_mid) < 5.0  # within reasonable sampling variance

    # Edge case: min >= max
    assert calculate_gaussian_jitter(50.0, 50.0) == 50.0


def test_link_diversity_cooldown_throttles_duplicate_url(test_setup):
    """Verify that posting a URL marks it recently posted, and subsequent replies drop the repeated link."""
    repo, settings, provider, orchestrator, radar = test_setup
    test_link = "https://gaza-aid-data.gov.il"

    # Initially not posted
    assert repo.is_link_recently_posted(test_link, cooldown_minutes=60) is False

    # Save a processed tweet with this link in dry run
    repo.save_processed_tweet(
        tweet_id="initial_tweet_001",
        author_handle="poster1",
        tweet_text="Sample aid claim",
        virality_score=10.0,
        reply_generated="Verified rebuttal",
        link_attached=test_link,
        was_published=False,
        status="PROCESSED_DRY_RUN"
    )

    # Now repo recognizes it as recently posted
    assert repo.is_link_recently_posted(test_link, cooldown_minutes=60, include_dry_run=True) is True

    # Orchestrator should suppress this URL to enforce domain diversity
    resolved = orchestrator._resolve_diverse_link(test_link, "Some claim about aid")
    assert resolved is None

    # An unrelated, diverse link should not be suppressed
    diverse_link = "https://mfa.gov.il/fact-sheet"
    assert orchestrator._resolve_diverse_link(diverse_link, "Different context") == diverse_link


def test_process_queue_enforces_per_cycle_reply_cap(test_setup):
    """Verify queue processor halts when max_replies_per_cycle is reached, leaving remaining items pending."""
    repo, settings, provider, orchestrator, radar = test_setup

    # Enqueue 5 viral candidate tweets
    for i in range(1, 6):
        radar.enqueue_manual(
            url_or_id=f"viral_tweet_{i}",
            author_handle=f"user_{i}",
            tweet_text=f"False claim number {i} regarding aid supplies",
            likes=1000 + i * 100,
            retweets=500,
            replies=200
        )

    pending_before = repo.get_pending_tweets(limit=10)
    assert len(pending_before) == 5

    # Process queue with cap of 2
    report = orchestrator.process_queue(interactive=False, limit=10)

    assert report["status"] == "SUCCESS"
    assert report["replies_sent"] == 2
    assert report["processed"] == 2
    assert len(report["results"]) == 2

    # Exactly 3 tweets should still remain in the DISCOVERED queue for the next cycle
    pending_after = repo.get_pending_tweets(limit=10)
    assert len(pending_after) == 3


def test_run_cycle_enforces_per_cycle_reply_cap(test_setup):
    """Verify run_cycle halts when max_replies_per_cycle is reached even if more viral tweets exist."""
    repo, settings, provider, orchestrator, radar = test_setup
    now = datetime.now(timezone.utc)

    # Populate provider with 4 viral tweets matching keywords
    provider.search_results = [
        Tweet(
            id=f"stream_tweet_{i}",
            text=f"Israel blocking all supplies {i}",
            author_handle=f"stream_user_{i}",
            created_at=now - timedelta(minutes=10 * i),
            likes=3000,
            retweets=1000,
            replies=400,
            conversation_id=f"stream_tweet_{i}"
        )
        for i in range(1, 5)
    ]

    report = orchestrator.run_cycle(interactive=False)

    assert report["status"] == "SUCCESS"
    assert report["replies_sent"] == 2
    assert len(report["results"]) == 2


def test_stealth_delay_invoked_between_consecutive_replies(test_setup):
    """Verify live mode triggers human hesitation sleep between consecutive replies but not before the first."""
    repo, settings, provider, orchestrator, radar = test_setup
    settings.dry_run = False  # Enable live mode
    settings.min_reply_delay_seconds = 40.0
    settings.max_reply_delay_seconds = 70.0

    # Enqueue 2 tweets
    radar.enqueue_manual(
        url_or_id="live_pacing_1",
        author_handle="live_user_1",
        tweet_text="Claim 1 needing live response",
        likes=1200, retweets=400, replies=150
    )
    radar.enqueue_manual(
        url_or_id="live_pacing_2",
        author_handle="live_user_2",
        tweet_text="Claim 2 needing live response",
        likes=1400, retweets=450, replies=160
    )

    with patch("time.sleep") as mock_sleep:
        report = orchestrator.process_queue(interactive=False, limit=5)

        assert report["status"] == "SUCCESS"
        assert report["replies_sent"] == 2

        # time.sleep should be called exactly once: before the 2nd reply
        assert mock_sleep.call_count == 1
        sleep_arg = mock_sleep.call_args[0][0]
        assert 40.0 <= sleep_arg <= 70.0


def test_stealth_delay_skipped_in_dry_run(test_setup):
    """Verify that in dry_run mode, time.sleep is never called."""
    repo, settings, provider, orchestrator, radar = test_setup
    settings.dry_run = True

    radar.enqueue_manual(
        url_or_id="dry_pacing_1", author_handle="u1", tweet_text="Aid claim 1",
        likes=1000, retweets=300, replies=100
    )
    radar.enqueue_manual(
        url_or_id="dry_pacing_2", author_handle="u2", tweet_text="Aid claim 2",
        likes=1000, retweets=300, replies=100
    )

    with patch("time.sleep") as mock_sleep:
        report = orchestrator.process_queue(interactive=False, limit=5)
        assert report["replies_sent"] == 2
        assert mock_sleep.call_count == 0
