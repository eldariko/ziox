# Design

## Context

See `proposal.md` for full motivation. Currently, `zioX` has initial multi-user primitives (`subscribers`, `dispatches`, `draft_variations`), but several architectural constraints prevent scaling from 5 to 1,000 subscribers:
1. **Variation & Cycle Caps**: `GroundingEngine.evaluate_and_draft()` generates at most 4 variations (`variations_per_tweet = 4`), and `BotOrchestrator` stops after `max_replies_per_cycle = 2` tweets—capping total community dispatches at 8 messages per cycle.
2. **Single-Wave Tweet Locking**: Once `BotOrchestrator` dispatches a tweet to Telegram, its status becomes `DISPATCHED_TELEGRAM` and `get_pending_tweets()` (`WHERE status = 'DISCOVERED'`) never selects it again, even if 990 other subscribers never received it.
3. **N+1 Database Bottleneck**: `TelegramDispatcher.dispatch_variations_to_subscribers()` fetches all active subscribers and then loops over each subscriber issuing two separate SQL queries (`has_received_tweet` and `get_subscriber_daily_count`). At 1,000 subscribers, processing 10 tweets triggers 20,000 sequential HTTP requests to Turso Cloud.
4. **No Engagement/Readiness Verification**: Users who tap `/start` and then ignore notifications consume unique Gemini variations and daily dispatch slots indefinitely without ever replying on X.
5. **No Language Routing**: Arabic and English tweets are dispatched indiscriminately to all subscribers regardless of whether the subscriber reads Arabic or English.

## Goals / Non-Goals

**Goals:**
- Support any subscriber population from 5 to 1,000+ active users with 100% unique reply text per subscriber.
- Distribute subscribers via **Horizontal Cohort Sharding** (`target_cohort_size_per_tweet`, e.g., 25 subscribers per tweet wave across up to `telegram_tweets_per_cycle` tweets per cycle) so community members cover multiple viral threads without triggering X's coordinated-brigading heuristics.
- Mix link-backed variations with linkless pure-text variations (`no_link_variation_ratio = 0.4`) across every cohort.
- Replace N+1 per-subscriber SQL checks with a single consolidated SQL query (`get_eligible_subscribers_for_tweet`).
- Enforce a **Readiness & Engagement Verification Loop**: require `/ready` (or inline button tap) after `/start`, track `✅ הגבתי ב-X` (`ack:<tweet_id>`) confirmations on dispatched cards, and auto-pause subscribers who ignore `max_unconfirmed_dispatches` consecutive cards.
- Support `/lang <en|ar|both>`, `/limit <number>` (bounded by central ceiling `max_user_daily_limit`), and `/quota` commands.

**Non-Goals:**
- Requiring X OAuth tokens or cookies from subscribers (all replies remain 100% client-side via X Web Intent URLs, preserving 0% automation ban risk for community members).
- Deploying a 24/7 webhook web server (all Telegram commands and inline button `callback_query` events are processed serverlessly via paginated `getUpdates` + `answerCallbackQuery` during scheduled runs).

## Decisions

### Decision 1: Consolidated Single-Query Cohort Selection (`database/repository.py`)
- **Choice**: Add `Repository.get_eligible_subscribers_for_tweet(tweet_id: str, lang: str = "en", limit: int = 25, max_unconfirmed: int = 5)` executing a single SQL query:
  ```sql
  SELECT s.*,
         COALESCE(today_counts.cnt, 0) AS today_count,
         last_disp.last_dispatched_at
  FROM subscribers s
  LEFT JOIN (
      SELECT chat_id, COUNT(*) AS cnt
      FROM dispatches
      WHERE date(dispatched_at) = date('now')
      GROUP BY chat_id
  ) today_counts ON today_counts.chat_id = s.chat_id
  LEFT JOIN (
      SELECT chat_id, MAX(dispatched_at) AS last_dispatched_at
      FROM dispatches
      GROUP BY chat_id
  ) last_disp ON last_disp.chat_id = s.chat_id
  WHERE s.active = 1
    AND s.ready_confirmed = 1
    AND (s.tier = 'admin' OR s.consecutive_unconfirmed < ?)
    AND (s.preferred_lang = 'both' OR s.preferred_lang = ?)
    AND COALESCE(today_counts.cnt, 0) < s.daily_limit
    AND NOT EXISTS (
        SELECT 1 FROM dispatches d
        WHERE d.tweet_id = ? AND d.chat_id = s.chat_id
    )
  ORDER BY
    CASE WHEN s.tier = 'admin' THEN 0 WHEN s.tier = 'pro' THEN 1 ELSE 2 END ASC,
    COALESCE(last_disp.last_dispatched_at, '1970-01-01') ASC,
    s.id ASC
  LIMIT ?
  ```
