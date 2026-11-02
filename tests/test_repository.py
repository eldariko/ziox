import os
import sqlite3
from database.repository import Repository


def test_repository_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_repo.db")
    repo = Repository(db_file)

    # 1. Deduplication
    assert repo.is_tweet_processed("tweet_999") is False

    repo.save_processed_tweet(
        tweet_id="tweet_999",
        author_handle="alice",
        tweet_text="Sample text",
        virality_score=8.5,
        was_published=True
    )

    assert repo.is_tweet_processed("tweet_999") is True
    assert repo.get_monthly_reply_count() == 1

    # 2. Thread operations
    assert repo.get_thread("thread_1") is None
    repo.create_thread("thread_1", user_handle="bob", max_turns=2)

    thread = repo.get_thread("thread_1")
    assert thread is not None
    assert thread["current_turn"] == 1
    assert thread["status"] == "ACTIVE"

    next_turn = repo.advance_thread_turn("thread_1")
    assert next_turn == 2

    updated = repo.get_thread("thread_1")
    assert updated["status"] == "COMPLETED"

    # 3. Logging
    log_id = repo.log_run(tweets_scanned=10, replies_sent=1, status="SUCCESS")
    assert log_id > 0
    logs = repo.get_recent_logs(limit=1)
    assert len(logs) == 1
    assert logs[0]["tweets_scanned"] == 10


def test_enqueue_tweet_with_external_parent_id(tmp_path):
    """Verify that enqueuing a reply to an external tweet does not fail foreign key constraints."""
    db_file = str(tmp_path / "test_ext_parent.db")
    repo = Repository(db_file)

    # Enqueue a tweet where parent_tweet_id is not in processed_tweets
    enqueued = repo.enqueue_tweet(
        tweet_id="reply_1001",
        author_handle="charlie",
        tweet_text="Replying to someone on Twitter",
        virality_score=15.0,
        parent_tweet_id="external_parent_77777"
    )
    assert enqueued is True
    assert repo.is_tweet_processed("reply_1001") is True

    pending = repo.get_pending_tweets(limit=5)
    assert len(pending) == 1
    assert pending[0]["tweet_id"] == "reply_1001"
    assert pending[0]["parent_tweet_id"] == "external_parent_77777"


def test_repository_migration_removes_foreign_key(tmp_path):
    """Verify that an existing database with the old FK constraint is migrated cleanly."""
    db_file = str(tmp_path / "legacy_schema.db")

    # Manually create table with legacy foreign key constraint
    conn = sqlite3.connect(db_file)
    conn.execute("""
    CREATE TABLE processed_tweets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tweet_id TEXT UNIQUE NOT NULL,
        parent_tweet_id TEXT,
        author_handle TEXT NOT NULL,
        tweet_text TEXT NOT NULL,
        reply_generated TEXT,
        link_attached TEXT,
        media_attached TEXT,
        was_published BOOLEAN DEFAULT 0,
        virality_score REAL DEFAULT 0,
        status TEXT DEFAULT 'PROCESSED',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(parent_tweet_id) REFERENCES processed_tweets(tweet_id)
    );
    """)
    conn.execute("""
    INSERT INTO processed_tweets (tweet_id, author_handle, tweet_text)
    VALUES ('old_tweet_1', 'alice', 'Pre-existing tweet')
    """)
    conn.commit()

    # Verify FK constraint exists prior to repository init
    fks_before = conn.execute("PRAGMA foreign_key_list(processed_tweets)").fetchall()
    assert len(fks_before) == 1
    conn.close()

    # Initialize repository -> triggers migration
    repo = Repository(db_file)

    conn = sqlite3.connect(db_file)
    fks_after = conn.execute("PRAGMA foreign_key_list(processed_tweets)").fetchall()
    assert len(fks_after) == 0
    count = conn.execute("SELECT COUNT(*) FROM processed_tweets").fetchone()[0]
    assert count == 1
    conn.close()

    # Enqueue a reply to an external tweet that does not exist in processed_tweets
    res = repo.enqueue_tweet(
        tweet_id="new_reply_2",
        author_handle="bob",
        tweet_text="Reply to external",
        virality_score=10.0,
        parent_tweet_id="untracked_tweet_999"
    )
    assert res is True


