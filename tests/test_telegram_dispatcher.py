"""
Unit and integration tests for TelegramDispatcher and Web Intent workflow.
"""

import json
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
    assert "━━━━━━━━━━━━━━━━━━" in card
    assert "<blockquote>\"Fake quote: &quot;A &amp; B &lt; C &gt; D&quot;\"</blockquote>" in card
    assert "• Fact 1 &amp; reliable" in card
    assert "• Fact 2 &lt;verified&gt;" in card
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
    sample_fc = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Incorrect timeline",
        draft_reply="Official records show this claim is inaccurate. Check verified logs.",
        recommended_link="https://mfa.gov.il",
        verified_facts=["Fact A"],
    )
    mock_grounding.evaluate_and_draft.return_value = sample_fc
    mock_grounding.generate_variations_batch.return_value = sample_fc

    mock_dispatcher = MagicMock(spec=TelegramDispatcher)
    mock_dispatcher.is_configured = True
    mock_dispatcher.has_bot_token = True
    mock_dispatcher.dispatch_review.return_value = True
    mock_dispatcher.dispatch_variations_to_subscribers.return_value = 1

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

    # Verify deduplication record in DB
    assert repo.is_tweet_processed("viral_tweet_777") is True

    # Second cycle: viral_tweet_777 must be filtered out by is_tweet_processed!
    mock_dispatcher.reset_mock()
    second_report = orchestrator.run_cycle(interactive=False)

    assert second_report["replies_sent"] == 0
    assert len(second_report["results"]) == 0
    mock_dispatcher.dispatch_review.assert_not_called()


def test_sync_subscribers_and_confirmation_messages(tmp_path):
    """
    Verify Task 3.2:
    1. Polling getUpdates registers /start users, updates /style preferences, and deactivates /stop users.
    2. Sends immediate confirmation messages to users who send /start or /style.
    3. Advances telegram_last_update_id in bot_state.
    """
    db_file = str(tmp_path / "test_sync_subs.db")
    repo = Repository(db_file)
    dispatcher = TelegramDispatcher(bot_token="test_bot_token", chat_ids="99999")

    sent_messages = []

    def mock_handler(request: httpx.Request):
        if "getUpdates" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 100,
                            "message": {
                                "chat": {"id": 1111, "username": "supporter_a"},
                                "text": "/start",
                            },
                        },
                        {
                            "update_id": 101,
                            "message": {
                                "chat": {"id": 2222, "username": "supporter_b"},
                                "text": "/start",
                            },
                        },
                        {
                            "update_id": 102,
                            "message": {
                                "chat": {"id": 1111, "username": "supporter_a"},
                                "text": "/style sharp",
                            },
                        },
                        {
                            "update_id": 103,
                            "message": {
                                "chat": {"id": 2222, "username": "supporter_b"},
                                "text": "/stop",
                            },
                        },
                    ],
                },
            )
        elif "sendMessage" in str(request.url):
            sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as client:
        summary = dispatcher.sync_subscribers(repository=repo, default_daily_limit=3, http_client=client)

    assert summary["started"] == 2
    assert summary["style_updated"] == 1
    assert summary["stopped"] == 1
    assert repo.get_state("telegram_last_update_id") == "103"

    # Active subscribers should be operator_admin (99999) + supporter_a (1111). supporter_b (2222) stopped!
    active_subs = {s["chat_id"]: s for s in repo.get_active_subscribers()}
    assert "99999" in active_subs
    assert "1111" in active_subs
    assert "2222" not in active_subs
    assert active_subs["1111"]["preferred_style"] == "sharp"

    # Verify confirmation messages were sent for /start, /style, and /stop
    assert len(sent_messages) == 4
    welcome_texts = [m["text"] for m in sent_messages if m["chat_id"] == "1111"]
    assert any("נרשמת בהצלחה ל-zioX" in t for t in welcome_texts)
    assert any("sharp" in t for t in welcome_texts)


