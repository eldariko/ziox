"""
Telegram Review & Web Intent Dispatcher.
Dispatches grounded reply drafts with native one-tap X Web Intent buttons,
serverless subscriber onboarding via getUpdates, per-subscriber variation sharding,
and admin-only technical alerts.
"""

import html
import logging
import urllib.parse
from typing import List, Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)

VALID_STYLES = {"any", "factual", "sharp", "historical_legal", "rhetorical_question"}


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
    with one-tap X Web Intent approval buttons, manage serverless community
    subscribers (/start, /stop, /style), and dispatch admin-only health alerts.
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
        self.updates_url = (
            f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            if self.bot_token
            else None
        )

    @property
    def is_configured(self) -> bool:
        """Returns True if bot token and at least one chat/channel ID are configured."""
        return bool(self.api_url and self.chat_ids)

    @property
    def has_bot_token(self) -> bool:
        """Returns True if a Telegram bot token is configured (sufficient for subscriber sync)."""
        return bool(self.api_url)

    def _send_direct_message(
        self,
        chat_id: str,
        text_html: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """Send an HTML message to a single Telegram chat_id."""
        if not self.api_url:
            return False

        payload: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        def _post(client: httpx.Client) -> bool:
            try:
                resp = client.post(self.api_url, json=payload)
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[TelegramDispatcher] Failed sending message to {chat_id}: {e}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

    def sync_subscribers(
        self,
        repository: Any,
        default_daily_limit: int = 3,
        http_client: Optional[httpx.Client] = None,
    ) -> Dict[str, int]:
        """
        Serverless Telegram onboarding:
        1. Seeds static operator `self.chat_ids` (from `.env` `TELEGRAM_CHAT_ID`) into `subscribers`
           with `tier='admin'` and `daily_limit=100` so existing setups work seamlessly.
        2. Polls Telegram `getUpdates` using the persisted `telegram_last_update_id` cursor.
        3. Processes `/start`, `/stop`, and `/style <style>` commands, updating `subscribers`
           and immediately sending a confirmation message back to the user.
        """
        summary = {"started": 0, "stopped": 0, "style_updated": 0}

        # 1. Ensure operator chat_ids from .env are seeded as admin subscribers
        for admin_cid in self.chat_ids:
            try:
                existing_admins = set(repository.get_admin_chat_ids())
                if admin_cid not in existing_admins:
                    repository.upsert_subscriber(
                        chat_id=admin_cid,
                        username="operator_admin",
                        tier="admin",
                        daily_limit=100,
                        preferred_style="any",
                        active=True,
                    )
            except Exception as e:
                logger.warning(f"[TelegramDispatcher] Could not seed admin chat_id {admin_cid}: {e}")

        if not self.updates_url:
            return summary

        last_update_str = repository.get_state("telegram_last_update_id")
        params: Dict[str, Any] = {"timeout": 0}
        if last_update_str is not None and str(last_update_str).isdigit():
            params["offset"] = int(last_update_str) + 1

        def _poll_and_process(client: httpx.Client) -> Dict[str, int]:
            try:
                resp = client.get(self.updates_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[TelegramDispatcher] Failed polling getUpdates: {e}")
                return summary

            if not data.get("ok"):
                return summary

            updates = data.get("result") or []
            max_update_id: Optional[int] = None

            for upd in updates:
                upd_id = upd.get("update_id")
                if isinstance(upd_id, int):
                    if max_update_id is None or upd_id > max_update_id:
                        max_update_id = upd_id

                msg = upd.get("message") or upd.get("edited_message")
                if not isinstance(msg, dict):
                    continue

                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", "")).strip()
                if not chat_id:
                    continue

                username = (
                    chat.get("username")
                    or (msg.get("from") or {}).get("username")
                    or chat.get("first_name")
                    or ""
                )
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                lower_text = text.lower()
                if lower_text.startswith("/start"):
                    tier = "admin" if chat_id in self.chat_ids else "free"
                    limit = 100 if tier == "admin" else default_daily_limit
                    repository.upsert_subscriber(
                        chat_id=chat_id,
                        username=str(username),
                        tier=tier,
                        daily_limit=limit,
                        preferred_style="any",
                        active=True,
                    )
                    summary["started"] += 1
                    welcome_html = (
                        "✅ <b>נרשמת בהצלחה ל-zioX!</b>\n"
                        "בסבב הסריקה הבא תקבל לכאן הצעות תגובה ייחודיות מבוססות מקורות מאומתים בלחיצה אחת.\n\n"
                        "🎨 <b>בחירת סגנון אישי:</b> שלח <code>/style sharp</code>, <code>/style factual</code>, "
                        "<code>/style historical_legal</code>, או <code>/style rhetorical_question</code>.\n"
                        "🛑 להפסקה בכל עת שלח <code>/stop</code>."
                    )
                    self._send_direct_message(chat_id=chat_id, text_html=welcome_html, http_client=client)

                elif lower_text.startswith("/stop"):
                    repository.deactivate_subscriber(chat_id)
                    summary["stopped"] += 1
                    stop_html = "🛑 <b>המנוי שלך ב-zioX הושהה.</b> תוכל לחזור בכל עת באמצעות שליחת <code>/start</code>."
                    self._send_direct_message(chat_id=chat_id, text_html=stop_html, http_client=client)

                elif lower_text.startswith("/style"):
                    parts = lower_text.split()
                    requested_style = parts[1].strip() if len(parts) > 1 else ""
                    if requested_style in VALID_STYLES:
                        repository.upsert_subscriber(
                            chat_id=chat_id,
                            username=str(username),
                            tier="admin" if chat_id in self.chat_ids else "free",
                            daily_limit=100 if chat_id in self.chat_ids else default_daily_limit,
                            preferred_style=requested_style,
                            active=True,
                        )
                        repository.update_subscriber_style(chat_id, requested_style)
                        summary["style_updated"] += 1
                        style_html = (
                            f"🎨 <b>סגנון התגובות שלך עודכן ל-<code>{html.escape(requested_style)}</code>!</b>\n"
                            "בסבבים הבאים נתעדף עבורך וריאציות בסגנון זה."
                        )
                    else:
                        valid_list = ", ".join(sorted(VALID_STYLES))
                        style_html = (
                            f"ℹ️ <b>בחירת סגנון תגובה ב-zioX:</b>\n"
                            f"שלח <code>/style &lt;name&gt;</code> עם אחת האפשרויות: <code>{valid_list}</code>"
                        )
                    self._send_direct_message(chat_id=chat_id, text_html=style_html, http_client=client)

            if max_update_id is not None:
                repository.set_state("telegram_last_update_id", str(max_update_id))

            return summary

        if http_client is not None:
            return _poll_and_process(http_client)
        with httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0)) as client:
            return _poll_and_process(client)

    def send_admin_alert(
        self,
        alert_text: str,
        repository: Optional[Any] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """
        Send a technical/health alert (such as X Scanner Circuit Breaker HTTP 429/403 cooldown)
        STRICTLY to operator admin chat IDs (`self.chat_ids` from `.env` + `tier='admin'` in DB).
        Regular subscribers (`free` or `pro`) NEVER receive technical admin alerts.
        """
        if not self.api_url:
            return False

        admin_targets: List[str] = list(self.chat_ids)
        if repository is not None:
            try:
                for db_admin_id in repository.get_admin_chat_ids():
                    if db_admin_id not in admin_targets:
                        admin_targets.append(db_admin_id)
            except Exception as e:
                logger.warning(f"[TelegramDispatcher] Could not query admin chat IDs: {e}")

        if not admin_targets:
            logger.warning("[TelegramDispatcher] No admin chat IDs configured for send_admin_alert.")
            return False

        formatted_alert = (
            "🚨 <b>zioX Admin Scanner Alert</b>\n\n"
            f"⚠️ <b>Details:</b> {html.escape(alert_text)}"
        )

        overall_ok = True
        for admin_chat_id in admin_targets:
            sent = self._send_direct_message(
                chat_id=admin_chat_id,
                text_html=formatted_alert,
                http_client=http_client,
            )
            if not sent:
                overall_ok = False
        return overall_ok

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
        target_chat_ids: Optional[List[str]] = None,
    ) -> bool:
        """
        Dispatches a review card to `target_chat_ids` (or all configured `self.chat_ids`)
        with an Inline Keyboard button for one-tap X Web Intent.
        """
        recipients = target_chat_ids if target_chat_ids is not None else self.chat_ids
        if not self.api_url or not recipients:
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
            for chat_id in recipients:
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

    def dispatch_variations_to_subscribers(
        self,
        repository: Any,
        tweet_id: str,
        author_handle: str,
        tweet_text: str,
        virality_score: float,
        virality_tier: str,
        variations: List[Dict[str, Any]],
        claim_flagged: Optional[str] = None,
        verified_facts: Optional[List[str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> int:
        """
        Distribute unique reply variations for `tweet_id` across eligible active subscribers:
        - Filters out subscribers who already received `tweet_id` or reached their daily_limit.
        - Matches each subscriber's `preferred_style` when available, otherwise assigns the next unused variation.
        - Never assigns the same `variation_hash` to two different subscribers on the same `tweet_id`.
        - Records each successful delivery in the `dispatches` table.
        Returns the number of subscribers who received a unique variation.
        """
        if not self.api_url or not variations:
            return 0

        active_subscribers = repository.get_active_subscribers()
        # Fallback: if no subscribers are in the DB yet but self.chat_ids is set, seed and fetch
        if not active_subscribers and self.chat_ids:
            for cid in self.chat_ids:
                repository.upsert_subscriber(
                    chat_id=cid,
                    username="operator_admin",
                    tier="admin",
                    daily_limit=100,
                    preferred_style="any",
                    active=True,
                )
            active_subscribers = repository.get_active_subscribers()

        if not active_subscribers:
            return 0

        used_hashes = set(repository.get_used_variation_hashes(tweet_id))

        # Prepare available unused variations with their computed hashes
        available_vars: List[Dict[str, Any]] = []
        for var in variations:
            v_text = (var.get("text") or "").strip()
            if not v_text:
                continue
            v_hash = repository.compute_variation_hash(v_text)
            if v_hash not in used_hashes and all(x["hash"] != v_hash for x in available_vars):
                available_vars.append({
                    "style": var.get("style", "factual"),
                    "text": v_text,
                    "link": var.get("link"),
                    "hash": v_hash,
                })

        if not available_vars:
            return 0

        dispatched_count = 0

        for sub in active_subscribers:
            if not available_vars:
                break

            chat_id = str(sub["chat_id"]).strip()
            daily_limit = int(sub.get("daily_limit", 3))
            pref_style = (sub.get("preferred_style") or "any").strip().lower()

            # Check deduplication & daily quota
            if repository.has_received_tweet(tweet_id, chat_id):
                continue
            if repository.get_subscriber_daily_count(chat_id) >= daily_limit:
                continue

            # Pick variation matching preferred_style if available, else first unused variation
            chosen_idx = 0
            if pref_style != "any":
                for idx, candidate in enumerate(available_vars):
                    if candidate["style"] == pref_style:
                        chosen_idx = idx
                        break

            chosen_var = available_vars.pop(chosen_idx)

            sent = self.dispatch_review(
                tweet_id=tweet_id,
                author_handle=author_handle,
                tweet_text=tweet_text,
                virality_score=virality_score,
                virality_tier=virality_tier,
                draft_reply=chosen_var["text"],
                claim_flagged=claim_flagged,
                verified_facts=verified_facts,
                http_client=http_client,
                target_chat_ids=[chat_id],
            )

            if sent:
                repository.record_dispatch(
                    tweet_id=tweet_id,
                    chat_id=chat_id,
                    variation_text_or_hash=chosen_var["hash"],
                    style=chosen_var["style"],
                )
                dispatched_count += 1

        return dispatched_count
