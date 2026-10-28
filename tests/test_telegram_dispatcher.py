"""
Unit and integration tests for TelegramDispatcher and Web Intent workflow.
"""

import pytest
from unittest.mock import MagicMock, patch
import httpx
from datetime import datetime, timezone

from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet
from engine.grounding import GroundingEngine, FactCheckResult
from engine.orchestrator import BotOrchestrator
from engine.telegram_dispatcher import (
    build_x_web_intent_url,
    TelegramDispatcher,
)


class DummyMockProvider(BaseTwitterProvider):
    def __init__(self, sample_tweets=None):
        self.sample_tweets = sample_tweets or []

    def search_recent_tweets(self, query: str, limit: int = 10):
        return self.sample_tweets

    def get_tweet(self, tweet_id: str):
        for t in self.sample_tweets:
            if t.id == tweet_id:
                return t
        return None

    def post_reply(self, text: str, reply_to_tweet_id: str):
        return {"id": "mock_reply_999", "text": text, "in_reply_to": reply_to_tweet_id}


def test_build_x_web_intent_url_strict_percent_encoding():
    """Verify URL encoding uses %20 for spaces and preserves newlines without + signs."""
    text = "Hello World!\nChecking facts & truth #zioX"
    url = build_x_web_intent_url(tweet_id="123456789", reply_text=text)

    assert "in_reply_to=123456789" in url
    assert "text=" in url
    # Spaces must be %20, never +
    assert "+" not in url
    assert "Hello%20World%21" in url
    assert "%0A" in url  # newline
    assert "%26" in url  # &


def test_build_x_web_intent_url_multilingual():
    """Verify non-ASCII / Hebrew / Arabic text is properly percent encoded."""
    text = "בדיקת עובדות: שלום עולם\nفحص الحقائق"
    url = build_x_web_intent_url(tweet_id="987654", reply_text=text)

    assert "in_reply_to=987654" in url
    assert "%0A" in url
    # Ensure no raw unencoded whitespace
    assert " " not in url


def test_telegram_dispatcher_unconfigured():
    """When token or chat ID is missing, dispatcher reports is_configured=False and skips."""
    dispatcher = TelegramDispatcher(bot_token="", chat_ids="")
    assert not dispatcher.is_configured
    assert dispatcher.dispatch_review(
        tweet_id="1",
        author_handle="test",
        tweet_text="sample",
        virality_score=10.0,
        virality_tier="High",
        draft_reply="Reply",
    ) is False


def test_telegram_dispatcher_format_review_card():
    """Verify HTML card formatting properly escapes HTML special characters."""
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="12345")
    card = dispatcher.format_review_card(
        tweet_id="101",
        author_handle="@attacker<script>",
        tweet_text='Fake quote: "A & B < C > D"',
        virality_score=12.5,
        virality_tier="Critical",
        draft_reply="Verified: 1 < 2 & safe.",
        claim_flagged="Disinformation <alert>",
        verified_facts=["Fact 1 & reliable", "Fact 2 <verified>"],
    )

    assert "&lt;script&gt;" in card
    assert "<script>" not in card
    assert "&amp;" in card
    assert "Score: 12.5" in card
    assert "[Critical | Score: 12.5]" in card
    assert "📌 <b>Facts Cited:</b>" in card
    assert "<code>Verified: 1 &lt; 2 &amp; safe.</code>" in card


def test_telegram_dispatcher_dispatch_success():
    """Verify message payload sent to Telegram API includes InlineKeyboardMarkup."""
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="-100999, 888")
    assert dispatcher.is_configured
    assert len(dispatcher.chat_ids) == 2
    assert dispatcher.chat_ids == ["-100999", "888"]

    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as mock_client:
        success = dispatcher.dispatch_review(
            tweet_id="445566",
            author_handle="speaker",
            tweet_text="Viral statement",
            virality_score=8.5,
            virality_tier="High",
            draft_reply="Counter response",
            http_client=mock_client,
        )

    assert success is True
    assert len(captured_requests) == 2

    import json
    payload_1 = json.loads(captured_requests[0].content)
    assert payload_1["chat_id"] == "-100999"
    assert payload_1["parse_mode"] == "HTML"
    assert payload_1["disable_web_page_preview"] is True

    # Verify InlineKeyboardMarkup
    inline_kb = payload_1["reply_markup"]["inline_keyboard"]
    assert len(inline_kb) == 2
    assert inline_kb[0][0]["text"] == "🚀 צייץ תגובה ב-X"
    assert "https://x.com/intent/tweet?in_reply_to=445566" in inline_kb[0][0]["url"]
    assert inline_kb[1][0]["text"] == "👀 צפה בציוץ המקורי"


def test_telegram_dispatcher_http_error_handling():
    """Verify dispatcher logs error and returns False if Telegram API returns 400/500."""
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="12345")

    def mock_handler(request: httpx.Request):
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as mock_client:
        success = dispatcher.dispatch_review(
            tweet_id="11",
            author_handle="u",
            tweet_text="t",
            virality_score=6.0,
            virality_tier="Normal",
            draft_reply="r",
            http_client=mock_client,
        )

    assert success is False


def test_orchestrator_telegram_review_and_deduplication(tmp_path):
    """
    Integration Test:
    When telegram_review_enabled=True:
    1. Candidate reply is dispatched to Telegram with Web Intent.
    2. Tweet is saved to repository with status DISPATCHED_TELEGRAM.
    3. is_tweet_processed(tweet.id) is True, ensuring subsequent runs ignore it.
    """
    db_file = str(tmp_path / "test_telegram.db")
    repo = Repository(db_path=db_file)

    settings = Settings(
        database_path=db_file,
        telegram_bot_token="dummy_token",
        telegram_chat_id="12345",
        telegram_review_enabled=True,
        virality_threshold=2.0,
        dry_run=True,
    )

    viral_tweet = Tweet(
        id="viral_tweet_777",
        text="Significant narrative claim that needs fact-checking",
        author_handle="viral_user",
        created_at=datetime.now(timezone.utc),
        likes=500,
        retweets=100,
        replies=50,
        conversation_id="viral_tweet_777",
    )

    provider = DummyMockProvider(sample_tweets=[viral_tweet])

    mock_grounding = MagicMock(spec=GroundingEngine)
    mock_grounding.evaluate_and_draft.return_value = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Incorrect timeline",
        draft_reply="Official records show this claim is inaccurate. Check verified logs.",
        recommended_link="https://mfa.gov.il",
        verified_facts=["Fact A"],
    )

    mock_dispatcher = MagicMock(spec=TelegramDispatcher)
    mock_dispatcher.is_configured = True
    mock_dispatcher.dispatch_review.return_value = True

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding,
        telegram_dispatcher=mock_dispatcher,
    )

    # First cycle: should dispatch to Telegram
    report = orchestrator.run_cycle(interactive=False)

    assert report["status"] == "SUCCESS"
    assert report["replies_sent"] == 1
    assert len(report["results"]) == 1
    assert report["results"][0]["telegram_dispatched"] is True

    mock_dispatcher.dispatch_review.assert_called_once()

    # Verify deduplication record in DB
    assert repo.is_tweet_processed("viral_tweet_777") is True

    # Second cycle: viral_tweet_777 must be filtered out by is_tweet_processed!
    mock_dispatcher.reset_mock()
    second_report = orchestrator.run_cycle(interactive=False)

    assert second_report["replies_sent"] == 0
    assert len(second_report["results"]) == 0
    mock_dispatcher.dispatch_review.assert_not_called()
