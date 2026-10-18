"""Database repository providing data access and persistence for zioX."""

import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database.schema import INIT_STATEMENTS


class Repository:
    """Manages SQLite queries for threads, tweets, and logs."""

    def __init__(self, db_path: str = "ziox.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create tables if they do not exist, and migrate columns."""
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM processed_tweets WHERE tweet_id = ?", (tweet_id,))
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO processed_tweets (
                    tweet_id, parent_tweet_id, author_handle, tweet_text,
                    virality_score, status, was_published
                ) VALUES (?, ?, ?, ?, ?, 'DISCOVERED', 0)
                """,
                (tweet_id, parent_tweet_id, author_handle, tweet_text, virality_score)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_pending_tweets(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch discovered tweets awaiting evaluation or action, ordered by virality momentum."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM processed_tweets
                WHERE status = 'DISCOVERED'
                ORDER BY virality_score DESC, created_at DESC
                LIMIT ?
                """,
                (limit,)
            )
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
            cursor.execute(query, params)
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO processed_tweets (
                    tweet_id, parent_tweet_id, author_handle, tweet_text,
                    reply_generated, link_attached, media_attached,
                    was_published, virality_score, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tweet_id, parent_tweet_id, author_handle, tweet_text,
                    reply_generated, link_attached, media_attached,
                    1 if was_published else 0, virality_score, status
                )
            )
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
            cursor.execute(query, (link, cooldown_minutes))
            row = cursor.fetchone()
            return (row["count"] > 0) if row else False

    def get_monthly_reply_count(self) -> int:
        """Count replies published in the current calendar month."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM processed_tweets
                WHERE was_published = 1
                AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
                """
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    # --- Thread Operations ---

    def get_thread(self, thread_root_id: str) -> Optional[Dict[str, Any]]:
        """Fetch thread state by root ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM threads WHERE thread_root_id = ?",
                (thread_root_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def create_thread(
        self,
        thread_root_id: str,
        user_handle: str,
        max_turns: int = 2
    ) -> None:
        """Initialize a new active thread."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO threads (
                    thread_root_id, user_handle, current_turn, max_turns, status
                ) VALUES (?, ?, 1, ?, 'ACTIVE')
                """,
                (thread_root_id, user_handle, max_turns)
            )
            conn.commit()

    def advance_thread_turn(self, thread_root_id: str) -> Optional[int]:
        """Increment thread turn count and update timestamp."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE threads
                SET current_turn = current_turn + 1,
                    last_interaction = CURRENT_TIMESTAMP
                WHERE thread_root_id = ?
                """,
                (thread_root_id,)
            )
            cursor.execute(
                "SELECT current_turn, max_turns FROM threads WHERE thread_root_id = ?",
                (thread_root_id,)
            )
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE threads
                SET status = ?, last_interaction = CURRENT_TIMESTAMP
                WHERE thread_root_id = ?
                """,
                (status, thread_root_id)
            )
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
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bot_logs (tweets_scanned, replies_sent, status, error_message)
                VALUES (?, ?, ?, ?)
                """,
                (tweets_scanned, replies_sent, status, error_message)
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_logs(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the most recent run logs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM bot_logs ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