- **Rationale**: Replaces 2,000 N+1 queries per tweet with 1 query. Prioritizes `admin` and `pro` tiers first, then applies strict Round-Robin (`last_dispatched_at ASC`) so every subscriber gets a fair turn across horizontal cohorts.
- **Alternatives Considered**: Filtering in Python after fetching all `dispatches` rows (rejected because `dispatches` grows unbounded over time).

### Decision 2: Demand-Driven Batch Variation Generation (`engine/grounding.py`, `engine/orchestrator.py`)
- **Choice**:
  - Before calling Gemini for a queued tweet, `BotOrchestrator` detects the tweet's language (`ar` if Arabic script `\u0600`–`\u06FF` is present, else `en`) and checks `eligible_subs = repo.get_eligible_subscribers_for_tweet(tweet.id, lang=tweet_lang, limit=settings.target_cohort_size_per_tweet)`.
  - Define `needed_count = max(1, len(eligible_subs))` (if `eligible_subs` is empty and legacy `self.chat_ids` fallback is used, default to `settings.variations_per_tweet`).
  - Add `GroundingEngine.generate_variations_batch(tweet_text, author_handle, total_variations)` which calls `evaluate_and_draft` in chunks of up to `max_variations_per_gemini_call` (default `10`). If `total_variations > 10` (e.g., 25), subsequent calls pass an `excluded_texts` list in the prompt and vary rhetorical sub-angles (`factual`, `sharp`, `historical_legal`, `rhetorical_question`, `comparative_context`, `concise_punchy`, `data_breakdown`, `moral_consistency`) so every subscriber in the 25-user cohort receives a genuinely unique text.
- **Rationale**: Scales dynamically—if 5 users are registered, only 5 variations are requested in 1 API call; if 1,000 users are registered, each tweet wave generates exactly `target_cohort_size_per_tweet` (e.g., 25) variations in 2–3 fast Flash-Lite calls.

### Decision 3: Link-to-Linkless Cohort Ratio (`engine/humanizer.py`)
- **Choice**: Add `no_link_variation_ratio: float = 0.0` parameter to `Humanizer.diversify_links_for_variations()` (configured via `settings.no_link_variation_ratio = 0.4` in `BotOrchestrator`). For a cohort of $K$ variations, approximately $\lfloor K \times \text{no\_link\_variation\_ratio} \rfloor$ variations (distributed evenly, e.g., every 2nd or 3rd item) are sanitized with `link=None` and `auto_attach_whitelist=False` so they contain zero URLs, while the remaining variations cycle through distinct URLs from `match_whitelisted_links_pool()`.
- **Rationale**: Prevents 25+ people from posting URLs in the same X thread simultaneously (which triggers X link-spam suppression) and boosts reply visibility since X's ranking algorithm favors pure-text replies.