def test_subscribers_dispatches_and_bot_state_lifecycle(tmp_path):
    """Verify Task 3.1: Subscribers, dispatches ledger, and bot_state CRUD in local SQLite."""
    db_file = str(tmp_path / "test_phase_c.db")
    repo = Repository(db_file)

    # 1. Subscriber registration & style updates
    repo.upsert_subscriber(chat_id="1001", username="user_one", tier="free", daily_limit=3)
    repo.upsert_subscriber(chat_id="1002", username="user_two", tier="pro", daily_limit=15)
    repo.upsert_subscriber(chat_id="9999", username="admin_op", tier="admin", daily_limit=100)

    active_subs = repo.get_active_subscribers()
    assert len(active_subs) == 3

    admin_ids = repo.get_admin_chat_ids()
    assert admin_ids == ["9999"]

    repo.update_subscriber_style("1001", "sharp")
    updated_subs = {s["chat_id"]: s for s in repo.get_active_subscribers()}
    assert updated_subs["1001"]["preferred_style"] == "sharp"

    # Deactivate and reactivate
    repo.deactivate_subscriber("1002")
    assert len(repo.get_active_subscribers()) == 2
    repo.upsert_subscriber(chat_id="1002", username="user_two", active=True)
    assert len(repo.get_active_subscribers()) == 3

    # 2. Dispatches ledger & deduplication
    assert repo.has_received_tweet("tweet_500", "1001") is False
    recorded = repo.record_dispatch("tweet_500", "1001", "Variation A text", style="sharp")
    assert recorded is True
    assert repo.has_received_tweet("tweet_500", "1001") is True
    assert repo.get_subscriber_daily_count("1001") == 1

    # Duplicate dispatch for same (tweet_id, chat_id) is ignored
    recorded_again = repo.record_dispatch("tweet_500", "1001", "Variation A text", style="sharp")
    assert recorded_again is False
    assert repo.get_subscriber_daily_count("1001") == 1

    used_hashes = repo.get_used_variation_hashes("tweet_500")
    assert len(used_hashes) == 1
    assert used_hashes[0] == repo.compute_variation_hash("Variation A text")

    # 3. Bot state key-value persistence
    assert repo.get_state("telegram_last_update_id") is None
    repo.set_state("telegram_last_update_id", "54321")
    assert repo.get_state("telegram_last_update_id") == "54321"
    repo.set_state("telegram_last_update_id", "54325")
    assert repo.get_state("telegram_last_update_id") == "54325"


