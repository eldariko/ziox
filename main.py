"""Command Line Interface for zioX Bot."""

import argparse
import sys
import logging
import os
import time
from datetime import datetime

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from config.settings import get_settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from providers.zernio_provider import ZernioTwitterProvider
from providers.twikit_provider import TwikitTwitterProvider
from engine.grounding import GroundingEngine
from engine.orchestrator import BotOrchestrator
from engine.radar import DiscoveryRadar, extract_tweet_id
from engine.telegram_dispatcher import TelegramDispatcher
from engine.summary_reporter import SummaryReporter

from engine.security import setup_secure_logging

setup_secure_logging(logging.INFO)
logger = logging.getLogger("zioX")


def show_queue(repo: Repository) -> None:
    """Print all candidate tweets currently waiting in the DISCOVERED queue."""
    pending = repo.get_pending_tweets(limit=25)
    print("\n" + "=" * 65)
    print("               zioX CANDIDATE TWEET QUEUE")
    print("=" * 65)
    if not pending:
        print("  Queue is empty (no DISCOVERED tweets awaiting action).")
    else:
        for idx, item in enumerate(pending, 1):
            print(f" {idx}. Tweet ID: {item['tweet_id']} | @{item['author_handle']}")
            print(f"    Virality Score: {item['virality_score']} | Created: {item['created_at']}")
            snippet = item['tweet_text'][:90] + "..." if len(item['tweet_text']) > 90 else item['tweet_text']
            print(f"    Text: \"{snippet}\"")
            print("    " + "-" * 55)
    print("=" * 65 + "\n")


