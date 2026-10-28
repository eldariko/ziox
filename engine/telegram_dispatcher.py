"""
Telegram Review & Web Intent Dispatcher.
Dispatches grounded reply drafts with native one-tap X Web Intent buttons.
"""

import html
import logging
import urllib.parse
from typing import List, Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


def build_x_web_intent_url(tweet_id: str, reply_text: str) -> str:
    """
    Constructs an X Web Intent URL.
    Uses urllib.parse.quote(..., safe='') to ensure strict %20 space encoding
    and safe newline preservation across both mobile and web clients.
    """
    encoded_text = urllib.parse.quote(reply_text.strip(), safe="")
    return f"https://x.com/intent/tweet?in_reply_to={tweet_id}&text={encoded_text}"


class TelegramDispatcher:
    """
    Lightweight dispatcher to send fact-checked draft cards to Telegram
    with one-tap X Web Intent approval buttons.
    """

    def __init__(self, bot_token: Optional[str] = None, chat_ids: Optional[str] = None):
        self.bot_token = (bot_token or "").strip()
        self.chat_ids: List[str] = [
            cid.strip() for cid in (chat_ids or "").split(",") if cid.strip()
        ]
        self.api_url = (
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            if self.bot_token
            else None
        )

    @property
    def is_configured(self) -> bool:
        """Returns True if bot token and at least one chat/channel ID are configured."""
        return bool(self.api_url and self.chat_ids)

    def format_review_card(
        self,
        tweet_id: str,
        author_handle: str,
        tweet_text: str,
        virality_score: float,
        virality_tier: str,
        draft_reply: str,
        claim_flagged: Optional[str] = None,
        verified_facts: Optional[List[str]] = None,
    ) -> str:
        """
        Formats the notification card in safe HTML.
        Uses html.escape to protect against special characters breaking HTML parse mode.
        """
        safe_author = html.escape(author_handle.lstrip("@"))
        safe_snippet = html.escape(tweet_text[:220] + ("..." if len(tweet_text) > 220 else ""))
        safe_draft = html.escape(draft_reply)

        card = (
            f"🎯 <b>zioX Review Alert</b> [{virality_tier} | Score: {virality_score:.1f}]\n\n"
            f"👤 <b>Target:</b> @{safe_author}\n"
            f"💬 <b>Tweet:</b> <i>\"{safe_snippet}\"</i>\n"
        )

        if claim_flagged:
            card += f"⚠️ <b>Claim Flagged:</b> {html.escape(claim_flagged)}\n"

        if verified_facts:
            facts_str = " | ".join(html.escape(f) for f in verified_facts)
            card += f"📌 <b>Facts Cited:</b> {facts_str}\n"

        card += f"\n💡 <b>Proposed Reply:</b>\n<code>{safe_draft}</code>"
        return card

    def dispatch_review(
        self,
        tweet_id: str,
        author_handle: str,
        tweet_text: str,
        virality_score: float,
        virality_tier: str,
        draft_reply: str,
        claim_flagged: Optional[str] = None,
        verified_facts: Optional[List[str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """
        Dispatches the review card to all configured chat IDs / channels
        with an Inline Keyboard button for one-tap X Web Intent.
        """
        if not self.is_configured:
            logger.debug("TelegramDispatcher not configured. Skipping dispatch.")
            return False

        message_html = self.format_review_card(
            tweet_id=tweet_id,
            author_handle=author_handle,
            tweet_text=tweet_text,
            virality_score=virality_score,
            virality_tier=virality_tier,
            draft_reply=draft_reply,
            claim_flagged=claim_flagged,
            verified_facts=verified_facts,
        )

        intent_url = build_x_web_intent_url(tweet_id, draft_reply)
        author_clean = author_handle.lstrip("@")
        original_tweet_url = f"https://x.com/{author_clean}/status/{tweet_id}"

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🚀 צייץ תגובה ב-X", "url": intent_url}],
                [{"text": "👀 צפה בציוץ המקורי", "url": original_tweet_url}],
            ]
        }

        def _send(client: httpx.Client) -> bool:
            overall_success = True
            for chat_id in self.chat_ids:
                try:
                    payload = {
                        "chat_id": chat_id,
                        "text": message_html,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True,
                    }
                    resp = client.post(self.api_url, json=payload)
                    resp.raise_for_status()
                    logger.info(f"[TelegramDispatcher] Dispatched review card to chat {chat_id}")
                except Exception as e:
                    logger.error(f"[TelegramDispatcher] Failed to send to chat {chat_id}: {e}")
                    overall_success = False
            return overall_success

        if http_client:
            return _send(http_client)
        else:
            with httpx.Client(timeout=10.0) as client:
                return _send(client)