### Decision 4: Pre-Activation Readiness Gate & Engagement Auto-Pause (`engine/telegram_dispatcher.py`, `database/repository.py`)
- **Choice**:
  - **Schema additions**:
    - `subscribers`: `preferred_lang TEXT DEFAULT 'both'`, `ready_confirmed BOOLEAN DEFAULT 1` (for seeded admins; `0` for new `/start` non-admin users), `consecutive_unconfirmed INTEGER DEFAULT 0`, `total_confirmed_replies INTEGER DEFAULT 0`.
    - `dispatches`: `confirmed BOOLEAN DEFAULT 0`, `confirmed_at TIMESTAMP`.
  - **Onboarding Gate (`/start` -> `/ready` or Callback `ready:confirm`)**:
    - When a regular user sends `/start`, `upsert_subscriber` sets `ready_confirmed = False` (unless `tier == 'admin'`) and sends a Hebrew welcome message explaining how the system works, with an inline button `[✅ אני מוכן לקבל פוסטים ולהגיב]` (`callback_data="ready:confirm"`) and text fallback `/ready`.
    - When `sync_subscribers` receives `callback_query` with `data == "ready:confirm"` or text `/ready`, it calls `repository.confirm_subscriber_ready(chat_id)`, setting `ready_confirmed = 1`, `active = 1`, and `consecutive_unconfirmed = 0`.
  - **Per-Card Action Confirmation (`ack:<tweet_id>`)**:
    - Every dispatched review card includes 3 buttons:
      1. `🚀 צייץ תגובה ב-X` (Web Intent URL)
      2. `✅ הגבתי ב-X (אשר ביצוע)` (`callback_data=f"ack:{tweet_id}"`)
      3. `👀 צפה בציוץ המקורי` (Original Tweet URL)
    - When a dispatch is recorded for a non-admin subscriber, `consecutive_unconfirmed` increments by 1.
    - If `consecutive_unconfirmed >= settings.max_unconfirmed_dispatches` (default `5`), `repository.pause_unresponsive_subscribers(max_unconfirmed)` (or `sync_subscribers`) marks `ready_confirmed = 0, active = 0` and sends a Hebrew pause alert with `[🔔 חזרתי - אני מוכן להגיב שוב]` (`callback_data="ready:confirm"`).
    - Clicking `✅ הגבתי ב-X` (`ack:<tweet_id>`) marks the dispatch confirmed, increments `total_confirmed_replies`, and resets `consecutive_unconfirmed = 0`.
- **Rationale**: Works 100% serverlessly with `getUpdates` (which returns both `message` and `callback_query` updates) and guarantees that ghost users stop consuming variations until they explicitly confirm readiness.

### Decision 5: Multi-Wave Campaign Status (`database/repository.py`, `engine/orchestrator.py`)
- **Choice**: Update `Repository.get_pending_tweets()` to return tweets with `status IN ('DISCOVERED', 'DISPATCHED_WAVE')` ordered by `CASE WHEN status = 'DISCOVERED' THEN 0 ELSE 1 END, virality_score DESC`. When a tweet is dispatched to a cohort in Telegram mode and more active subscribers still haven't received it, set its status to `DISPATCHED_WAVE` (or `DISPATCHED_TELEGRAM` once all active subscribers have received it or when running in single-user mode).
- **Rationale**: Allows a high-virality post to serve Cohort 1 (subscribers 1–25) in wave 1, and Cohort 2 (subscribers 26–50) in a subsequent wave if needed, while prioritizing brand-new `DISCOVERED` tweets first.

## Risks / Trade-offs

- **[Risk] Existing unit tests expect `/start` subscribers to be immediately eligible without a separate `/ready` step** → **Mitigation**: Default `upsert_subscriber(..., ready_confirmed=True)` at the repository method level so existing unit tests calling `repo.upsert_subscriber()` directly continue to work without modification, while `TelegramDispatcher.sync_subscribers()` supports a `require_readiness_confirm: bool = False` (or defaults `/start` onboarding to `ready_confirmed=True` unless `require_readiness_gate` is enabled, OR sets `ready_confirmed=False` on `/start` and provides `/ready` while keeping backward compatibility in existing test fixtures). Let's inspect `tests/test_telegram_dispatcher.py` before finalizing tasks to ensure zero regressions in existing tests!
- **[Risk] Telegram rate limits when dispatching to 250+ users in one cycle** → **Mitigation**: Add a small configurable pacing delay (`telegram_send_delay_seconds = 0.04`, ~25 msgs/sec) and `HTTP 429` `retry_after` handling in `TelegramDispatcher`, plus immediate `deactivate_subscriber(chat_id)` on `HTTP 403`.

## Migration Plan

1. **Idempotent Schema Migration**: `Repository._init_db()` checks `PRAGMA table_info(subscribers)` and `PRAGMA table_info(dispatches)` on both local SQLite and remote Turso, executing `ALTER TABLE ... ADD COLUMN ...` for `preferred_lang`, `ready_confirmed`, `consecutive_unconfirmed`, `total_confirmed_replies`, `confirmed`, and `confirmed_at`.
2. **Backward Compatibility**: Existing `subscribers` rows default to `preferred_lang = 'both'`, `ready_confirmed = 1`, and `consecutive_unconfirmed = 0`.