def test_scale_1000_single_query_cohort_eligibility_and_readiness(tmp_path):
    """
    Verify Tasks 1.1 & 1.2:
    - Automatic column migrations on legacy subscribers/dispatches tables
    - Language filtering (en, ar, both)
    - Daily limit clamping (/limit)
    - Readiness confirmation (/ready) and consecutive_unconfirmed streak auto-pause
    - Single-query cohort selection (get_eligible_subscribers_for_tweet)
    - Multi-wave DISPATCHED_WAVE queue priority
    """
    db_file = str(tmp_path / "test_scale_1000.db")
    # Simulate legacy subscribers & dispatches tables without new columns
    conn = sqlite3.connect(db_file)
    conn.execute("""
    CREATE TABLE subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT UNIQUE NOT NULL,
        username TEXT DEFAULT '',
        tier TEXT DEFAULT 'free',
        daily_limit INTEGER DEFAULT 3,
        preferred_style TEXT DEFAULT 'any',
        active BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("""
    CREATE TABLE dispatches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tweet_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        variation_hash TEXT NOT NULL,
        style TEXT DEFAULT 'factual',
        dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(tweet_id, chat_id)
    );
    """)
    conn.commit()
    conn.close()

    # Initialize Repository -> should auto-migrate missing columns
    repo = Repository(db_file)

    # Register subscribers with different readiness & language preferences
    repo.upsert_subscriber(chat_id="u_en", username="en_only", preferred_lang="en", ready_confirmed=True, daily_limit=3)
    repo.upsert_subscriber(chat_id="u_ar", username="ar_only", preferred_lang="ar", ready_confirmed=True, daily_limit=3)
    repo.upsert_subscriber(chat_id="u_both", username="both_lang", preferred_lang="both", ready_confirmed=True, daily_limit=2)
    repo.upsert_subscriber(chat_id="u_pending", username="not_ready", preferred_lang="both", ready_confirmed=False, daily_limit=3)

    # 1. Check eligibility for English tweet ('en') -> u_en and u_both only (u_ar and u_pending excluded)
    en_cohort = repo.get_eligible_subscribers_for_tweet("tweet_en_1", lang="en", limit=10)
    assert [s["chat_id"] for s in en_cohort] == ["u_en", "u_both"]

    # 2. Check eligibility for Arabic tweet ('ar') -> u_ar and u_both only
    ar_cohort = repo.get_eligible_subscribers_for_tweet("tweet_ar_1", lang="ar", limit=10)
    assert [s["chat_id"] for s in ar_cohort] == ["u_ar", "u_both"]

    # 3. Confirm readiness for u_pending -> now included!
    repo.confirm_subscriber_ready("u_pending")
    en_cohort_after = repo.get_eligible_subscribers_for_tweet("tweet_en_1", lang="en", limit=10)
    assert set(s["chat_id"] for s in en_cohort_after) == {"u_en", "u_both", "u_pending"}

    # 4. Language update & daily limit clamping
    repo.update_subscriber_language("u_en", "ar")
    assert repo.get_subscriber("u_en")["preferred_lang"] == "ar"
    repo.update_subscriber_language("u_en", "en")

    clamped = repo.update_subscriber_daily_limit("u_en", requested_limit=20, max_ceiling=5)
    assert clamped == 5
    assert repo.get_subscriber("u_en")["daily_limit"] == 5

    # 5. Unconfirmed streak & confirmation reset
    for i in range(3):
        repo.record_dispatch(f"t_streak_{i}", "u_en", f"var_{i}")
    assert repo.get_subscriber("u_en")["consecutive_unconfirmed"] == 3

    # Confirming one reply resets consecutive_unconfirmed to 0 and increments total_confirmed_replies
    assert repo.confirm_dispatch_replied("t_streak_1", "u_en") is True
    sub_en = repo.get_subscriber("u_en")
    assert sub_en["consecutive_unconfirmed"] == 0
    assert sub_en["total_confirmed_replies"] == 1

    # Exceeding max_unconfirmed pauses subscriber
    repo.upsert_subscriber(chat_id="u_ghost", username="ghost", ready_confirmed=True, daily_limit=10)
    for i in range(5):
        repo.record_dispatch(f"t_ghost_{i}", "u_ghost", f"ghost_var_{i}")
    paused_ids = repo.pause_unresponsive_subscribers(max_unconfirmed=5)
    assert paused_ids == ["u_ghost"]
    ghost_sub = repo.get_subscriber("u_ghost")
    assert ghost_sub["active"] == 0
    assert ghost_sub["ready_confirmed"] == 0

    # 6. Multi-wave DISPATCHED_WAVE queue ordering
    repo.enqueue_tweet("wave_tweet_1", "author1", "Wave tweet", virality_score=50.0)
    repo.update_tweet_status("wave_tweet_1", status="DISPATCHED_WAVE")
    repo.enqueue_tweet("fresh_tweet_2", "author2", "Fresh tweet", virality_score=10.0)

    pending = repo.get_pending_tweets(limit=5, include_waves=True)
    # Fresh DISCOVERED tweet comes before DISPATCHED_WAVE even if DISPATCHED_WAVE has higher virality
    assert [p["tweet_id"] for p in pending] == ["fresh_tweet_2", "wave_tweet_1"]


def test_get_available_subscriber_demand(tmp_path):
    """Verify Task 2.1: get_available_subscriber_demand counts active, ready subscribers under daily quota by language."""
    db_file = str(tmp_path / "test_demand.db")
    repo = Repository(db_file)

    # 300 English, 100 Arabic, 50 Both, 20 Pending (ready_confirmed=0), 10 Inactive (active=0)
    for i in range(300):
        repo.upsert_subscriber(chat_id=f"en_{i}", preferred_lang="en", ready_confirmed=True, daily_limit=2)
    for i in range(100):
        repo.upsert_subscriber(chat_id=f"ar_{i}", preferred_lang="ar", ready_confirmed=True, daily_limit=2)
    for i in range(50):
        repo.upsert_subscriber(chat_id=f"both_{i}", preferred_lang="both", ready_confirmed=True, daily_limit=1)
    for i in range(20):
        repo.upsert_subscriber(chat_id=f"pend_{i}", preferred_lang="en", ready_confirmed=False, daily_limit=3)
    for i in range(10):
        repo.upsert_subscriber(chat_id=f"inact_{i}", preferred_lang="en", ready_confirmed=True, active=False, daily_limit=3)

    demand = repo.get_available_subscriber_demand(max_unconfirmed=5)
    assert demand["en"] == 350   # 300 en + 50 both
    assert demand["ar"] == 150   # 100 ar + 50 both
    assert demand["total"] == 450  # 300 + 100 + 50 distinct available subscribers

    # Exhaust daily quota for the 50 'both' subscribers (daily_limit=1)
    for i in range(50):
        repo.record_dispatch("tweet_quota_test", f"both_{i}", f"hash_{i}")

    demand_after = repo.get_available_subscriber_demand(max_unconfirmed=5)
    assert demand_after["en"] == 300
    assert demand_after["ar"] == 100
    assert demand_after["total"] == 400
