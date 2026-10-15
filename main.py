"""Command Line Interface for zioX Bot."""

import argparse
import sys
import logging

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
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

    print("\n" + "=" * 55)
    print("                zioX STATUS REPORT")
    print("=" * 55)
    print(f"Database Path        : {settings.database_path}")
    print(f"Twitter Provider     : {settings.twitter_provider}")
    print(f"Dry Run Mode         : {settings.dry_run}")
    print(f"Monthly Reply Usage  : {monthly_count} / {settings.monthly_max_replies}")
    print(f"Virality Threshold   : {settings.virality_threshold}")
    print(f"Max Thread Turns     : {settings.max_thread_turns}")
    print("-" * 55)
    print("Recent Execution Logs:")
    if not logs:
        print("  (No runs recorded yet)")
    else:
        for log in logs:
            err = f" | Error: {log['error_message']}" if log['error_message'] else ""
            print(f"  [{log['run_timestamp']}] Status: {log['status']} | Scanned: {log['tweets_scanned']} | Replies: {log['replies_sent']}{err}")
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
        "--run-once",
        action="store_true",
        help="Execute a single monitoring, verification, and engagement cycle"
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
        "-i", "--interactive",
        action="store_true",
        help="Enable Human-in-the-Loop review mode before any reply is sent"
    )

    args = parser.parse_args()
    settings = get_settings()

    if args.live:
        settings.dry_run = False

    if args.provider:
        settings.twitter_provider = args.provider

    repo = Repository(settings.database_path)

    if args.status:
        show_status(repo, settings)
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
        print(f"\n[zioX Radar] Scanning {len(settings.search_keywords)} target keywords (Provider: {settings.twitter_provider})...")
        discovered = radar.scan_keywords(
            provider=provider,
            keywords=settings.search_keywords,
            limit_per_keyword=5,
            min_virality_score=settings.virality_threshold
        )
        print(f"[zioX Radar] Scan complete. Enqueued {len(discovered)} candidate tweets into database.")
        for item in discovered:
            print(f"  * [{item['tier']}] Tweet {item['tweet_id']} by @{item['author']} (Score: {item['virality_score']}) [Keyword: {item['keyword']}]")
        show_queue(repo)
        return

    # Grounding engine
    grounding = GroundingEngine(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model
    )

    orchestrator = BotOrchestrator(
        settings=settings,
        repository=repo,
        provider=provider,
        grounding_engine=grounding
    )

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
        show_status(repo, settings)


if __name__ == "__main__":
    main()