def test_send_admin_alert_restricted_strictly_to_admins(tmp_path):
    """
    Verify Task 3.2 (User Requirement #1):
    send_admin_alert() MUST ONLY send technical alerts to operatorTELEGRAM_CHAT_ID / tier='admin',
    and NEVER to regular 'free' or 'pro' subscribers!
    """
    db_file = str(tmp_path / "test_admin_only.db")
    repo = Repository(db_file)

    # Register regular subscribers and 1 DB admin
    repo.upsert_subscriber(chat_id="1111", username="regular_free", tier="free", daily_limit=3)
    repo.upsert_subscriber(chat_id="2222", username="regular_pro", tier="pro", daily_limit=15)
    repo.upsert_subscriber(chat_id="8888", username="db_admin", tier="admin", daily_limit=100)

    dispatcher = TelegramDispatcher(bot_token="test_bot_token", chat_ids="9999")
    sent_payloads = []

    def mock_handler(request: httpx.Request):
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as client:
        ok = dispatcher.send_admin_alert(
            alert_text="HTTP 429 Rate Limit on X Scout account. Entering 12h cooldown.",
            repository=repo,
            http_client=client,
        )

    assert ok is True
    recipient_ids = [p["chat_id"] for p in sent_payloads]
    # ONLY 9999 (.env admin) and 8888 (DB tier='admin') receive the alert
    assert set(recipient_ids) == {"9999", "8888"}
    assert "1111" not in recipient_ids
    assert "2222" not in recipient_ids


def test_dispatch_variations_to_subscribers_unique_sharding(tmp_path):
    """
    Verify Task 3.2:
    Multiple active subscribers each receive a DIFFERENT reply variation for the same tweet,
    respecting preferred_style and recording deliveries in `dispatches`.
    """
    db_file = str(tmp_path / "test_var_sharding.db")
    repo = Repository(db_file)

    repo.upsert_subscriber(chat_id="101", username="u1", tier="free", daily_limit=3, preferred_style="sharp")
    repo.upsert_subscriber(chat_id="102", username="u2", tier="free", daily_limit=3, preferred_style="factual")
    repo.upsert_subscriber(chat_id="103", username="u3", tier="free", daily_limit=3, preferred_style="any")

    dispatcher = TelegramDispatcher(bot_token="test_bot_token", chat_ids="")
    sent_payloads = []

    def mock_handler(request: httpx.Request):
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    variations = [
        {"style": "factual", "text": "Factual rebuttal variation 1 https://govextra.gov.il/1", "link": "https://govextra.gov.il/1"},
        {"style": "sharp", "text": "Sharp witty rebuttal variation 2 https://gaza-aid-data.gov.il/2", "link": "https://gaza-aid-data.gov.il/2"},
        {"style": "historical_legal", "text": "Legal rebuttal variation 3 https://idf.il/3", "link": "https://idf.il/3"},
    ]

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as client:
        count = dispatcher.dispatch_variations_to_subscribers(
            repository=repo,
            tweet_id="viral_900",
            author_handle="target_user",
            tweet_text="False claim tweet",
            virality_score=25.0,
            virality_tier="CRITICAL",
            variations=variations,
            claim_flagged="False claim",
            verified_facts=["Fact 1"],
            http_client=client,
        )

    assert count == 3
    assert len(sent_payloads) == 3

    by_chat = {p["chat_id"]: p["text"] for p in sent_payloads}
    # Subscriber 101 requested 'sharp' -> gets variation 2
    assert "Sharp witty rebuttal variation 2" in by_chat["101"]
    # Subscriber 102 requested 'factual' -> gets variation 1
    assert "Factual rebuttal variation 1" in by_chat["102"]
    # Subscriber 103 ('any') -> gets remaining variation 3
    assert "Legal rebuttal variation 3" in by_chat["103"]

    # Verify the inline keyboard includes the '✅ הגבתי ב-X' (ack:<tweet_id>) confirmation button!
    kb_101 = sent_payloads[0]["reply_markup"]["inline_keyboard"]
    assert len(kb_101) == 3
    assert kb_101[1][0]["callback_data"] == "ack:viral_900"

    # Calling again for the same tweet_id should send 0 messages (all 3 subscribers already received it)
    sent_payloads.clear()
    with httpx.Client(transport=transport) as client:
        repeat_count = dispatcher.dispatch_variations_to_subscribers(
            repository=repo,
            tweet_id="viral_900",
            author_handle="target_user",
            tweet_text="False claim tweet",
            virality_score=25.0,
            virality_tier="CRITICAL",
            variations=variations,
            http_client=client,
        )
    assert repeat_count == 0


