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
    status TEXT DEFAULT 'PROCESSED', -- 'DISCOVERED', 'PROCESSED', 'APPROVED', 'PUBLISHED', 'SKIPPED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

CREATE_SUBSCRIBERS_TABLE = """
CREATE TABLE IF NOT EXISTS subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT UNIQUE NOT NULL,
    username TEXT DEFAULT '',
    tier TEXT DEFAULT 'free', -- 'free', 'pro', 'admin'
    daily_limit INTEGER DEFAULT 3,
    preferred_style TEXT DEFAULT 'any', -- 'any', 'factual', 'sharp', 'historical_legal', 'rhetorical_question'
    active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DISPATCHES_TABLE = """
CREATE TABLE IF NOT EXISTS dispatches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tweet_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    variation_hash TEXT NOT NULL,
    style TEXT DEFAULT 'factual',
    dispatched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(tweet_id, chat_id)
);
"""

CREATE_BOT_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS bot_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INIT_STATEMENTS = [
    CREATE_THREADS_TABLE,
    CREATE_PROCESSED_TWEETS_TABLE,
    CREATE_BOT_LOGS_TABLE,
    CREATE_SUBSCRIBERS_TABLE,
    CREATE_DISPATCHES_TABLE,
    CREATE_BOT_STATE_TABLE,
]
