"""
Quick simulation script to test zioX Telegram review card and Web Intent generation.
"""

import sys
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import httpx
from config.settings import get_settings
from engine.telegram_dispatcher import TelegramDispatcher, build_x_web_intent_url

def main():
    settings = get_settings()
    print("=" * 60)
    print(" zioX Telegram Integration Test")
    print("=" * 60)
    print(f"Bot Token : {settings.telegram_bot_token[:10]}... (configured: {bool(settings.telegram_bot_token)})")
    print(f"Chat ID   : {settings.telegram_chat_id}")
    print(f"Enabled   : {settings.telegram_review_enabled}")
    print("-" * 60)

    dispatcher = TelegramDispatcher(
        bot_token=settings.telegram_bot_token,
        chat_ids=settings.telegram_chat_id
    )

    sample_tweet_id = "1978654321098765432"
    sample_author = "narrative_spreader"
    sample_text = "Breaking: All humanitarian supply lines have been completely halted indefinitely according to reports."
    sample_score = 14.8
    sample_tier = "Viral / Critical"
    sample_draft = "Official COGAT records confirm 420+ aid trucks crossed today via Kerem Shalom and Erez. Operational logistics data is publicly tracked daily."
    sample_claim = "Claim of total aid halt"
    sample_facts = ["COGAT daily manifest logs 420 trucks", "Crossings operational"]

    # 1. Preview formatted HTML card in console
    card_html = dispatcher.format_review_card(
        tweet_id=sample_tweet_id,
        author_handle=sample_author,
        tweet_text=sample_text,
        virality_score=sample_score,
        virality_tier=sample_tier,
        draft_reply=sample_draft,
        claim_flagged=sample_claim,
        verified_facts=sample_facts
    )
    print("\n[Preview of Telegram HTML Card]:\n")
    print(card_html)

    # 2. Preview Web Intent URL
    intent_url = build_x_web_intent_url(sample_tweet_id, sample_draft)
    print("\n[Generated One-Tap X Web Intent URL]:")
    print(intent_url)

    # 3. Attempt live delivery
    print("\n[Sending live message to Telegram...]")
    try:
        success = dispatcher.dispatch_review(
            tweet_id=sample_tweet_id,
            author_handle=sample_author,
            tweet_text=sample_text,
            virality_score=sample_score,
            virality_tier=sample_tier,
            draft_reply=sample_draft,
            claim_flagged=sample_claim,
            verified_facts=sample_facts
        )
        if success:
            print("\n>>> SUCCESS! Check your Telegram chat - the review card with buttons has arrived.")
        else:
            print("\n>>> Delivery failed. Note: If this is a new bot, make sure you opened Telegram, searched for the bot, and clicked 'Start' (/start).")
    except Exception as e:
        print(f"\n>>> Error sending to Telegram: {e}")

if __name__ == "__main__":
    main()
