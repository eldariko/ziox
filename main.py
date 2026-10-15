"""Command Line Interface for zioX Bot."""

import argparse
import sys
import logging
from config.settings import get_settings
from database.repository import Repository
from providers.mock_provider import MockTwitterProvider
from providers.zernio_provider import ZernioTwitterProvider
from engine.grounding import GroundingEngine
from engine.orchestrator import BotOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("zioX")


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
        choices=["mock", "zernio"],
        help="Override Twitter provider ('mock' or 'zernio')"
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

    # Choose Twitter provider
    if settings.twitter_provider == "zernio":
        if not settings.zernio_api_key:
            logger.error("ZERNIO_API_KEY is not configured in .env. Exiting.")
            sys.exit(1)
        provider = ZernioTwitterProvider(
            api_key=settings.zernio_api_key,
            twitter_account_id=settings.zernio_twitter_account_id
        )
    else:
        provider = MockTwitterProvider()

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
