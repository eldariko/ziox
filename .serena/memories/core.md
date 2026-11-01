# zioX Core Architecture

AI-powered fact-checking, advocacy, and engagement bot for X (Twitter). Monitors discussions, verifies claims, humanizes replies, and dispatches authoritative counter-arguments or context.

## References

- Technical architecture and dependencies: `mem:tech_stack`
- Development, testing, and system commands: `mem:suggested_commands`
- Code style, design patterns, and structure: `mem:conventions`
- Verification checklist for completed tasks: `mem:task_completion`

## Core Subsystems

- engine/orchestrator.py: Pipeline coordination connecting radar, analysis, verification, humanizer, Telegram dispatcher, and posting.
- engine/telegram_dispatcher.py: Telegram Bot API integration with one-tap X Web Intent buttons and mobile HTML review cards.
- engine/radar.py: Monitors timeline and searches for relevant narratives and claims.
- engine/grounding.py: Fact-checking and grounding engine powered by Gemini.
- engine/humanizer.py: Style, tone modulation, and anti-bot stealth heuristics.
- engine/link_validator.py: Validates evidence URLs and citation links.
- providers/: Interfaces to social platform backends (twikit_provider.py, mock_provider.py).
- database/: Storage & state tracking with Turso/libSQL (turso_client.py, repository.py).

## Community SaaS Architecture (multi-subscriber Telegram)

- Scanner = ONE dedicated X account (twikit cookies); subscribers never touch X credentials. They post via X Web Intent buttons from their own accounts. Bot never auto-posts to X when telegram_review_enabled.
- Flow: radar (Boolean OR queries per script, min_faves, Gaussian jitter, circuit breaker) -> queue -> grounding (batch variations) -> humanizer (link/no-link mix) -> sharded dispatch to eligible subscribers.
- Circuit breaker: 401/403/429/lock -> ScannerCircuitBreakerError -> abort scan, bot_state cooldown (scanner_cooldown_minutes), admin-only alert (TELEGRAM_CHAT_ID / tier=admin).
- Subscriber lifecycle: /start -> pending (ready_confirmed=0) -> /ready or button -> active; ack:<tweet_id> button confirms reply; max_unconfirmed_dispatches in a row -> auto-pause (active=0); HTTP 403 from Telegram -> deactivate.
- Eligibility = ONE SQL query (repository.get_eligible_subscribers_for_tweet): active, ready, lang match, daily quota, not already dispatched. Never reintroduce N+1 per-subscriber queries.
- Cohort sharding: target_cohort_size_per_tweet subscribers per tweet, telegram_tweets_per_cycle tweets per cycle; each subscriber gets a unique text variation.
- Tables: subscribers, dispatches, bot_state (+ tweets/replies). Migrations are additive ALTER lists in repository.py (SUBSCRIBER_MIGRATIONS, DISPATCH_MIGRATIONS); schema auto-applies on Turso and local SQLite.
- Telegram commands: /start /stop /style /lang /limit /quota /ready. Pipeline syncs getUpdates once per run; --poll-telegram daemon gives real-time handling.
- OpenSpec: main specs in openspec/specs/ are source of truth; completed changes archived in openspec/changes/archive/.
