from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet
from engine.grounding import FactCheckResult
from engine.orchestrator import BotOrchestrator


class MockProviderForInteractive(BaseTwitterProvider):
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.mock_tweets = [
            Tweet(
                id="tweet_approve_1",
                text="Israel completely stopped all food aid trucks into Gaza.",
                author_handle="claim_user_1",
                created_at=now - timedelta(minutes=15),
                likes=500,
                retweets=200,
                replies=80
            ),
            Tweet(
                id="tweet_edit_2",
                text="Israel blocked food aid completely.",
                author_handle="claim_user_2",
                created_at=now - timedelta(minutes=10),
                likes=400,
                retweets=150,
                replies=50
            ),
            Tweet(
                id="tweet_skip_3",
                text="Another false aid claim.",
                author_handle="claim_user_3",
                created_at=now - timedelta(minutes=5),
                likes=300,
                retweets=100,
                replies=40
            )
        ]

    def search_recent_tweets(self, query: str, limit: int = 10):
        return self.mock_tweets

    def post_reply(self, text: str, reply_to_tweet_id: str, media_paths=None):
        return {"id": "reply_123", "text": text}

    def get_tweet(self, tweet_id: str):
        return None


def test_interactive_approval(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_interactive.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=True,
        search_keywords=["aid"]
    )
    provider = MockProviderForInteractive()
    grounding = MagicMock()
    grounding.evaluate_and_draft.return_value = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Claim that food aid was stopped",
        verified_facts=["Over 30,000 trucks entered"],
        recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
        draft_reply="Over 30,000 trucks have crossed into Gaza through Kerem Shalom."
    )

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=grounding
    )

    # Simulate user answering: 'a' (approve first), 'e' then custom text (second), 's' (skip third)
    inputs = iter(["a", "e", "Custom human edited response.", "s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    report = orchestrator.run_cycle(interactive=True)
    assert report["status"] == "SUCCESS"
    assert len(report["results"]) == 2  # approved + edited (skipped is not in published results)
    assert "Custom human edited response." in report["results"][1]["reply"]
