"""Tests for Step 11: Turso Cloud SQLite / libSQL Database Adapter."""

import pytest
import os
from unittest.mock import MagicMock, patch
from database.repository import Repository
from database.schema import INIT_STATEMENTS


def test_repository_local_mode_by_default(tmp_path):
    """Verify Repository defaults to standard local sqlite3 when turso_url is not set."""
    db_file = str(tmp_path / "local_test.db")
    repo = Repository(db_path=db_file)

    assert repo.is_remote is False
    assert repo._remote_client is None
    assert os.path.exists(db_file)

    # Basic insert & fetch check
    repo.enqueue_tweet(
        tweet_id="local_t1",
        author_handle="alice",
        tweet_text="Sample text",
        virality_score=10.0
    )
    assert repo.is_tweet_processed("local_t1") is True
    pending = repo.get_pending_tweets(limit=5)
    assert len(pending) == 1
    assert pending[0]["tweet_id"] == "local_t1"


def test_repository_remote_mode_with_turso_client(tmp_path):
    """Verify Repository initializes libsql_client when turso_url is provided."""
    mock_client = MagicMock()
    # Mock schema table check
    mock_client.execute.return_value = MagicMock(rows=[{"name": "status"}], rows_affected=1, last_insert_rowid=1)

    with patch("libsql_client.create_client_sync", return_value=mock_client) as mock_create:
        repo = Repository(
            db_path=str(tmp_path / "unused.db"),
            turso_url="libsql://test-db.turso.io",
            turso_auth_token="test_token_123"
        )

        assert repo.is_remote is True
        assert repo._remote_client == mock_client
        mock_create.assert_called_once_with(
            url="libsql://test-db.turso.io",
            auth_token="test_token_123"
        )

        # Ensure init statements were executed against remote client
        assert mock_client.execute.call_count >= len(INIT_STATEMENTS)


def test_repository_remote_mode_crud_operations():
    """Verify that tweet CRUD queries map cleanly through the remote libSQL client."""
    mock_client = MagicMock()
    mock_client.execute.return_value = MagicMock(
        rows=[{"name": "status"}],
        rows_affected=1,
        last_insert_rowid=42
    )

    with patch("libsql_client.create_client_sync", return_value=mock_client):
        repo = Repository(
            turso_url="libsql://mock-cloud.turso.io",
            turso_auth_token="secret"
        )

        # 1. Enqueue tweet
        mock_client.execute.return_value.rows_affected = 1
        enqueued = repo.enqueue_tweet("t_100", "bob", "Hello world", 15.0)
        assert enqueued is True

        # 2. Check processed
        mock_client.execute.return_value.rows = [{"1": 1}]
        assert repo.is_tweet_processed("t_100") is True

        # 3. Monthly reply count
        mock_client.execute.return_value.rows = [{"count": 5}]
        assert repo.get_monthly_reply_count() == 5

        # 4. Link cooldown check
        mock_client.execute.return_value.rows = [{"count": 1}]
        assert repo.is_link_recently_posted("https://idf.il", cooldown_minutes=60) is True

        mock_client.execute.return_value.rows = [{"count": 0}]
        assert repo.is_link_recently_posted("https://mfa.gov.il", cooldown_minutes=60) is False

        # 5. Thread state
        mock_client.execute.return_value.rows = [{"thread_root_id": "root_1", "current_turn": 1, "max_turns": 2}]
        thread = repo.get_thread("root_1")
        assert thread is not None
        assert thread["thread_root_id"] == "root_1"
