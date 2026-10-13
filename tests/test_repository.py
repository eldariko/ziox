import os
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
