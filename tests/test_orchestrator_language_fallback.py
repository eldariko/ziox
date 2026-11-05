"""Unit tests for language-aware Telegram review fallback dispatching in BotOrchestrator."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from engine.orchestrator import BotOrchestrator
from providers.base import Tweet
from engine.grounding import FactCheckResult


def test_fallback_dispatch_suppressed_when_admin_language_mismatches():
    """Verify that unassigned tweets in Arabic do not fall back to admin configured for English."""
    mock_repo = MagicMock()
    mock_telegram = MagicMock()
    mock_settings = MagicMock()
    mock_settings.target_cohort_size_per_tweet = 25
    mock_settings.max_unconfirmed_dispatches = 5
    mock_settings.no_link_variation_ratio = 0.0
    mock_settings.telegram_review_enabled = True

    # No eligible community subscribers
    mock_repo.get_active_subscribers.return_value = []
    mock_telegram.chat_ids = ["123456"]

    # Admin prefers English ('en')
    mock_repo.get_subscriber.return_value = {
        "chat_id": "123456",
        "preferred_lang": "en",
        "tier": "admin",
    }

    orchestrator = BotOrchestrator(
        settings=mock_settings,
        repository=mock_repo,
        provider=MagicMock(),
        grounding_engine=MagicMock(),
        telegram_dispatcher=mock_telegram,
    )

    arabic_tweet = Tweet(
        id="99901",
        text="تقرير جديد عن شاحنات المساعدات في قطاع غزة",
        author_handle="arabic_user",
        created_at=datetime.now(timezone.utc),
    )

    eval_result = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Fake claim",
        verified_facts=["Fact 1"],
        draft_reply="English reply draft",
    )

    dispatched, status, count = orchestrator._dispatch_to_telegram_community(
        tweet=arabic_tweet,
        virality_score=10.0,
        tier="HIGH",
        eval_result=eval_result,
        final_reply="English reply draft",
        effective_link=None,
    )

    # Dispatch to admin should be suppressed
    assert dispatched is False
    assert status == "DISPATCH_SUPPRESSED_LANGUAGE_MISMATCH"
    assert count == 0
    mock_telegram.dispatch_review.assert_not_called()


def test_fallback_dispatch_allowed_when_admin_language_matches():
    """Verify that unassigned tweets in English fall back to admin configured for English."""
    mock_repo = MagicMock()
    mock_telegram = MagicMock()
    mock_settings = MagicMock()
    mock_settings.target_cohort_size_per_tweet = 25
    mock_settings.max_unconfirmed_dispatches = 5
    mock_settings.no_link_variation_ratio = 0.0
    mock_settings.telegram_review_enabled = True

    mock_repo.get_active_subscribers.return_value = []
    mock_telegram.chat_ids = ["123456"]
    mock_telegram.dispatch_review.return_value = True

    mock_repo.get_subscriber.return_value = {
        "chat_id": "123456",
        "preferred_lang": "en",
        "tier": "admin",
    }

    orchestrator = BotOrchestrator(
        settings=mock_settings,
        repository=mock_repo,
        provider=MagicMock(),
        grounding_engine=MagicMock(),
        telegram_dispatcher=mock_telegram,
    )

    english_tweet = Tweet(
        id="99902",
        text="Breaking news regarding border aid convoys.",
        author_handle="news_user",
        created_at=datetime.now(timezone.utc),
    )

    eval_result = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Fake claim",
        verified_facts=["Fact 1"],
        draft_reply="English reply draft",
    )

    dispatched, status, count = orchestrator._dispatch_to_telegram_community(
        tweet=english_tweet,
        virality_score=10.0,
        tier="HIGH",
        eval_result=eval_result,
        final_reply="English reply draft",
        effective_link=None,
    )

    assert dispatched is True
    assert status == "DISPATCHED_TELEGRAM"
    assert count == 1
    mock_telegram.dispatch_review.assert_called_once()