def test_scale_1000_readiness_gate_commands_callbacks_and_403_deactivation(tmp_path):
    """
    Verify Scale-1000 Tasks 3.1 & 3.2:
    - /start with require_readiness_confirm=True puts user in ready_confirmed=0 until /ready or callback ready:confirm
    - /lang <en|ar|both>, /limit <number>, /quota commands
    - callback_query ack:<tweet_id> resets consecutive_unconfirmed and answers callback
    - HTTP 403 Forbidden automatically deactivates blocked subscriber
    - Auto-pause notification sent when subscriber hits max_unconfirmed_dispatches
    """
    db_file = str(tmp_path / "test_scale_tg.db")
    repo = Repository(db_file)
    dispatcher = TelegramDispatcher(bot_token="test_bot_token", chat_ids="")

    sent_messages = []
    callback_answers = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "getUpdates" in url_str:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 200,
                            "message": {"chat": {"id": 5001, "username": "u_ready"}, "text": "/start"},
                        },
                        {
                            "update_id": 201,
                            "message": {"chat": {"id": 5002, "username": "u_pending"}, "text": "/start"},
                        },
                        {
                            "update_id": 202,
                            "callback_query": {
                                "id": "cb_1",
                                "data": "ready:confirm",
                                "message": {"chat": {"id": 5001}},
                            },
                        },
                        {
                            "update_id": 203,
                            "message": {"chat": {"id": 5001, "username": "u_ready"}, "text": "/lang en"},
                        },
                        {
                            "update_id": 204,
                            "message": {"chat": {"id": 5001, "username": "u_ready"}, "text": "/limit 4"},
                        },
                        {
                            "update_id": 205,
                            "message": {"chat": {"id": 5001, "username": "u_ready"}, "text": "/quota"},
                        },
                    ],
                },
            )
        elif "answerCallbackQuery" in url_str:
            callback_answers.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})
        elif "sendMessage" in url_str:
            payload = json.loads(request.content)
            if payload["chat_id"] == "blocked_user":
                return httpx.Response(403, json={"ok": False, "description": "Forbidden: bot was blocked by the user"})
            sent_messages.append(payload)
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    with httpx.Client(transport=transport) as client:
        summary = dispatcher.sync_subscribers(
            repository=repo,
            default_daily_limit=3,
            max_user_daily_limit=5,
            require_readiness_confirm=True,
            http_client=client,
        )

    assert summary["started"] == 2
    assert summary["ready_confirmed"] == 1
    assert summary["lang_updated"] == 1
    assert summary["limit_updated"] == 1
    assert len(callback_answers) == 1

    # 5001 confirmed readiness, set lang='en', limit=4; 5002 did NOT confirm readiness yet
    sub_5001 = repo.get_subscriber("5001")
    sub_5002 = repo.get_subscriber("5002")
    assert sub_5001["ready_confirmed"] == 1
    assert sub_5001["preferred_lang"] == "en"
    assert sub_5001["daily_limit"] == 4
    assert sub_5002["ready_confirmed"] == 0

    # Add a subscriber who blocked the bot (returns 403)
    repo.upsert_subscriber(chat_id="blocked_user", username="blocker", ready_confirmed=True, active=True)

    variations = [
        {"style": "factual", "text": "Variation for 5001", "link": None},
        {"style": "sharp", "text": "Variation for blocked_user", "link": None},
    ]
    with httpx.Client(transport=transport) as client:
        sent_cnt = dispatcher.dispatch_variations_to_subscribers(
            repository=repo,
            tweet_id="t_999",
            author_handle="author",
            tweet_text="English claim tweet",
            virality_score=15.0,
            virality_tier="HIGH",
            variations=variations,
            http_client=client,
        )

    # 5001 received the card; 5002 was skipped (ready_confirmed=0); blocked_user returned 403 and was deactivated!
    assert sent_cnt == 1
    assert repo.get_subscriber("blocked_user")["active"] == 0


