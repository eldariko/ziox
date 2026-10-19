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
