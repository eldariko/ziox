"""Tests for Step 11: Turso Cloud SQLite Database Adapter."""

import pytest
import os
from unittest.mock import MagicMock, patch
from database.repository import Repository
from database.turso_client import TursoClient, TursoRow, TursoResultSet
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


def test_turso_client_url_normalization():
    """Verify TursoClient normalizes libsql:// and wss:// URLs to https://."""
    client = TursoClient("libsql://my-db.turso.io", auth_token="tok123")
    assert client.base_url == "https://my-db.turso.io"
    assert client.pipeline_url == "https://my-db.turso.io/v2/pipeline"
    client.close()

    client2 = TursoClient("wss://my-db.turso.io")
    assert client2.base_url == "https://my-db.turso.io"
    client2.close()


def test_turso_client_execute_pipeline():
    """Verify TursoClient executes SQL and correctly parses /v2/pipeline response."""
    client = TursoClient("https://mock-db.turso.io", auth_token="token_xyz")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {
                "type": "ok",
                "response": {
                    "type": "execute",
                    "result": {
                        "cols": [{"name": "id"}, {"name": "author"}],
                        "rows": [
                            [
                                {"type": "integer", "value": "1"},
                                {"type": "text", "value": "alice"}
                            ]
                        ],
                        "affected_row_count": 0,
                        "last_insert_rowid": "1"
                    }
                }
            }
        ]
    }

    with patch.object(client._session, "post", return_value=mock_resp) as mock_post:
        res = client.execute("SELECT id, author FROM users WHERE id = ?", [1])

        assert len(res) == 1
        assert res.columns == ("id", "author")
        assert res.rows[0]["id"] == 1
        assert res.rows[0]["author"] == "alice"
        assert res.rows[0][0] == 1
        assert res.rows[0][1] == "alice"
        assert res.last_insert_rowid == 1

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"] == "Bearer token_xyz"
        assert call_kwargs["json"]["requests"][0]["stmt"]["sql"] == "SELECT id, author FROM users WHERE id = ?"
        assert call_kwargs["json"]["requests"][0]["stmt"]["args"] == [{"type": "integer", "value": "1"}]

    client.close()


def test_repository_remote_mode_with_turso_client(tmp_path):
    """Verify Repository initializes TursoClient when turso_url is provided."""
    mock_client = MagicMock()
    mock_client.execute.return_value = MagicMock(
        rows=[{"name": "status"}],
        rows_affected=1,
        last_insert_rowid=1
    )

    with patch("database.repository.TursoClient", return_value=mock_client) as mock_create:
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
        assert mock_client.execute.call_count >= len(INIT_STATEMENTS)

        repo.close()
        mock_client.close.assert_called_once()


def test_repository_remote_mode_crud_operations():
    """Verify that tweet CRUD queries map cleanly through the remote TursoClient."""
    mock_client = MagicMock()
    mock_client.execute.return_value = MagicMock(
        rows=[{"name": "status"}],
        rows_affected=1,
        last_insert_rowid=42
    )

    with patch("database.repository.TursoClient", return_value=mock_client):
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

        repo.close()
