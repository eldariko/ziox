"""Database repository providing data access and persistence for zioX."""

import atexit
import hashlib
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from database.schema import INIT_STATEMENTS, CREATE_PROCESSED_TWEETS_TABLE
from database.turso_client import TursoClient

logger = logging.getLogger(__name__)


class Repository:
    """
    Manages database queries for threads, tweets, subscribers, dispatches, state, and logs.
    Supports dual-mode engine:
    - Local Mode (default): standard Python sqlite3 with `db_path`.
    - Cloud Mode (Turso / libSQL): remote HTTP connection via native TursoClient (/v2/pipeline).
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
        self._remote_client: Optional[TursoClient] = None

        if self.is_remote:
            logger.info(f"[REPOSITORY] Connecting to Turso Cloud SQLite endpoint: {self.turso_url}")
            self._remote_client = TursoClient(
                url=self.turso_url,
                auth_token=self.turso_auth_token
            )
            atexit.register(self.close)
        else:
            logger.info(f"[REPOSITORY] Using local SQLite database at: {self.db_path}")

        self._init_db()

    def close(self) -> None:
        """Close database connections and cleanup open sessions."""
        if self._remote_client is not None:
            try:
                self._remote_client.close()
            except Exception:
                pass
            self._remote_client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Local sqlite3 connection fallback."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
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
                conn.commit()
                return cursor

    def _init_db(self) -> None:
        """Create tables if they do not exist, and migrate columns/constraints."""
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
            self._migrate_remove_parent_tweet_fk_remote()
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
                self._migrate_remove_parent_tweet_fk_local(conn)

    def _migrate_remove_parent_tweet_fk_remote(self) -> None:
        """Remove foreign key constraint on parent_tweet_id in remote Turso database if present."""
        try:
            fk_res = self._remote_client.execute("PRAGMA foreign_key_list(processed_tweets)")
        except Exception as e:
            logger.warning(f"[MIGRATION] Failed checking foreign key list on remote DB: {e}")
            return

        has_fk = False
        for row in fk_res.rows:
            from_col = row.get("from") if isinstance(row, dict) else (row[3] if len(row) > 3 else None)
            if from_col == "parent_tweet_id":
                has_fk = True
                break

        if not has_fk:
            return

        logger.info("[MIGRATION] Migrating remote processed_tweets table to remove foreign key constraint on parent_tweet_id...")
        self._remote_client.execute("DROP TABLE IF EXISTS processed_tweets_migration_temp")
        temp_create = CREATE_PROCESSED_TWEETS_TABLE.replace("processed_tweets", "processed_tweets_migration_temp")
        self._remote_client.execute(temp_create)

        info_res = self._remote_client.execute("PRAGMA table_info(processed_tweets)")
        existing_cols = [row["name"] for row in info_res.rows]
        temp_info = self._remote_client.execute("PRAGMA table_info(processed_tweets_migration_temp)")
        target_cols = [row["name"] for row in temp_info.rows]
        common_cols = [col for col in existing_cols if col in target_cols]
        cols_str = ", ".join(common_cols)

        self._remote_client.execute(
            f"INSERT INTO processed_tweets_migration_temp ({cols_str}) SELECT {cols_str} FROM processed_tweets"
        )
        self._remote_client.execute("DROP TABLE processed_tweets")
        self._remote_client.execute("ALTER TABLE processed_tweets_migration_temp RENAME TO processed_tweets")
        logger.info("[MIGRATION] Successfully removed foreign key constraint from remote processed_tweets.")

    def _migrate_remove_parent_tweet_fk_local(self, conn: sqlite3.Connection) -> None:
        """Remove foreign key constraint on parent_tweet_id in local SQLite database if present."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_key_list(processed_tweets)")
        fks = cursor.fetchall()
        has_parent_fk = any(
            (row["from"] if isinstance(row, sqlite3.Row) else row[3]) == "parent_tweet_id"
            for row in fks
        )
        if not has_parent_fk:
            return

        logger.info("[MIGRATION] Migrating local processed_tweets table to remove foreign key constraint on parent_tweet_id...")
        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute("DROP TABLE IF EXISTS processed_tweets_migration_temp")
        temp_create = CREATE_PROCESSED_TWEETS_TABLE.replace("processed_tweets", "processed_tweets_migration_temp")
        cursor.execute(temp_create)

        cursor.execute("PRAGMA table_info(processed_tweets)")
        existing_cols = [col["name"] for col in cursor.fetchall()]
        cursor.execute("PRAGMA table_info(processed_tweets_migration_temp)")
        target_cols = [col["name"] for col in cursor.fetchall()]
        common_cols = [col for col in existing_cols if col in target_cols]
        cols_str = ", ".join(common_cols)

        cursor.execute(
            f"INSERT INTO processed_tweets_migration_temp ({cols_str}) SELECT {cols_str} FROM processed_tweets"
        )
        cursor.execute("DROP TABLE processed_tweets")
        cursor.execute("ALTER TABLE processed_tweets_migration_temp RENAME TO processed_tweets")
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON")
        logger.info("[MIGRATION] Successfully removed foreign key constraint from local processed_tweets.")

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

    # --- Phase C: Multi-User Subscribers, Dispatches Ledger & Bot State ---

    def upsert_subscriber(
        self,
        chat_id: str,
        username: str = "",
        tier: str = "free",
        daily_limit: int = 3,
        preferred_style: str = "any",
        active: bool = True,
    ) -> None:
        """Insert a new Telegram subscriber or reactivate an existing one."""
        clean_id = str(chat_id).strip()
        active_int = 1 if active else 0
        query = """
            INSERT INTO subscribers (chat_id, username, tier, daily_limit, preferred_style, active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = CASE WHEN excluded.username != '' THEN excluded.username ELSE subscribers.username END,
                active = excluded.active,
                updated_at = CURRENT_TIMESTAMP
        """
        params = [clean_id, username, tier, daily_limit, preferred_style, active_int]
        if self.is_remote:
            self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()

    def deactivate_subscriber(self, chat_id: str) -> None:
        """Mark a subscriber as inactive (/stop)."""
        clean_id = str(chat_id).strip()
        query = """
            UPDATE subscribers
            SET active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
        """
        if self.is_remote:
            self._remote_client.execute(query, [clean_id])
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (clean_id,))
                conn.commit()

    def update_subscriber_style(self, chat_id: str, preferred_style: str) -> None:
        """Update a subscriber's preferred reply style (/style <style>)."""
        clean_id = str(chat_id).strip()
        query = """
            UPDATE subscribers
            SET preferred_style = ?, updated_at = CURRENT_TIMESTAMP
            WHERE chat_id = ?
        """
        params = [preferred_style.strip().lower(), clean_id]
        if self.is_remote:
            self._remote_client.execute(query, params)
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()

    def get_active_subscribers(self) -> List[Dict[str, Any]]:
        """
        Return all active subscribers ordered by least-recently-dispatched first
        (Round-Robin sharding fairness).
        """
        query = """
            SELECT s.*,
                   (SELECT MAX(d.dispatched_at) FROM dispatches d WHERE d.chat_id = s.chat_id) AS last_dispatched_at
            FROM subscribers s
            WHERE s.active = 1
            ORDER BY COALESCE(last_dispatched_at, '1970-01-01') ASC, s.id ASC
        """
        if self.is_remote:
            res = self._remote_client.execute(query)
            return [dict(row) for row in res.rows]
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [dict(row) for row in cursor.fetchall()]

    def get_admin_chat_ids(self) -> List[str]:
        """Return chat_ids of active subscribers with tier = 'admin'."""
        query = "SELECT chat_id FROM subscribers WHERE active = 1 AND tier = 'admin'"
        if self.is_remote:
            res = self._remote_client.execute(query)
            return [str(row["chat_id"]) for row in res.rows]
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [str(row["chat_id"]) for row in cursor.fetchall()]

    @staticmethod
    def compute_variation_hash(text: str) -> str:
        """Compute deterministic SHA-256 short digest for a reply variation text."""
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]

    def record_dispatch(
        self,
        tweet_id: str,
        chat_id: str,
        variation_text_or_hash: str,
        style: str = "factual",
    ) -> bool:
        """
        Record that a specific reply variation for `tweet_id` was dispatched to `chat_id`.
        Returns True if newly recorded, False if already dispatched to this chat_id.
        """
        clean_chat = str(chat_id).strip()
        v_hash = (
            variation_text_or_hash
            if len(variation_text_or_hash) == 16 and all(c in "0123456789abcdef" for c in variation_text_or_hash)
            else self.compute_variation_hash(variation_text_or_hash)
        )
        query = """
            INSERT OR IGNORE INTO dispatches (tweet_id, chat_id, variation_hash, style)
            VALUES (?, ?, ?, ?)
        """
        params = [str(tweet_id), clean_chat, v_hash, style]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            return res.rows_affected > 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                conn.commit()
                return cursor.rowcount > 0

    def has_received_tweet(self, tweet_id: str, chat_id: str) -> bool:
        """Check whether `chat_id` has already received a review card for `tweet_id`."""
        query = "SELECT 1 FROM dispatches WHERE tweet_id = ? AND chat_id = ?"
        params = [str(tweet_id), str(chat_id).strip()]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            return len(res.rows) > 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                return cursor.fetchone() is not None

    def get_used_variation_hashes(self, tweet_id: str) -> List[str]:
        """Return all `variation_hash` values already dispatched for `tweet_id` across any subscriber."""
        query = "SELECT variation_hash FROM dispatches WHERE tweet_id = ?"
        if self.is_remote:
            res = self._remote_client.execute(query, [str(tweet_id)])
            return [str(row["variation_hash"]) for row in res.rows]
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (str(tweet_id),))
                return [str(row["variation_hash"]) for row in cursor.fetchall()]

    def get_subscriber_daily_count(self, chat_id: str) -> int:
        """Count how many dispatches `chat_id` has received today (UTC date)."""
        query = """
            SELECT COUNT(*) as count FROM dispatches
            WHERE chat_id = ?
            AND date(dispatched_at) = date('now')
        """
        params = [str(chat_id).strip()]
        if self.is_remote:
            res = self._remote_client.execute(query, params)
            row = res.rows[0] if res.rows else None
            return int(row["count"]) if row else 0
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                return int(row["count"]) if row else 0

    def get_state(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve a persistent key-value state string from `bot_state`."""
        query = "SELECT value FROM bot_state WHERE key = ?"
        if self.is_remote:
            res = self._remote_client.execute(query, [key])
            return str(res.rows[0]["value"]) if res.rows else default
        else:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (key,))
                row = cursor.fetchone()
                return str(row["value"]) if row else default

    def set_state(self, key: str, value: str) -> None:
        """Upsert a persistent key-value state string into `bot_state`."""
        query = """
            INSERT INTO bot_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """
        params = [key, str(value)]
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