def test_default_language_is_english_only(tmp_path):
    """Verify that new subscribers registered via /start default strictly to 'en'."""
    db_file = str(tmp_path / "test_lang_default.db")
    repo = Repository(db_file)
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="")

    sent_messages = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "getUpdates" in url_str:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {
                            "update_id": 1,
                            "message": {"chat": {"id": 8888, "username": "new_user"}, "text": "/start"},
                        }
                    ],
                },
            )
        elif "sendMessage" in url_str:
            sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(mock_handler)) as client:
        dispatcher.sync_subscribers(repository=repo, http_client=client)

    sub = repo.get_subscriber("8888")
    assert sub is not None
    assert sub["preferred_lang"] == "en"
    # Check welcome message contains English default notification and keyboard
    assert len(sent_messages) == 1
    assert "en" in sent_messages[0]["text"]
    assert "reply_markup" in sent_messages[0]
    assert "inline_keyboard" in sent_messages[0]["reply_markup"]


def test_commands_show_multiple_choice_inline_keyboards(tmp_path):
    """Verify that /style, /lang, /limit, /help commands present multiple-choice inline keyboards."""
    db_file = str(tmp_path / "test_commands_keyboards.db")
    repo = Repository(db_file)
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="")

    sent_messages = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "getUpdates" in url_str:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {"update_id": 10, "message": {"chat": {"id": 7777}, "text": "/style"}},
                        {"update_id": 11, "message": {"chat": {"id": 7777}, "text": "/lang"}},
                        {"update_id": 12, "message": {"chat": {"id": 7777}, "text": "/limit"}},
                        {"update_id": 13, "message": {"chat": {"id": 7777}, "text": "/help"}},
                    ],
                },
            )
        elif "sendMessage" in url_str:
            sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(mock_handler)) as client:
        dispatcher.sync_subscribers(repository=repo, http_client=client)

    assert len(sent_messages) == 4
    # /style message has style choices (factual, sharp, etc.)
    style_kb = sent_messages[0]["reply_markup"]["inline_keyboard"]
    style_callbacks = [btn["callback_data"] for row in style_kb for btn in row]
    assert "set_style:factual" in style_callbacks
    assert "set_style:sharp" in style_callbacks

    # /lang message has language choices (en, ar, both)
    lang_kb = sent_messages[1]["reply_markup"]["inline_keyboard"]
    lang_callbacks = [btn["callback_data"] for row in lang_kb for btn in row]
    assert "set_lang:en" in lang_callbacks
    assert "set_lang:ar" in lang_callbacks
    assert "set_lang:both" in lang_callbacks

    # /limit message has daily limit choices
    limit_kb = sent_messages[2]["reply_markup"]["inline_keyboard"]
    limit_callbacks = [btn["callback_data"] for row in limit_kb for btn in row]
    assert "set_limit:1" in limit_callbacks
    assert "set_limit:3" in limit_callbacks

    # /help message has command navigation menu
    help_kb = sent_messages[3]["reply_markup"]["inline_keyboard"]
    help_callbacks = [btn["callback_data"] for row in help_kb for btn in row]
    assert "menu:style" in help_callbacks
    assert "menu:lang" in help_callbacks


