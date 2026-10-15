"""End-to-End (E2E) Full Pipeline Simulation Test for zioX."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet
from engine.grounding import GroundingEngine, FactCheckResult
from engine.orchestrator import BotOrchestrator
from engine.radar import DiscoveryRadar
from engine.link_validator import LinkValidator
from engine.humanizer import Humanizer


class SimulatedTwitterProvider(BaseTwitterProvider):
    """Simulates real-world Twitter network feed and reply tracking."""

    def __init__(self):
        now = datetime.now(timezone.utc)
        self.published_replies = []
        self.network_feed = [
            # 1. Candidate viral tweet with false aid claim
            Tweet(
                id="viral_aid_101",
                text="BREAKING: Israel has completely blocked all food and aid trucks into Gaza, creating pure famine!",
                author_handle="hostile_account_1",
                created_at=now - timedelta(minutes=20),
                likes=2500,
                retweets=850,
                replies=420,
                conversation_id="viral_aid_101"
            ),
            # 2. Low engagement tweet (below threshold)
            Tweet(
                id="low_engagement_102",
                text="Just another day of news in the Middle East.",
                author_handle="casual_user",
                created_at=now - timedelta(hours=2),
                likes=1,
                retweets=0,
                replies=0,
                conversation_id="low_engagement_102"
            ),
            # 3. Pure ad-hominem insult/trolling (should be filtered out by Grounding)
            Tweet(
                id="troll_tweet_103",
                text="You are all evil murderers and terrorists, shut up!",
                author_handle="troll_user",
                created_at=now - timedelta(minutes=15),
                likes=1200,
                retweets=300,
                replies=180,
                conversation_id="troll_tweet_103"
            )
        ]

    def search_recent_tweets(self, query: str, limit: int = 10):
        return self.network_feed

    def get_tweet(self, tweet_id: str):
        for t in self.network_feed:
            if t.id == tweet_id:
                return t
        return None

    def post_reply(self, text: str, reply_to_tweet_id: str, media_paths=None):
        reply_record = {
            "id": f"reply_to_{reply_to_tweet_id}",
            "reply_to": reply_to_tweet_id,
            "text": text,
            "char_length": Humanizer.calculate_tweet_length(text),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.published_replies.append(reply_record)
        return reply_record


def test_full_pipeline_radar_to_approval_and_publish(tmp_path, monkeypatch):
    """
    Simulates the COMPLETE end-to-end lifecycle:
    1. Discovery Radar scans network feed & enqueues viral candidate tweets into SQLite.
    2. Low-virality and duplicate tweets are properly filtered.
    3. Responder / Orchestrator pulls queued tweets.
    4. Evaluates thread permissions & toxicity.
    5. Runs Fact Grounding (rebutting false aid claims).
    6. LinkValidator validates attached link (ensures no dead link or bot challenge).
    7. Humanizer enforces 280-char Twitter limit and natural tone.
    8. Human-in-the-Loop approves ('a').
    9. Reply is dispatched and verified in SQLite as 'PUBLISHED' with valid link and <280 chars.
    """
    db_file = str(tmp_path / "e2e_full_lifecycle.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=False,  # Test real publishing flow
        virality_threshold=5.0,
        monthly_max_replies=30,
        max_thread_turns=2,
        search_keywords=["aid", "famine"]
    )

    provider = SimulatedTwitterProvider()

    # Step A: Run Discovery Radar
    radar = DiscoveryRadar(repo)
    discovered = radar.scan_keywords(
        provider=provider,
        keywords=settings.search_keywords,
        min_virality_score=settings.virality_threshold
    )

    # Only viral_aid_101 and troll_tweet_103 exceed threshold; low_engagement_102 is ignored
    assert len(discovered) == 2
    pending = repo.get_pending_tweets(limit=10)
    assert len(pending) == 2
    assert any(item["tweet_id"] == "viral_aid_101" for item in pending)

    # Step B: Setup Grounding Engine
    mock_grounding = MagicMock(spec=GroundingEngine)
    def mock_eval(text, author):
        if "blocked all food" in text.lower():
            return FactCheckResult(
                is_worth_replying=True,
                claim_identified="False claim that all aid was blocked",
                verified_facts=["Over 30,000 aid trucks entered via Kerem Shalom and Erez crossing."],
                # Supply a link to be tested through LinkValidator & Humanizer
                recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                draft_reply="Over 30,000 aid trucks and hundreds of thousands of tons of food have entered through official crossings like Kerem Shalom. Distribution bottlenecks happen inside the strip, not at the border."
            )
        else:
            # Troll tweet
            return FactCheckResult(
                is_worth_replying=False,
                claim_identified="Ad hominem abuse",
                draft_reply=""
            )

    mock_grounding.evaluate_and_draft.side_effect = mock_eval

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding
    )

    # Step C: Human-in-the-Loop review input simulation: user approves candidate ('a')
    monkeypatch.setattr("builtins.input", lambda prompt="": "a")

    # Step D: Execute Queue Processing
    report = orchestrator.process_queue(interactive=True)

    # Verify high-level execution report
    assert report["status"] == "SUCCESS"
    assert report["processed"] == 2
    assert report["replies_sent"] == 1  # 1 published, 1 skipped (troll)

    # Verify provider received the dispatched reply
    assert len(provider.published_replies) == 1
    dispatched = provider.published_replies[0]
    assert dispatched["reply_to"] == "viral_aid_101"

    # CRITICAL E2E CHECKS:
    # 1. Twitter length limit must NOT exceed 280
    assert dispatched["char_length"] <= 280
    # 2. Verified link is attached
    assert "https://govextra.gov.il/cogat/humanitarian-efforts/home/" in dispatched["text"]
    # 3. No robotic transition clichés
    assert "crucial to understand" not in dispatched["text"].lower()

    # Step E: Verify database final state
    with repo._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, was_published, reply_generated FROM processed_tweets WHERE tweet_id = 'viral_aid_101'")
        row_aid = cursor.fetchone()
        assert row_aid["status"] == "PUBLISHED"
        assert row_aid["was_published"] == 1
        assert "govextra.gov.il" in row_aid["reply_generated"]

        cursor.execute("SELECT status, was_published FROM processed_tweets WHERE tweet_id = 'troll_tweet_103'")
        row_troll = cursor.fetchone()
        assert row_troll["status"] == "SKIPPED"
        assert row_troll["was_published"] == 0

    # Step F: Queue should now have 0 DISCOVERED items
    assert len(repo.get_pending_tweets()) == 0
