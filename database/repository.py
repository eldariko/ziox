"""Database repository providing data access and persistence for zioX."""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database.schema import INIT_STATEMENTS

logger = logging.getLogger(__name__)

try:
    import libsql_client
    HAS_LIBSQL = True
except ImportError:
    HAS_LIBSQL = False


class Repository:
    """
    Manages database queries for threads, tweets, and logs.
    Supports dual-mode engine:
    - Local Mode (default): standard Python sqlite3 with `db_path`.
    - Cloud Mode (Turso / libSQL): remote HTTP/libSQL connection via `turso_url` & `turso_auth_token`.
    """

    def __init__(
        self,
        db_path: str = "ziox.db",
        turso_url: Optional[str] = None,
        turso_auth_token: Optional[str] = None
    ):
        self.db_path = db_path
        self.turso_url = turso_url.strip() if turso_url else ""
        self.turso_auth_token = turso_auth_token.strip() if turso_auth_token else ""
        self.is_remote = bool(self.turso_url)
        self._remote_client = None

        if self.is_remote:
            if not HAS_LIBSQL:
                raise ImportError("libsql-client is required to connect to Turso cloud database.")
            logger.info(f"[REPOSITORY] Connecting to Turso Cloud SQLite endpoint: {self.turso_url}")
            self._remote_client = libsql_client.create_client_sync(
                url=self.turso_url,
                auth_token=self.turso_auth_token
            )
        else:
            logger.info(f"[REPOSITORY] Using local SQLite database at: {self.db_path}")

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Local sqlite3 connection fallback."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, query: str, params: Optional[List[Any]] = None) -> Any:
        """
        Executes query against remote Turso client or local SQLite connection.
        Returns a result wrapper with rows and row metadata.
        """
        params = params or []
        if self.is_remote:
            return self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.commit()
                return cursor

    def _init_db(self) -> None:
        """Create tables if they do not exist, and migrate columns."""
        if self.is_remote:
            for stmt in INIT_STATEMENTS:
                self._remote_client.execute(stmt)
            # Column migration check for status in processed_tweets
            info_res = self._remote_client.execute("PRAGMA table_info(processed_tweets)")
            columns = [row["name"] for row in info_res.rows]
            if "status" not in columns:
                self._remote_client.execute(
                    "ALTER TABLE processed_tweets ADD COLUMN status TEXT DEFAULT 'PROCESSED'"
                )
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                for stmt in INIT_STATEMENTS:
                    cursor.execute(stmt)
                # Migration check for status column
                cursor.execute("PRAGMA table_info(processed_tweets)")
                columns = [col["name"] for col in cursor.fetchall()]
                if "status" not in columns:
                    cursor.execute("ALTER TABLE processed_tweets ADD COLUMN status TEXT DEFAULT 'PROCESSED'")
                conn.commit()

    # --- Tweet Operations ---

    def is_tweet_processed(self, tweet_id: str) -> bool:
        """Check if a tweet ID has already been recorded."""
        query = "SELECT 1 FROM processed_tweets WHERE tweet_id = ?"
        if self.is_remote:
            res = self._remote_client.execute(query, [tweet_id])
            return len(res.rows) > 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (tweet_id,))
                return cursor.fetchone() is not None

    def enqueue_tweet(
        self,
        tweet_id: str,
        author_handle: str,
        tweet_text: str,
        virality_score: float = 0.0,
        parent_tweet_id: Optional[str] = None
    ) -> bool:
        """
        Enqueue a discovered tweet for processing.
        Returns True if newly enqueued, False if already exists.
        """
        query = """
            INSERT OR IGNORE INTO processed_tweets (
                tweet_id, parent_tweet_id, author_handle, tweet_text,
                virality_score, status, was_published
            ) VALUES (?, ?, ?, ?, ?, 'DISCOVERED', 0)
        """
        params = [tweet_id, parent_tweet_id, author_handle, tweet_text, virality_score]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            return res.rows_affected > 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()
                return cursor.rowcount > 0

    def get_pending_tweets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch discovered tweets awaiting evaluation or action, ordered by virality momentum."""
        query = """
            SELECT * FROM processed_tweets
            WHERE status = 'DISCOVERED'
            ORDER BY virality_score DESC, created_at DESC
            LIMIT ?
        """
        if self.is_remote:
            res = self._remote_client.execute(query, [limit])
            return [dict(row) for row in res.rows]
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (limit,))
                return [dict(row) for row in cursor.fetchall()]

    def update_tweet_status(
        self,
        tweet_id: str,
        status: str,
        reply_generated: Optional[str] = None,
        link_attached: Optional[str] = None,
        was_published: Optional[bool] = None
    ) -> None:
        """Update processing status and details of a queued tweet."""
        updates = ["status = ?"]
        params: List[Any] = [status]
        if reply_generated is not None:
            updates.append("reply_generated = ?")
            params.append(reply_generated)
        if link_attached is not None:
            updates.append("link_attached = ?")
            params.append(link_attached)
        if was_published is not None:
            updates.append("was_published = ?")
            params.append(1 if was_published else 0)
        params.append(tweet_id)
        query = f"UPDATE processed_tweets SET {', '.join(updates)} WHERE tweet_id = ?"

        if self.is_remote:
            self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()

    def save_processed_tweet(
        self,
        tweet_id: str,
        author_handle: str,
        tweet_text: str,
        virality_score: float,
        parent_tweet_id: Optional[str] = None,
        reply_generated: Optional[str] = None,
        link_attached: Optional[str] = None,
        media_attached: Optional[str] = None,
        was_published: bool = False,
        status: str = "PROCESSED"
    ) -> int:
        """Store a processed tweet."""
        query = """
            INSERT INTO processed_tweets (
                tweet_id, parent_tweet_id, author_handle, tweet_text,
                reply_generated, link_attached, media_attached,
                was_published, virality_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = [
            tweet_id, parent_tweet_id, author_handle, tweet_text,
            reply_generated, link_attached, media_attached,
            1 if was_published else 0, virality_score, status
        ]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            return res.last_insert_rowid or 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()
                return cursor.lastrowid

    def is_link_recently_posted(
        self,
        link: str,
        cooldown_minutes: int = 60,
        include_dry_run: bool = True
    ) -> bool:
        """Check if a URL has already been attached to a published reply within the cooldown period."""
        if not link:
            return False
        if include_dry_run:
            query = """
                SELECT COUNT(*) as count FROM processed_tweets
                WHERE link_attached = ?
                AND (was_published = 1 OR status = 'PROCESSED_DRY_RUN')
                AND created_at >= datetime('now', '-' || ? || ' minutes')
            """
        else:
            query = """
                SELECT COUNT(*) as count FROM processed_tweets
                WHERE link_attached = ?
                AND was_published = 1
                AND created_at >= datetime('now', '-' || ? || ' minutes')
            """
        params = [link, str(cooldown_minutes)]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            row = res.rows[0] if res.rows else None
            return (row["count"] > 0) if row else False
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return (row["count"] > 0) if row else False

    def get_monthly_reply_count(self) -> int:
        """Count replies published in the current calendar month."""
        query = """
            SELECT COUNT(*) as count FROM processed_tweets
            WHERE was_published = 1
            AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """
        if self.is_remote:
            res = self._remote_client.execute(query)
            row = res.rows[0] if res.rows else None
            return row["count"] if row else 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                row = cursor.fetchone()
                return row["count"] if row else 0

    # --- Thread Operations ---

    def get_thread(self, thread_root_id: str) -> Optional[Dict[str, Any]]:
        """Fetch thread state by root ID."""
        query = "SELECT * FROM threads WHERE thread_root_id = ?"
        if self.is_remote:
            res = self._remote_client.execute(query, [thread_root_id])
            return dict(res.rows[0]) if res.rows else None
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (thread_root_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

    def create_thread(
        self,
        thread_root_id: str,
        user_handle: str,
        max_turns: int = 2
    ) -> None:
        """Initialize a new active thread."""
        query = """
            INSERT OR IGNORE INTO threads (
                thread_root_id, user_handle, current_turn, max_turns, status
            ) VALUES (?, ?, 1, ?, 'ACTIVE')
        """
        params = [thread_root_id, user_handle, max_turns]
        if self.is_remote:
            self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()

    def advance_thread_turn(self, thread_root_id: str) -> Optional[int]:
        """Increment thread turn count and update timestamp."""
        update_query = """
            UPDATE threads
            SET current_turn = current_turn + 1,
                last_interaction = CURRENT_TIMESTAMP
            WHERE thread_root_id = ?
        """
        select_query = "SELECT current_turn, max_turns FROM threads WHERE thread_root_id = ?"

        if self.is_remote:
            self._remote_client.execute(update_query, [thread_root_id])
            res = self._remote_client.execute(select_query, [thread_root_id])
            if res.rows:
                row = res.rows[0]
                if row["current_turn"] >= row["max_turns"]:
                    self._remote_client.execute(
                        "UPDATE threads SET status = 'COMPLETED' WHERE thread_root_id = ?",
                        [thread_root_id]
                    )
                return row["current_turn"]
            return None
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(update_query, (thread_root_id,))
                cursor.execute(select_query, (thread_root_id,))
                row = cursor.fetchone()
                if row:
                    if row["current_turn"] >= row["max_turns"]:
                        cursor.execute(
                            "UPDATE threads SET status = 'COMPLETED' WHERE thread_root_id = ?",
                            (thread_root_id,)
                        )
                    conn.commit()
                    return row["current_turn"]
                return None

    def update_thread_status(self, thread_root_id: str, status: str) -> None:
        """Update thread status (e.g. 'COMPLETED', 'DROPPED_TOXIC')."""
        query = """
            UPDATE threads
            SET status = ?, last_interaction = CURRENT_TIMESTAMP
            WHERE thread_root_id = ?
        """
        params = [status, thread_root_id]
        if self.is_remote:
            self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()

    # --- Run Audit Logs ---

    def log_run(
        self,
        tweets_scanned: int,
        replies_sent: int,
        status: str,
        error_message: Optional[str] = None
    ) -> int:
        """Log a bot execution run."""
        query = """
            INSERT INTO bot_logs (tweets_scanned, replies_sent, status, error_message)
            VALUES (?, ?, ?, ?)
        """
        params = [tweets_scanned, replies_sent, status, error_message]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            return res.last_insert_rowid or 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()
                return cursor.lastrowid

    def get_recent_logs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the most recent run logs."""
        query = "SELECT * FROM bot_logs ORDER BY id DESC LIMIT ?"
        if self.is_remote:
            res = self._remote_client.execute(query, [limit])
            return [dict(row) for row in res.rows]
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (limit,))
                return [dict(row) for row in cursor.fetchall()]