def show_status(repo: Repository, settings) -> None:
    """Print current operational status and statistics."""
    monthly_count = repo.get_monthly_reply_count()
    logs = repo.get_recent_logs(limit=5)
    demand = repo.get_available_subscriber_demand(max_unconfirmed=settings.max_unconfirmed_dispatches)

    print("\n" + "=" * 55)
    print("                zioX STATUS REPORT")
    print("=" * 55)
    db_target = f"Turso Cloud ({settings.turso_database_url})" if settings.turso_database_url else f"Local SQLite ({settings.database_path})"
    print(f"Database Target      : {db_target}")
    print(f"Twitter Provider     : {settings.twitter_provider}")
    print(f"Dry Run Mode         : {settings.dry_run}")
    print(f"Monthly Reply Usage  : {monthly_count} / {settings.monthly_max_replies}")
    print(f"Virality Threshold   : {settings.virality_threshold}")
    print(f"Max Tweet Age        : {settings.max_tweet_age_hours}h")
    print(f"Available Subscribers: {demand['total']} (EN: {demand['en']} | AR: {demand['ar']})")
    print(f"Max Thread Turns     : {settings.max_thread_turns}")
    print("-" * 55)
    print("Recent Execution Logs:")
    if not logs:
        print("  (No runs recorded yet)")
    else:
        for log in logs:
            err = f" | Error: {log['error_message']}" if log['error_message'] else ""
            print(f"  [{log['run_timestamp']} UTC] Status: {log['status']} | Scanned: {log['tweets_scanned']} | Replies/Dispatches: {log['replies_sent']}{err}")
    print("=" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(description="zioX: AI Fact-Checking & Advocacy Agent for X")
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display bot status, database statistics, and recent execution logs"
    )
    parser.add_argument(
        "--radar",
        action="store_true",
        help="Run Discovery Radar across all search keywords to find and queue candidate posts"
    )
    parser.add_argument(
        "--queue-tweet",
        type=str,
        help="Queue a specific tweet by URL or numeric ID into the database queue"
    )
    parser.add_argument(
        "--text",
        type=str,
        default="",
        help="Tweet text (used when enqueuing via --queue-tweet)"
    )
    parser.add_argument(
        "--author",
        type=str,
        default="unknown",
        help="Tweet author handle (used when enqueuing via --queue-tweet)"
    )
    parser.add_argument(
        "--likes",
        type=int,
        default=0,
        help="Tweet likes count (used when enqueuing via --queue-tweet)"
    )
    parser.add_argument(
        "--retweets",
        type=int,
        default=0,
        help="Tweet retweets count (used when enqueuing via --queue-tweet)"
    )
    parser.add_argument(
        "--replies",
        type=int,
        default=0,
        help="Tweet replies count (used when enqueuing via --queue-tweet)"
    )
    parser.add_argument(
        "--queue-list",
        action="store_true",
        help="Display all candidate tweets currently in the queue"
    )
    parser.add_argument(
        "--process-queue",
        action="store_true",
        help="Process candidate tweets waiting in the DISCOVERED queue"
    )
    parser.add_argument(
        "--process-tweet",
        type=str,
        help="Target and process a specific tweet by URL or ID end-to-end"
    )
    parser.add_argument(
        "--pipeline",
        action="store_true",
        help="Execute autonomous unified pipeline: Discovery Radar -> Queue Processing -> Stealth Dispatch"
    )
    parser.add_argument(
        "--start-jitter",
        type=float,
        default=None,
        help="Maximum random start delay in minutes before executing pipeline (overrides setting)"
    )
    parser.add_argument(
        "--no-jitter",
        action="store_true",
        help="Disable start jitter delay completely for immediate execution"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Execute a single monitoring, verification, and engagement cycle"
    )
    parser.add_argument(
        "--sync-telegram",
        action="store_true",
        help="Poll Telegram getUpdates once to sync subscribers, commands, and callback confirmations"
    )
    parser.add_argument(
        "--poll-telegram",
        action="store_true",
        help="Run continuous live polling daemon for Telegram commands (/start, /ready, /lang, /quota) and button callbacks"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds for --poll-telegram (default: 2.0s)"
    )
    parser.add_argument(
        "--set-webhook",
        type=str,
        default=None,
        help="Register a serverless HTTPS Webhook URL (e.g. Cloudflare Worker) with Telegram Bot API"
    )
    parser.add_argument(
        "--webhook-secret",
        type=str,
        default=None,
        help="Optional secret token for X-Telegram-Bot-Api-Secret-Token verification when using --set-webhook"
    )
    parser.add_argument(
        "--delete-webhook",
        action="store_true",
        help="Delete the active Telegram Webhook and re-enable getUpdates polling"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Override DRY_RUN and allow live publishing to X"
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "zernio", "twikit"],
        help="Override Twitter provider ('mock', 'zernio', or 'twikit')"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="Override minimum virality threshold score (e.g. --threshold 1.0)"
    )
    parser.add_argument(
        "--min-faves",
        type=int,
        default=None,
        help="Minimum likes filter in search query (e.g. --min-faves 5) to filter out 0-engagement noise"
    )
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Enable Human-in-the-Loop review mode before any reply is sent"
    )
    parser.add_argument(
        "--summary-file",
        type=str,
        default=None,
        help="Optional path to write visual Markdown report (defaults to GITHUB_STEP_SUMMARY if set in environment)"
    )

    args = parser.parse_args()
    settings = get_settings()

    if args.live:
        settings.dry_run = False

    if args.provider:
        settings.twitter_provider = args.provider

    if args.threshold is not None:
        settings.virality_threshold = args.threshold

    if args.min_faves is not None:
        settings.search_min_faves = args.min_faves

    repo = Repository(
        db_path=settings.database_path,
        turso_url=settings.turso_database_url,
        turso_auth_token=settings.turso_auth_token
    )

    if args.status:
        show_status(repo, settings)
        return

    if args.set_webhook or args.delete_webhook:
        if not settings.telegram_bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not configured in .env. Exiting.")
            sys.exit(1)
        dispatcher = TelegramDispatcher(
            bot_token=settings.telegram_bot_token,
            chat_ids=settings.telegram_chat_id
        )
        if args.set_webhook:
            ok = dispatcher.set_webhook(
                webhook_url=args.set_webhook,
                secret_token=args.webhook_secret,
            )
            if ok:
                print(f"[zioX Telegram] Successfully registered Webhook: {args.set_webhook}")
            else:
                print("[zioX Telegram] Failed to register Webhook. Check logs for details.")
                sys.exit(1)
            return

        if args.delete_webhook:
            ok = dispatcher.delete_webhook()
            if ok:
                print("[zioX Telegram] Successfully deleted Webhook. getUpdates polling is now active.")
            else:
                print("[zioX Telegram] Failed to delete Webhook. Check logs for details.")
                sys.exit(1)
            return

    if args.sync_telegram or args.poll_telegram:
        if not settings.telegram_bot_token:
            logger.error("TELEGRAM_BOT_TOKEN is not configured in .env. Exiting.")
            sys.exit(1)
        dispatcher = TelegramDispatcher(
            bot_token=settings.telegram_bot_token,
            chat_ids=settings.telegram_chat_id
        )
        # Register bot commands in Telegram UI
        dispatcher.setup_bot_commands()
        if args.sync_telegram:
            print("[zioX Telegram] Syncing updates from Telegram servers...")
            summary = dispatcher.sync_subscribers(
                repository=repo,
                default_daily_limit=3,
                max_user_daily_limit=settings.max_user_daily_limit,
            )
            print(f"[zioX Telegram] Sync completed: {summary}")
            return

        if args.poll_telegram:
            print(f"[zioX Telegram] Starting live continuous polling daemon (interval: {args.poll_interval}s)...")
            print("  The bot is now listening for /start, /ready, /lang, /limit, /quota and button clicks in real time.")
            print("  Press Ctrl+C to terminate.")
            try:
                while True:
                    summary = dispatcher.sync_subscribers(
                        repository=repo,
                        default_daily_limit=3,
                        max_user_daily_limit=settings.max_user_daily_limit,
                    )
                    any_activity = any(v > 0 for v in summary.values())
                    if any_activity:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Processed Telegram updates: {summary}")
                    time.sleep(args.poll_interval)
            except KeyboardInterrupt:
                print("\n[zioX Telegram] Polling daemon stopped by user.")
            return

    if args.queue_list:
        show_queue(repo)
        return

    if args.queue_tweet:
        radar = DiscoveryRadar(repo)
        try:
            res = radar.enqueue_manual(
                url_or_id=args.queue_tweet,
                author_handle=args.author,
                tweet_text=args.text,
                likes=args.likes,
                retweets=args.retweets,
                replies=args.replies
            )
            print("\n[zioX Radar] Tweet Enqueue Result:")
            print(f"  Tweet ID       : {res['tweet_id']}")
            print(f"  Author         : @{res['author']}")
            print(f"  Virality Score : {res['virality_score']} [{res['tier']}]")
            print(f"  Queue Status   : {res['status']} (Newly Enqueued: {res['newly_enqueued']})\n")
        except Exception as e:
            logger.error(f"Failed to enqueue tweet: {e}")
            sys.exit(1)
        return

    # Choose Twitter provider
    if settings.twitter_provider == "twikit":
        provider = TwikitTwitterProvider(
            auth_token=settings.x_auth_token,
            ct0=settings.x_ct0,
            cookies_file=settings.x_cookies_file
        )
    elif settings.twitter_provider == "zernio":
        if not settings.zernio_api_key:
            logger.error("ZERNIO_API_KEY is not configured in .env. Exiting.")
            sys.exit(1)
        provider = ZernioTwitterProvider(
            api_key=settings.zernio_api_key,
            twitter_account_id=settings.zernio_twitter_account_id
        )
    else:
        provider = MockTwitterProvider()

    if args.radar:
        radar = DiscoveryRadar(repo)
        demand = repo.get_available_subscriber_demand(max_unconfirmed=settings.max_unconfirmed_dispatches)
        import math
        needed_waves = max(settings.telegram_tweets_per_cycle, math.ceil(demand["total"] / max(1, settings.target_cohort_size_per_tweet)))
        dynamic_limit = max(15, min(50, needed_waves * 2))
        print(f"\n[zioX Radar] Scanning {len(settings.search_keywords)} target keywords (Provider: {settings.twitter_provider}, Demand: {demand['total']}, Limit/Query: {dynamic_limit})...")
        discovered = radar.scan_keywords(
            provider=provider,
            keywords=settings.search_keywords,
            limit_per_keyword=dynamic_limit,
            min_virality_score=settings.virality_threshold,
            combine_queries=settings.combine_search_queries,
            max_keywords_per_query=settings.max_keywords_per_query,
            min_search_delay_seconds=settings.min_search_delay_seconds,
            max_search_delay_seconds=settings.max_search_delay_seconds,
            dry_run=settings.dry_run,
            min_faves=settings.search_min_faves,
            max_tweet_age_hours=settings.max_tweet_age_hours,
        )
        print(f"[zioX Radar] Scan complete. Enqueued {len(discovered)} candidate tweets into database.")
        for item in discovered:
            print(f"  * [{item['tier']}] Tweet {item['tweet_id']} by @{item['author']} (Score: {item['virality_score']}) [Keyword: {item['keyword']}]")
        show_queue(repo)
        return

    # Grounding engine
    grounding = GroundingEngine(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
        enable_search=settings.gemini_search_grounding
    )

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=grounding
    )

    # Unified Pipeline Execution (External Scheduler / Cron Target)
    if args.pipeline:
        radar = DiscoveryRadar(repo)
        mode_label = "Interactive" if args.interactive else "Autonomous"
        print(f"\n[zioX Pipeline] Starting unified pipeline (Mode: {mode_label}, Provider: {settings.twitter_provider}, Dry Run: {settings.dry_run})...")
        start_jitter = 0.0 if args.no_jitter else args.start_jitter
        report = orchestrator.run_full_pipeline(
            radar=radar,
            start_jitter_minutes=start_jitter,
            interactive=args.interactive
        )
        print(f"[zioX Pipeline] Pipeline finished with status: {report['status']}")
        print(f"                Discovered tweets : {report.get('discovered_count', 0)}")
        print(f"                Tweets processed  : {report.get('processed', 0)}")
        print(f"                Dispatched waves  : {report.get('replies_sent', 0)}")
        print(f"                Subscribers served: {report.get('subscribers_served', 0)}")
        if report.get("details"):
            print(f"                Details           : {report['details']}")
        if report.get("results"):
            print("\nGenerated Responses:")
            for item in report["results"]:
                print(f" - Tweet ID: {item['tweet_id']} (@{item['author']}) | Score: {item['virality_score']}")
                print(f"   Claim: {item['claim']}")
                print(f"   Reply: {item['reply']}")
                print(f"   Published: {item['published']}\n")

        if args.summary_file:
            written_to = SummaryReporter.generate_and_publish(
                run_report=report,
                settings=settings,
                repository=repo,
                target_file=args.summary_file,
            )
            if written_to:
                print(f"[zioX Summary] Markdown report written to: {written_to}")

        show_status(repo, settings)
        return

    # Process queue or targeted tweet
    if args.process_queue or args.process_tweet:
        target_id = extract_tweet_id(args.process_tweet) if args.process_tweet else None
        mode_label = "Interactive" if args.interactive else "Standard"
        print(f"\n[zioX Responder] Processing queue (Mode: {mode_label}, Provider: {settings.twitter_provider}, Dry Run: {settings.dry_run})...")
        report = orchestrator.process_queue(
            interactive=args.interactive,
            target_tweet_id=target_id
        )
        print(f"[zioX Responder] Queue processing finished with status: {report['status']}")
        print(f"                 Tweets processed: {report['processed']}")
        print(f"                 Replies planned/sent: {report['replies_sent']}")
        if report.get("results"):
            print("\nGenerated Responses:")
            for item in report["results"]:
                print(f" - Tweet ID: {item['tweet_id']} (@{item['author']}) | Score: {item['virality_score']}")
                print(f"   Claim: {item['claim']}")
                print(f"   Reply: {item['reply']}")
                print(f"   Published: {item['published']}\n")

        if args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY"):
            written_to = SummaryReporter.generate_and_publish(
                run_report=report,
                settings=settings,
                repository=repo,
                target_file=args.summary_file,
            )
            if written_to:
                print(f"[zioX Summary] Markdown report written to: {written_to}")

        show_status(repo, settings)
        return

    if args.run_once or args.interactive or len(sys.argv) == 1:
        mode_label = "Interactive" if args.interactive else "Standard"
        print(f"\n[zioX] Starting scan cycle (Mode: {mode_label}, Provider: {settings.twitter_provider}, Dry Run: {settings.dry_run})...")
        report = orchestrator.run_cycle(interactive=args.interactive)
        print(f"[zioX] Cycle completed with status: {report['status']}")
        print(f"       Tweets scanned: {report['scanned']}")
        print(f"       Replies planned/sent: {report['replies_sent']}")

        if report.get("results"):
            print("\nGenerated Responses:")
            for item in report["results"]:
                print(f" - Tweet ID: {item['tweet_id']} (@{item['author']}) | Score: {item['virality_score']}")
                print(f"   Claim: {item['claim']}")
                print(f"   Reply: {item['reply']}")
                print(f"   Published: {item['published']}\n")

        if args.summary_file or os.environ.get("GITHUB_STEP_SUMMARY"):
            written_to = SummaryReporter.generate_and_publish(
                run_report=report,
                settings=settings,
                repository=repo,
                target_file=args.summary_file,
            )
            if written_to:
                print(f"[zioX Summary] Markdown report written to: {written_to}")

        show_status(repo, settings)


if __name__ == "__main__":
    main()
