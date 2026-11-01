"""End-to-End (E2E) Full Pipeline Simulation Test for zioX."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from config.settings import Settings
from database.repository import Repository
from providers.base import BaseTwitterProvider, Tweet, ScannerCircuitBreakerError
from engine.grounding import GroundingEngine, FactCheckResult, DraftVariation
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


def test_e2e_community_saas_variation_sharding_and_scanner_cooldown(tmp_path):
    """
    Simulates the Community SaaS & Scanner Shield lifecycle:
    1. Multiple active Telegram subscribers registered with different styles.
    2. Pipeline generates 5 distinct draft_variations and diversifies links across whitelisted sources.
    3. Each subscriber receives a unique variation and is logged in `dispatches`.
    4. If ScannerRateLimitError (HTTP 429) triggers during radar scan, scanner enters cooldown
       quarantine in `bot_state` and only the admin receives the technical alert.
    """
    db_file = str(tmp_path / "e2e_community_saas.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=False,
        virality_threshold=5.0,
        monthly_max_replies=30,
        search_keywords=["aid", "famine"],
        telegram_bot_token="123456:TEST_TOKEN",
        telegram_chat_id="999000",  # Operator admin chat ID
        telegram_review_enabled=True,
        scanner_cooldown_minutes=360,
    )

    # Register 3 regular community subscribers with different styles
    repo.upsert_subscriber(chat_id="sub_1", username="user1", preferred_style="empathetic", tier="free")
    repo.upsert_subscriber(chat_id="sub_2", username="user2", preferred_style="sharp", tier="free")
    repo.upsert_subscriber(chat_id="sub_3", username="user3", preferred_style="direct_data", tier="pro")

    provider = SimulatedTwitterProvider()

    mock_grounding = MagicMock(spec=GroundingEngine)
    def mock_eval_variations(text, author):
        if "blocked all food" in text.lower():
            return FactCheckResult(
                is_worth_replying=True,
                claim_identified="False claim that all aid was blocked",
                verified_facts=["Over 30,000 aid trucks entered via Kerem Shalom."],
                recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
                draft_reply="Over 30,000 aid trucks entered Gaza via official crossings.",
                draft_variations=[
                    DraftVariation(style="direct_data", text="Over 30,000 aid trucks and 500,000+ tons of food entered Gaza via Kerem Shalom and Erez."),
                    DraftVariation(style="socratic", text="If aid is completely blocked, how did over 30,000 inspected trucks cross into Gaza via Kerem Shalom?"),
                    DraftVariation(style="historical", text="Since October, COGAT and UN agencies have coordinated over 30,000 aid trucks into Gaza."),
                    DraftVariation(style="empathetic", text="Civilians need real relief, which is why over 30,000 aid trucks have entered Gaza—the bottleneck is internal distribution."),
                    DraftVariation(style="sharp", text="30,000+ aid trucks entered Gaza through inspected crossings. Blaming the border ignores the real distribution bottleneck."),
                ],
            )
        return FactCheckResult(is_worth_replying=False, claim_identified="Troll", draft_reply="")

    mock_grounding.evaluate_and_draft.side_effect = mock_eval_variations

    mock_telegram = MagicMock()
    mock_telegram.is_configured.return_value = True
    mock_telegram.sync_subscribers.return_value = 0

    dispatched_payloads = {}
    def fake_dispatch_variations(
        repository,
        tweet_id,
        author_handle,
        tweet_text,
        virality_score,
        virality_tier,
        variations,
        claim_flagged="",
        verified_facts=None,
    ):
        from engine.telegram_dispatcher import TelegramDispatcher
        real_dispatcher = TelegramDispatcher(bot_token="123456:TEST_TOKEN", chat_ids="999000")
        mock_http = MagicMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        def capture_post(url, json=None, **kwargs):
            if json and "chat_id" in json:
                dispatched_payloads[json["chat_id"]] = json
            return mock_resp
        mock_http.post.side_effect = capture_post
        return real_dispatcher.dispatch_variations_to_subscribers(
            repository=repository,
            tweet_id=tweet_id,
            author_handle=author_handle,
            tweet_text=tweet_text,
            virality_score=virality_score,
            virality_tier=virality_tier,
            variations=variations,
            claim_flagged=claim_flagged,
            verified_facts=verified_facts,
            http_client=mock_http,
        )

    mock_telegram.dispatch_variations_to_subscribers.side_effect = fake_dispatch_variations

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding,
        telegram_dispatcher=mock_telegram,
    )

    radar = DiscoveryRadar(repo)

    # Run non-interactive cycle (Community SaaS mode)
    report = orchestrator.run_full_pipeline(radar=radar, start_jitter_minutes=0.0, interactive=False, limit_queue=5)
    assert report["status"] == "SUCCESS"
    assert report["replies_sent"] == 1

    # Verify all 3 subscribers received unique variations in `dispatches`
    used_hashes = repo.get_used_variation_hashes("viral_aid_101")
    assert len(used_hashes) == 3
    assert len(set(used_hashes)) == 3  # 3 unique variation hashes sharded across 3 subscribers
    assert len(dispatched_payloads) == 3

    # Now simulate HTTP 429 Circuit Breaker during next radar scan
    def rate_limited_search(query: str, limit: int = 10):
        raise ScannerCircuitBreakerError("HTTP 429 Too Many Requests from X GraphQL", status_code=429, reason="RATE_LIMIT_429")

    provider.search_recent_tweets = rate_limited_search
    orchestrator.run_full_pipeline(radar=radar, start_jitter_minutes=0.0, interactive=False, limit_queue=5)

    # Verify cooldown timestamp was persisted in bot_state and admin alert was triggered
    cooldown_until = repo.get_state("scanner_cooldown_until")
    assert cooldown_until is not None
    assert mock_telegram.send_admin_alert.called


def test_e2e_scale_multi_wave_cohort_sharding_and_language_routing(tmp_path):
    """
    Simulates scaling to a large community with horizontal cohort sharding across multiple waves:
    - 35 English/both subscribers + 5 Arabic-only subscribers = 40 active subscribers.
    - `target_cohort_size_per_tweet = 20`, `no_link_variation_ratio = 0.4`.
    - Wave 1:
      * English tweet `viral_aid_101` serves the first 20 eligible subscribers with 20 unique variations
        (mixing 60% linked and 40% linkless replies) and transitions to `DISPATCHED_WAVE`.
      * Arabic tweet `viral_ar_201` routes only to Arabic/both subscribers.
    - Wave 2:
      * Running `process_queue` again picks up `viral_aid_101` (`DISPATCHED_WAVE`), generates a fresh batch
        for the remaining 15 English/both subscribers, serves all 35 without a single duplicate hash,
        and transitions `viral_aid_101` to `DISPATCHED_TELEGRAM`.
    """
    from engine.telegram_dispatcher import TelegramDispatcher

    db_file = str(tmp_path / "e2e_scale_waves.db")
    repo = Repository(db_file)
    settings = Settings(
        database_path=db_file,
        dry_run=False,
        virality_threshold=5.0,
        monthly_max_replies=100,
        telegram_bot_token="123456:TEST_TOKEN",
        telegram_chat_id="999000",
        telegram_review_enabled=True,
        target_cohort_size_per_tweet=20,
        telegram_tweets_per_cycle=10,
        no_link_variation_ratio=0.4,
        max_variations_per_gemini_call=10,
    )

    styles = ["direct_data", "socratic", "historical", "empathetic", "sharp"]
    # Register 30 English-only subscribers + 5 Both-language subscribers (= 35 eligible for English)
    for i in range(30):
        repo.upsert_subscriber(
            chat_id=f"en_sub_{i}",
            username=f"en_user_{i}",
            preferred_style=styles[i % len(styles)],
            preferred_lang="en",
            ready_confirmed=True,
        )
    for i in range(5):
        repo.upsert_subscriber(
            chat_id=f"both_sub_{i}",
            username=f"both_user_{i}",
            preferred_style=styles[i % len(styles)],
            preferred_lang="both",
            ready_confirmed=True,
        )
    # Register 5 Arabic-only subscribers (should NOT receive English tweets, only Arabic tweets)
    for i in range(5):
        repo.upsert_subscriber(
            chat_id=f"ar_sub_{i}",
            username=f"ar_user_{i}",
            preferred_style=styles[i % len(styles)],
            preferred_lang="ar",
            ready_confirmed=True,
        )

    # Enqueue 1 English viral tweet and 1 Arabic viral tweet
    repo.save_processed_tweet(
        tweet_id="viral_aid_101",
        author_handle="hostile_en",
        tweet_text="BREAKING: Israel has completely blocked all food and aid trucks into Gaza!",
        virality_score=95.0,
        was_published=False,
        status="DISCOVERED",
    )
    repo.save_processed_tweet(
        tweet_id="viral_ar_201",
        author_handle="hostile_ar",
        tweet_text="عاجل: إسرائيل تمنع دخول جميع شاحنات المساعدات الإنسانية والغذاء إلى غزة بالكامل!",
        virality_score=88.0,
        was_published=False,
        status="DISCOVERED",
    )

    provider = SimulatedTwitterProvider()
    batch_call_counter = {"count": 0}

    mock_grounding = MagicMock(spec=GroundingEngine)
    def fake_generate_batch(tweet_text, author_handle, total_variations=10, max_per_call=10):
        batch_call_counter["count"] += 1
        call_idx = batch_call_counter["count"]
        is_ar = any("\u0600" <= c <= "\u06ff" for c in tweet_text)
        vars_list = []
        for idx in range(total_variations):
            st = styles[idx % len(styles)]
            if is_ar:
                txt = f"بيانات رسمية ({call_idx}-{idx}): دخلت أكثر من 30,000 شاحنة مساعدات عبر المعابر."
            else:
                txt = f"Verified crossing record #{call_idx}-{idx}: Over 30,000 inspected aid trucks entered Gaza."
            vars_list.append(DraftVariation(style=st, text=txt))
        return FactCheckResult(
            is_worth_replying=True,
            claim_identified="False aid blockade claim",
            verified_facts=["30,000+ aid trucks entered Gaza"],
            recommended_link="https://govextra.gov.il/cogat/humanitarian-efforts/home/",
            draft_reply=vars_list[0].text,
            draft_variations=vars_list,
        )

    mock_grounding.generate_variations_batch.side_effect = fake_generate_batch
    mock_grounding.evaluate_and_draft.side_effect = lambda text, author: fake_generate_batch(text, author, total_variations=10)

    real_dispatcher = TelegramDispatcher(bot_token="123456:TEST_TOKEN", chat_ids="999000")
    mock_http = MagicMock()
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    sent_messages = []
    def capture_post(url, json=None, **kwargs):
        if json and "chat_id" in json and "text" in json:
            sent_messages.append(json)
        return mock_resp
    mock_http.post.side_effect = capture_post

    mock_telegram = MagicMock()
    mock_telegram.is_configured.return_value = True
    mock_telegram.sync_subscribers.return_value = 0
    mock_telegram.dispatch_variations_to_subscribers.side_effect = (
        lambda **kwargs: real_dispatcher.dispatch_variations_to_subscribers(**kwargs, http_client=mock_http)
    )

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=mock_grounding,
        telegram_dispatcher=mock_telegram,
    )

    # --- WAVE 1 ---
    report_w1 = orchestrator.process_queue(interactive=False, limit=10)
    assert report_w1["status"] == "SUCCESS"
    assert report_w1["processed"] == 2

    # Check viral_aid_101 after Wave 1: 20 subscribers served, 15 remaining -> DISPATCHED_WAVE
    hashes_en_w1 = repo.get_used_variation_hashes("viral_aid_101")
    assert len(hashes_en_w1) == 20
    assert len(set(hashes_en_w1)) == 20

    # Check viral_ar_201 after Wave 1: 5 ar_sub + 5 both_sub = 10 eligible subscribers served -> DISPATCHED_TELEGRAM
    hashes_ar_w1 = repo.get_used_variation_hashes("viral_ar_201")
    assert len(hashes_ar_w1) == 10
    assert len(set(hashes_ar_w1)) == 10

    with repo._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM processed_tweets WHERE tweet_id = 'viral_aid_101'")
        assert cursor.fetchone()["status"] == "DISPATCHED_WAVE"
        cursor.execute("SELECT status FROM processed_tweets WHERE tweet_id = 'viral_ar_201'")
        assert cursor.fetchone()["status"] == "DISPATCHED_TELEGRAM"

    # Verify Arabic-only subscribers NEVER received the English tweet
    with repo._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM dispatches WHERE tweet_id = 'viral_aid_101'")
        en_recipients_w1 = {r["chat_id"] for r in cursor.fetchall()}
        assert all(not cid.startswith("ar_sub_") for cid in en_recipients_w1)

    # --- WAVE 2 ---
    # Running process_queue again should pick up viral_aid_101 (DISPATCHED_WAVE) and serve the remaining 15 subscribers
    report_w2 = orchestrator.process_queue(interactive=False, limit=10)
    assert report_w2["status"] == "SUCCESS"
    assert report_w2["processed"] == 1

    hashes_en_total = repo.get_used_variation_hashes("viral_aid_101")
    assert len(hashes_en_total) == 35
    assert len(set(hashes_en_total)) == 35  # 100% unique across all 35 subscribers!

    with repo._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM processed_tweets WHERE tweet_id = 'viral_aid_101'")
        assert cursor.fetchone()["status"] == "DISPATCHED_TELEGRAM"
