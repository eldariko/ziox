"""SQLite database schema and initialization for zioX."""

CREATE_THREADS_TABLE = """
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_root_id TEXT UNIQUE NOT NULL,
    user_handle TEXT NOT NULL,
    current_turn INTEGER DEFAULT 1,
    max_turns INTEGER DEFAULT 2,
    status TEXT DEFAULT 'ACTIVE', -- 'ACTIVE', 'COMPLETED', 'DROPPED_TOXIC'
    last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PROCESSED_TWEETS_TABLE = """
CREATE TABLE IF NOT EXISTS processed_tweets (
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_tweet_id) REFERENCES processed_tweets(tweet_id)
);
"""

CREATE_BOT_LOGS_TABLE = """
CREATE TABLE IF NOT EXISTS bot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tweets_scanned INTEGER DEFAULT 0,
    replies_sent INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT
);
"""

INIT_STATEMENTS = [
    CREATE_THREADS_TABLE,
    CREATE_PROCESSED_TWEETS_TABLE,
    CREATE_BOT_LOGS_TABLE
]
