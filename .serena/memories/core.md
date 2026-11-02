# zioX Core Architecture

AI-powered fact-checking, advocacy, and engagement bot for X (Twitter). Monitors discussions, verifies claims, humanizes replies, and dispatches authoritative counter-arguments or context.

## References

- Technical architecture and dependencies: `mem:tech_stack`
- Development, testing, and system commands: `mem:suggested_commands`
- Code style, design patterns, and structure: `mem:conventions`
- Verification checklist for completed tasks: `mem:task_completion`

## Core Subsystems

- engine/orchestrator.py: Pipeline coordination connecting radar, analysis, verification, humanizer, Telegram dispatcher, and posting.
- engine/telegram_dispatcher.py: Telegram Bot API integration with one-tap X Web Intent buttons, mobile HTML review cards, and webhook management (`set_webhook`, `delete_webhook`).
- engine/radar.py: Monitors timeline and searches for relevant narratives and claims (filters by `max_tweet_age_hours`).
- engine/virality.py: Hybrid virality scoring supporting both fresh breaking tweets (`<60m`) and sustained viral posts (`1h-24h` via `age_hours ** 0.65` decay).
- engine/grounding.py: Fact-checking and grounding engine powered by Gemini.
- engine/humanizer.py: Style, tone modulation, and anti-bot stealth heuristics.
- engine/link_validator.py: Validates evidence URLs and citation links.
- providers/: Interfaces to social platform backends (twikit_provider.py blends `Top` + `Latest` tabs and deduplicates; mock_provider.py).
- database/: Storage & state tracking with Turso/libSQL (turso_client.py, repository.py).
- workers/telegram_webhook/: Zero-cost serverless Cloudflare Worker (`worker.js` + `wrangler.toml`) handling live Telegram commands & inline callbacks directly against Turso HTTP `/v2/pipeline`.

## Community SaaS Architecture (multi-subscriber Telegram)

- Scanner = ONE dedicated X account (twikit cookies); subscribers never touch X credentials. They post via X Web Intent buttons from their own accounts. Bot never auto-posts to X when telegram_review_enabled.
- Flow: demand query (`repository.get_available_subscriber_demand`) -> dynamic radar (`Top` + `Latest` Boolean OR queries per script, `min_faves`, dynamic `limit_per_keyword`, Gaussian jitter, circuit breaker) -> queue -> grounding (batch variations) -> humanizer (link/no-link mix) -> multi-wave sharded dispatch to eligible subscribers until 100% of available subscribers in the run receive at least one post.
- Circuit breaker: 401/403/429/lock -> ScannerCircuitBreakerError -> abort scan, bot_state cooldown (scanner_cooldown_minutes), admin-only alert (TELEGRAM_CHAT_ID / tier=admin).
- Subscriber lifecycle: /start -> pending (ready_confirmed=0) -> /ready or button -> active; ack:<tweet_id> button confirms reply; max_unconfirmed_dispatches in a row -> auto-pause (active=0); HTTP 403 from Telegram -> deactivate.
- Eligibility = ONE SQL query (repository.get_eligible_subscribers_for_tweet): active, ready, lang match, daily quota, not already dispatched. Demand = ONE SQL query (`get_available_subscriber_demand`). Never reintroduce N+1 per-subscriber queries.
- Cohort sharding & dynamic scaling: `target_cohort_size_per_tweet` subscribers per tweet wave; cycle cap and search depth scale dynamically with `math.ceil(demand_total / cohort_size)` and `allow_multi_wave_in_run=True` so 1 to 1,000+ ready users are all served in a single pipeline run.
- Tables: subscribers, dispatches, bot_state (+ tweets/replies). Migrations are additive ALTER lists in repository.py (SUBSCRIBER_MIGRATIONS, DISPATCH_MIGRATIONS); schema auto-applies on Turso and local SQLite.
- Telegram commands: /start /help /stop /style /lang /limit /quota /ready. Default subscriber language is English ('en'). Interactive multiple-choice inline keyboards for commands (/style, /lang, /limit, /help, /start) and callback handlers (set_style, set_lang, set_limit, menu). Handled either via Python polling or 24/7 via the Cloudflare Worker webhook (`sync_subscribers` gracefully skips `409 Conflict` when webhook is active).
- OpenSpec: main specs in openspec/specs/ are source of truth; completed changes archived in openspec/changes/archive/.