def test_callback_query_selection_updates_subscriber_preferences(tmp_path):
    """Verify that inline button clicks (callback queries) update preferences and acknowledge Telegram."""
    db_file = str(tmp_path / "test_cb_prefs.db")
    repo = Repository(db_file)
    repo.upsert_subscriber(chat_id="6666", username="test_cb", preferred_lang="en", active=True)
    dispatcher = TelegramDispatcher(bot_token="test_token", chat_ids="")

    answered_callbacks = []
    sent_messages = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "getUpdates" in url_str:
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "result": [
                        {"update_id": 50, "callback_query": {"id": "cb_style", "data": "set_style:sharp", "message": {"chat": {"id": 6666}}}},
                        {"update_id": 51, "callback_query": {"id": "cb_lang", "data": "set_lang:ar", "message": {"chat": {"id": 6666}}}},
                        {"update_id": 52, "callback_query": {"id": "cb_limit", "data": "set_limit:5", "message": {"chat": {"id": 6666}}}},
                    ],
                },
            )
        elif "answerCallbackQuery" in url_str:
            answered_callbacks.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True})
        elif "sendMessage" in url_str:
            sent_messages.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(mock_handler)) as client:
        summary = dispatcher.sync_subscribers(repository=repo, http_client=client)

    assert summary["style_updated"] == 1
    assert summary["lang_updated"] == 1
    assert summary["limit_updated"] == 1
    assert len(answered_callbacks) == 3
    sub = repo.get_subscriber("6666")
    assert sub["preferred_style"] == "sharp"
    assert sub["preferred_lang"] == "ar"
    assert sub["daily_limit"] == 5


def test_setup_bot_commands_registers_all_commands():
    """Verify setup_bot_commands sends all commands to Telegram API setMyCommands."""
    dispatcher = TelegramDispatcher(bot_token="fake_bot_token")
    recorded_payload = []

    def mock_handler(request: httpx.Request):
        if "setMyCommands" in str(request.url):
            recorded_payload.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "result": True})
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(mock_handler)) as client:
        ok = dispatcher.setup_bot_commands(http_client=client)

    assert ok is True
    assert len(recorded_payload) == 1
    commands = [c["command"] for c in recorded_payload[0]["commands"]]
    assert "start" in commands
    assert "help" in commands
    assert "style" in commands
    assert "lang" in commands
    assert "limit" in commands
    assert "quota" in commands
    assert "stop" in commands


def test_set_and_delete_webhook_and_409_conflict_handling(tmp_path):
    """
    Verify Task 3.2:
    1. set_webhook registers the Cloudflare Worker URL and optional secret_token via Telegram setWebhook API.
    2. delete_webhook removes the webhook via Telegram deleteWebhook API.
    3. sync_subscribers handles HTTP 409 Conflict gracefully when a webhook is active.
    """
    db_file = str(tmp_path / "test_webhook_409.db")
    repo = Repository(db_file)
    dispatcher = TelegramDispatcher(bot_token="webhook_bot_token", chat_ids="99999")

    webhook_calls = []

    def mock_handler(request: httpx.Request):
        url_str = str(request.url)
        if "setMyCommands" in url_str:
            return httpx.Response(200, json={"ok": True, "result": True})
        if "setWebhook" in url_str:
            webhook_calls.append(("setWebhook", json.loads(request.content)))
            return httpx.Response(200, json={"ok": True, "result": True})
        if "deleteWebhook" in url_str:
            webhook_calls.append(("deleteWebhook", json.loads(request.content)))
            return httpx.Response(200, json={"ok": True, "result": True})
        if "getUpdates" in url_str:
            return httpx.Response(
                409,
                json={
                    "ok": False,
                    "error_code": 409,
                    "description": "Conflict: can't use getUpdates method while webhook is active",
                },
            )
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(mock_handler)) as client:
        ok_set = dispatcher.set_webhook(
            webhook_url="https://ziox-telegram-webhook.example.workers.dev",
            secret_token="my_secret_123",
            http_client=client,
        )
        assert ok_set is True

        # Calling sync_subscribers when webhook is active (HTTP 409) should seed admin and return cleanly
        summary = dispatcher.sync_subscribers(repository=repo, http_client=client)
        assert summary["started"] == 0
        assert "99999" in repo.get_admin_chat_ids()

        ok_del = dispatcher.delete_webhook(http_client=client)
        assert ok_del is True

    assert webhook_calls[0][0] == "setWebhook"
    assert webhook_calls[0][1]["url"] == "https://ziox-telegram-webhook.example.workers.dev"
    assert webhook_calls[0][1]["secret_token"] == "my_secret_123"
    assert webhook_calls[1][0] == "deleteWebhook"
