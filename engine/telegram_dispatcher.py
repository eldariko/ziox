"""
Telegram Review & Web Intent Dispatcher.
Dispatches grounded reply drafts with native one-tap X Web Intent buttons,
serverless subscriber onboarding via paginated getUpdates or Cloudflare Worker Webhook,
readiness & action confirmation, language/quota commands, per-subscriber variation sharding,
and admin-only technical alerts.
"""

import html
import logging
import urllib.parse
from typing import List, Optional, Dict, Any
import httpx
from engine.security import mask_telegram_token

logger = logging.getLogger(__name__)

VALID_STYLES = {"any", "factual", "sharp", "historical_legal", "rhetorical_question"}
VALID_LANGS = {"en", "ar", "both"}


def build_x_web_intent_url(tweet_id: str, reply_text: str) -> str:
    """
    Constructs an X Web Intent URL.
    Uses urllib.parse.quote(..., safe='') to ensure strict %20 space encoding
    and safe newline preservation across both mobile and web clients.
    """
    encoded_text = urllib.parse.quote(reply_text.strip(), safe="")
    return f"https://x.com/intent/tweet?in_reply_to={tweet_id}&text={encoded_text}"


def get_style_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "🎯 Factual (עובדתי)", "callback_data": "set_style:factual"},
                {"text": "⚡ Sharp (עוקצני/חד)", "callback_data": "set_style:sharp"},
            ],
            [
                {"text": "📜 Historical/Legal (משפטי)", "callback_data": "set_style:historical_legal"},
                {"text": "❓ Rhetorical (רטורי)", "callback_data": "set_style:rhetorical_question"},
            ],
            [
                {"text": "🎲 Any (ללא העדפה)", "callback_data": "set_style:any"},
            ],
            [
                {"text": "🔙 תפריט ראשי", "callback_data": "menu:main"},
            ],
        ]
    }


def get_lang_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "🇬🇧 English (אנגלית - ברירת מחדל)", "callback_data": "set_lang:en"},
            ],
            [
                {"text": "🇸🇦 Arabic (ערבית בלבד)", "callback_data": "set_lang:ar"},
            ],
            [
                {"text": "🌐 Both (שתי השפות)", "callback_data": "set_lang:both"},
            ],
            [
                {"text": "🔙 תפריט ראשי", "callback_data": "menu:main"},
            ],
        ]
    }


def get_limit_keyboard(max_user_daily_limit: int = 5) -> Dict[str, Any]:
    row = [
        {"text": f"{i} ביום", "callback_data": f"set_limit:{i}"}
        for i in range(1, max_user_daily_limit + 1)
    ]
    return {
        "inline_keyboard": [
            row,
            [{"text": "🔙 תפריט ראשי", "callback_data": "menu:main"}],
        ]
    }


def get_main_menu_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "✅ אני מוכן להגיב", "callback_data": "ready:confirm"}],
            [
                {"text": "🎨 סגנון תגובה (/style)", "callback_data": "menu:style"},
                {"text": "🌐 שפת פוסטים (/lang)", "callback_data": "menu:lang"},
            ],
            [
                {"text": "📊 מכסה יומית (/limit)", "callback_data": "menu:limit"},
                {"text": "📈 סטטוס ומכסה (/quota)", "callback_data": "menu:quota"},
            ],
            [
                {"text": "🛑 השהיית מנוי (/stop)", "callback_data": "menu:stop"},
            ],
        ]
    }


class TelegramDispatcher:
    """
    Lightweight dispatcher to send fact-checked draft cards to Telegram
    with one-tap X Web Intent approval buttons, manage serverless community
    subscribers (/start, /ready, /stop, /style, /lang, /limit, /quota + callback queries),
    register/remove Cloudflare Worker webhooks, and dispatch admin-only health alerts.
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
        self.callback_url = (
            f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
            if self.bot_token
            else None
        )
        self.set_commands_url = (
            f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
            if self.bot_token
            else None
        )
        self.set_webhook_url = (
            f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
            if self.bot_token
            else None
        )
        self.delete_webhook_url = (
            f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook"
            if self.bot_token
            else None
        )

    def setup_bot_commands(self, http_client: Optional[httpx.Client] = None) -> bool:
        """
        Register bot commands in Telegram's UI via setMyCommands API.
        Populates Telegram's native command autocomplete list and Menu button.
        """
        if not self.set_commands_url:
            return False
        commands = [
            {"command": "start", "description": "הרשמה והפעלת המנוי ב-zioX"},
            {"command": "help", "description": "מדריך פקודות ותפריט מהיר"},
            {"command": "ready", "description": "אישור מוכנות לקבלת פוסטים להגבה"},
            {"command": "style", "description": "בחירת סגנון תגובות מועדף"},
            {"command": "lang", "description": "בחירת שפת פוסטים (ברירת מחדל: en)"},
            {"command": "limit", "description": "עדכון מכסה יומית של פוסטים"},
            {"command": "quota", "description": "בדיקת מצב המכסה וההגדרות שלך"},
            {"command": "stop", "description": "השהיית קבלת פוסטים"},
        ]
        payload = {"commands": commands}

        def _post(client: httpx.Client) -> bool:
            try:
                resp = client.post(self.set_commands_url, json=payload)
                resp.raise_for_status()
                logger.info("[TelegramDispatcher] Successfully registered bot commands in Telegram UI.")
                return True
            except Exception as e:
                logger.debug(f"[TelegramDispatcher] Could not register bot commands: {mask_telegram_token(e)}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

    def set_webhook(
        self,
        webhook_url: str,
        secret_token: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """
        Register an HTTPS Webhook URL (e.g., Cloudflare Worker) with Telegram's Bot API (`setWebhook`)
        and register the bot's command menu (`setMyCommands`).
        """
        if not self.set_webhook_url or not webhook_url:
            return False
        payload: Dict[str, Any] = {
            "url": webhook_url.strip(),
            "allowed_updates": ["message", "edited_message", "callback_query"],
        }
        if secret_token:
            payload["secret_token"] = secret_token.strip()

        def _post(client: httpx.Client) -> bool:
            try:
                self.setup_bot_commands(http_client=client)
                resp = client.post(self.set_webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                ok = bool(data.get("ok"))
                if ok:
                    logger.info(f"[TelegramDispatcher] Successfully registered Telegram Webhook: {webhook_url}")
                return ok
            except Exception as e:
                logger.error(f"[TelegramDispatcher] Failed setting Telegram Webhook: {mask_telegram_token(e)}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

    def delete_webhook(
        self,
        drop_pending_updates: bool = False,
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """
        Remove the active Telegram Webhook (`deleteWebhook`) so `getUpdates` polling can be used again.
        """
        if not self.delete_webhook_url:
            return False
        payload = {"drop_pending_updates": bool(drop_pending_updates)}

        def _post(client: httpx.Client) -> bool:
            try:
                resp = client.post(self.delete_webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                ok = bool(data.get("ok"))
                if ok:
                    logger.info("[TelegramDispatcher] Successfully deleted Telegram Webhook (getUpdates re-enabled).")
                return ok
            except Exception as e:
                logger.error(f"[TelegramDispatcher] Failed deleting Telegram Webhook: {mask_telegram_token(e)}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

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
        repository: Optional[Any] = None,
    ) -> bool:
        """
        Send an HTML message to a single Telegram chat_id.
        If Telegram returns HTTP 403 Forbidden (bot blocked by user) and `repository` is provided,
        immediately marks the subscriber as `active = 0`.
        """
        if not self.api_url:
            return False

        clean_chat_id = str(chat_id).strip()
        payload: Dict[str, Any] = {
            "chat_id": clean_chat_id,
            "text": text_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        def _post(client: httpx.Client) -> bool:
            try:
                resp = client.post(self.api_url, json=payload)
                if resp.status_code == 403 and repository is not None and hasattr(repository, "deactivate_subscriber"):
                    logger.warning(
                        f"[TelegramDispatcher] Chat {clean_chat_id} returned 403 Forbidden (bot blocked). Deactivating subscriber."
                    )
                    repository.deactivate_subscriber(clean_chat_id)
                    return False
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[TelegramDispatcher] Failed sending message to {clean_chat_id}: {mask_telegram_token(e)}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

    def _answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        http_client: Optional[httpx.Client] = None,
    ) -> bool:
        """Acknowledge an inline keyboard button press via Telegram's `answerCallbackQuery`."""
        if not self.callback_url or not callback_query_id:
            return False
        payload: Dict[str, Any] = {"callback_query_id": str(callback_query_id)}
        if text:
            payload["text"] = text

        def _post(client: httpx.Client) -> bool:
            try:
                resp = client.post(self.callback_url, json=payload)
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.debug(f"[TelegramDispatcher] answerCallbackQuery skipped/failed: {mask_telegram_token(e)}")
                return False

        if http_client is not None:
            return _post(http_client)
        with httpx.Client(timeout=10.0) as client:
            return _post(client)

    def sync_subscribers(
        self,
        repository: Any,
        default_daily_limit: int = 3,
        max_user_daily_limit: int = 5,
        require_readiness_confirm: bool = False,
        http_client: Optional[httpx.Client] = None,
    ) -> Dict[str, int]:
        """
        Serverless Telegram onboarding & engagement synchronization:
        1. Seeds static operator `self.chat_ids` (from `.env` `TELEGRAM_CHAT_ID`) into `subscribers`
           with `tier='admin'`, `ready_confirmed=True`, and `daily_limit=100`.
        2. Polls Telegram `getUpdates` in a paginated loop using `telegram_last_update_id` until
           all pending updates (100+ across large communities) are processed.
           If a Cloudflare Worker Webhook is active (HTTP 409 Conflict), logs an info message and
           returns cleanly without error.
        3. Processes commands (`/start`, `/ready`, `/stop`, `/style`, `/lang`, `/limit`, `/quota`)
           and inline button `callback_query` events (`ready:confirm` and `ack:<tweet_id>`).
        """
        summary = {
            "started": 0,
            "stopped": 0,
            "style_updated": 0,
            "lang_updated": 0,
            "limit_updated": 0,
            "ready_confirmed": 0,
            "replies_confirmed": 0,
        }

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
                        preferred_lang="en",
                        ready_confirmed=True,
                        active=True,
                    )
            except Exception as e:
                logger.warning(f"[TelegramDispatcher] Could not seed admin chat_id {admin_cid}: {e}")

        if not self.updates_url:
            return summary

        last_update_str = repository.get_state("telegram_last_update_id")
        current_offset: Optional[int] = None
        if last_update_str is not None and str(last_update_str).isdigit():
            current_offset = int(last_update_str) + 1

        def _poll_and_process(client: httpx.Client) -> Dict[str, int]:
            nonlocal current_offset
            max_pages = 20  # Up to 2,000 updates per cycle safety cap
            pages_fetched = 0

            while pages_fetched < max_pages:
                pages_fetched += 1
                params: Dict[str, Any] = {"timeout": 0, "limit": 100}
                if current_offset is not None:
                    params["offset"] = current_offset

                try:
                    resp = client.get(self.updates_url, params=params)
                    if resp.status_code == 409:
                        logger.info(
                            "[TelegramDispatcher] Telegram Webhook is active (HTTP 409 on getUpdates). "
                            "Live updates are handled directly by the Cloudflare Worker Webhook."
                        )
                        break
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"[TelegramDispatcher] Failed polling getUpdates: {mask_telegram_token(e)}")
                    break

                if not data.get("ok"):
                    break

                updates = data.get("result") or []
                if not updates:
                    break

                max_update_id: Optional[int] = None

                for upd in updates:
                    upd_id = upd.get("update_id")
                    if isinstance(upd_id, int):
                        if max_update_id is None or upd_id > max_update_id:
                            max_update_id = upd_id

                    # A. Handle Inline Button Callback Queries (ready:confirm / ack:<tweet_id>)
                    cb = upd.get("callback_query")
                    if isinstance(cb, dict):
                        cb_id = str(cb.get("id", "")).strip()
                        cb_data = str(cb.get("data", "")).strip()
                        cb_msg = cb.get("message") or {}
                        cb_chat = cb_msg.get("chat") or (cb.get("from") or {})
                        cb_chat_id = str(cb_chat.get("id", "")).strip()
                        cb_username = (
                            (cb.get("from") or {}).get("username")
                            or cb_chat.get("username")
                            or cb_chat.get("first_name")
                            or ""
                        )
                        if cb_chat_id:
                            if hasattr(repository, "get_subscriber") and repository.get_subscriber(cb_chat_id) is None:
                                repository.upsert_subscriber(
                                    chat_id=cb_chat_id,
                                    username=str(cb_username),
                                    tier="admin" if cb_chat_id in self.chat_ids else "free",
                                    daily_limit=100 if cb_chat_id in self.chat_ids else default_daily_limit,
                                    preferred_style="any",
                                    preferred_lang="en",
                                    ready_confirmed=True if cb_chat_id in self.chat_ids else (not require_readiness_confirm),
                                    active=True,
                                )
                            if cb_data == "ready:confirm":
                                if hasattr(repository, "confirm_subscriber_ready"):
                                    repository.confirm_subscriber_ready(cb_chat_id)
                                summary["ready_confirmed"] += 1
                                self._answer_callback_query(
                                    cb_id,
                                    text="✅ מוכנותך אושרה! תקבל פוסטים בסבב הקרוב.",
                                    http_client=client,
                                )
                                ready_html = (
                                    "🚀 <b>מעולה! החשבון שלך פעיל ומוכן לקבלת פוסטים.</b>\n"
                                    "בכל פעם שתקבל פוסט ותגיב עליו ב-X, לחץ על הכפתור <b>✅ הגבתי ב-X</b> בכרטיס כדי להמשיך לקבל פוסטים."
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=ready_html,
                                    http_client=client,
                                    repository=repository,
                                    reply_markup=get_main_menu_keyboard(),
                                )
                            elif cb_data.startswith("set_style:"):
                                req_style = cb_data.split(":", 1)[1].strip().lower()
                                if req_style in VALID_STYLES:
                                    repository.update_subscriber_style(cb_chat_id, req_style)
                                    summary["style_updated"] += 1
                                    self._answer_callback_query(
                                        cb_id,
                                        text=f"✅ סגנון עודכן ל-{req_style}",
                                        http_client=client,
                                    )
                                    style_html = (
                                        f"🎨 <b>סגנון התגובות שלך עודכן ל-<code>{html.escape(req_style)}</code>!</b>\n"
                                        "בסבבים הבאים נתעדף עבורך וריאציות בסגנון זה.\n"
                                        "תוכל לשנות סגנון בכל עת:"
                                    )
                                    self._send_direct_message(
                                        chat_id=cb_chat_id,
                                        text_html=style_html,
                                        reply_markup=get_style_keyboard(),
                                        http_client=client,
                                        repository=repository,
                                    )
                            elif cb_data.startswith("set_lang:"):
                                req_lang = cb_data.split(":", 1)[1].strip().lower()
                                if req_lang in VALID_LANGS:
                                    if hasattr(repository, "update_subscriber_language"):
                                        repository.update_subscriber_language(cb_chat_id, req_lang)
                                    summary["lang_updated"] += 1
                                    self._answer_callback_query(
                                        cb_id,
                                        text=f"✅ שפה עודכנה ל-{req_lang}",
                                        http_client=client,
                                    )
                                    lang_desc = "אנגלית בלבד" if req_lang == "en" else ("ערבית בלבד" if req_lang == "ar" else "שתי השפות")
                                    lang_html = (
                                        f"🌐 <b>שפת הפוסטים שלך עודכנה ל-<code>{html.escape(req_lang)}</code> ({lang_desc})!</b>\n"
                                        "תוכל לשנות שפה בכל עת:"
                                    )
                                    self._send_direct_message(
                                        chat_id=cb_chat_id,
                                        text_html=lang_html,
                                        reply_markup=get_lang_keyboard(),
                                        http_client=client,
                                        repository=repository,
                                    )
                            elif cb_data.startswith("set_limit:"):
                                limit_str = cb_data.split(":", 1)[1].strip()
                                if limit_str.isdigit():
                                    req_val = int(limit_str)
                                    eff_limit = (
                                        repository.update_subscriber_daily_limit(
                                            cb_chat_id,
                                            requested_limit=req_val,
                                            max_ceiling=max_user_daily_limit,
                                        )
                                        if hasattr(repository, "update_subscriber_daily_limit")
                                        else min(req_val, max_user_daily_limit)
                                    )
                                    summary["limit_updated"] += 1
                                    self._answer_callback_query(
                                        cb_id,
                                        text=f"✅ מכסה עודכנה ל-{eff_limit}",
                                        http_client=client,
                                    )
                                    limit_html = (
                                        f"📊 <b>המכסה היומית שלך עודכנה ל-<code>{eff_limit}</code> פוסטים ביום!</b>\n"
                                        "תוכל לעדכן בכל עת:"
                                    )
                                    self._send_direct_message(
                                        chat_id=cb_chat_id,
                                        text_html=limit_html,
                                        reply_markup=get_limit_keyboard(max_user_daily_limit),
                                        http_client=client,
                                        repository=repository,
                                    )
                            elif cb_data == "menu:style":
                                self._answer_callback_query(cb_id, http_client=client)
                                style_html = (
                                    "🎨 <b>בחירת סגנון תגובה ב-zioX:</b>\n"
                                    "בחר את סגנון התגובות המועדף עליך באמצעות הכפתורים למטה:"
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=style_html,
                                    reply_markup=get_style_keyboard(),
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data == "menu:lang":
                                self._answer_callback_query(cb_id, http_client=client)
                                lang_html = (
                                    "🌐 <b>בחירת שפת פוסטים ב-zioX:</b>\n"
                                    "ברירת המחדל היא <b>אנגלית בלבד</b> (<code>en</code>).\n"
                                    "בחר שפה באמצעות הכפתורים למטה:"
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=lang_html,
                                    reply_markup=get_lang_keyboard(),
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data == "menu:limit":
                                self._answer_callback_query(cb_id, http_client=client)
                                limit_html = (
                                    f"📊 <b>עדכון מכסה יומית:</b>\n"
                                    f"בחר את כמות הפוסטים היומית המועדפת עליך (עד {max_user_daily_limit} ביום):"
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=limit_html,
                                    reply_markup=get_limit_keyboard(max_user_daily_limit),
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data == "menu:quota":
                                self._answer_callback_query(cb_id, http_client=client)
                                sub_info = repository.get_subscriber(cb_chat_id) if hasattr(repository, "get_subscriber") else None
                                today_used = repository.get_subscriber_daily_count(cb_chat_id) if hasattr(repository, "get_subscriber_daily_count") else 0
                                d_limit = int(sub_info.get("daily_limit", default_daily_limit)) if sub_info else default_daily_limit
                                p_style = (sub_info.get("preferred_style") if sub_info else "any") or "any"
                                p_lang = (sub_info.get("preferred_lang") if sub_info else "en") or "en"
                                total_conf = int(sub_info.get("total_confirmed_replies", 0)) if sub_info else 0
                                quota_html = (
                                    "📊 <b>סטטוס המנוי שלך ב-zioX:</b>\n"
                                    f"• <b>פוסטים היום:</b> <code>{today_used} / {d_limit}</code>\n"
                                    f"• <b>תגובות שאושרו ב-X:</b> <code>{total_conf}</code>\n"
                                    f"• <b>סגנון מועדף:</b> <code>{html.escape(p_style)}</code>\n"
                                    f"• <b>שפה מועדפת:</b> <code>{html.escape(p_lang)}</code>"
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=quota_html,
                                    reply_markup=get_main_menu_keyboard(),
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data == "menu:stop":
                                repository.deactivate_subscriber(cb_chat_id)
                                summary["stopped"] += 1
                                self._answer_callback_query(cb_id, text="🛑 המנוי הושהה", http_client=client)
                                stop_html = "🛑 <b>המנוי שלך ב-zioX הושהה.</b> תוכל לחזור בכל עת באמצעות שליחת <code>/start</code> או <code>/ready</code>."
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=stop_html,
                                    reply_markup={"inline_keyboard": [[{"text": "🚀 הפעל מחדש", "callback_data": "ready:confirm"}]]},
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data == "menu:main":
                                self._answer_callback_query(cb_id, http_client=client)
                                main_html = (
                                    "⚙️ <b>תפריט ראשי zioX:</b>\n"
                                    "בחר באחת האפשרויות למטה לניהול המנוי וההעדפות שלך:"
                                )
                                self._send_direct_message(
                                    chat_id=cb_chat_id,
                                    text_html=main_html,
                                    reply_markup=get_main_menu_keyboard(),
                                    http_client=client,
                                    repository=repository,
                                )
                            elif cb_data.startswith("ack:"):
                                ack_tweet_id = cb_data.split(":", 1)[1].strip()
                                if ack_tweet_id and hasattr(repository, "confirm_dispatch_replied"):
                                    repository.confirm_dispatch_replied(ack_tweet_id, cb_chat_id)
                                summary["replies_confirmed"] += 1
                                self._answer_callback_query(
                                    cb_id,
                                    text="👏 תודה! התגובה שלך נרשמה.",
                                    http_client=client,
                                )
                        continue

                    # B. Handle Standard Text Commands
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
                        is_ready = True if tier == "admin" else (not require_readiness_confirm)
                        repository.upsert_subscriber(
                            chat_id=chat_id,
                            username=str(username),
                            tier=tier,
                            daily_limit=limit,
                            preferred_style="any",
                            preferred_lang="en",
                            ready_confirmed=is_ready,
                            active=True,
                        )
                        summary["started"] += 1
                        welcome_html = (
                            "✅ <b>נרשמת בהצלחה ל-zioX!</b>\n"
                            "בסבב הסריקה הבא תקבל לכאן הצעות תגובה ייחודיות מבוססות מקורות מאומתים בלחיצה אחת.\n\n"
                            "🌐 <b>שפת ברירת מחדל:</b> אנגלית בלבד (<code>en</code>).\n\n"
                            "🎨 <b>בחירת סגנון אישי:</b> <code>/style</code> (או לחץ על הכפתור למטה)\n"
                            "🌐 <b>בחירת שפה:</b> <code>/lang</code> (או לחץ על הכפתור למטה)\n"
                            "📊 <b>מכסה יומית:</b> <code>/limit</code> (או <code>/quota</code> לבדיקת מצב)\n"
                            "✋ <b>וידוא מוכנות:</b> לחץ על הכפתור <b>✅ אני מוכן להגיב</b> (או שלח <code>/ready</code>)\n"
                            "🛑 להפסקה בכל עת שלח <code>/stop</code>."
                        )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=welcome_html,
                            reply_markup=get_main_menu_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/help"):
                        help_html = (
                            "📖 <b>מדריך פקודות ותפריט zioX:</b>\n\n"
                            "• <code>/start</code> - הרשמה והפעלת המנוי\n"
                            "• <code>/ready</code> - אישור מוכנות לקבלת פוסטים להגבה\n"
                            "• <code>/style</code> - בחירת סגנון תגובות מועדף\n"
                            "• <code>/lang</code> - בחירת שפת פוסטים (ברירת מחדל: אנגלית <code>en</code>)\n"
                            "• <code>/limit</code> - עדכון מכסה יומית (1 עד 5 פוסטים)\n"
                            "• <code>/quota</code> - בדיקת מצב המכסה וההגדרות שלך\n"
                            "• <code>/stop</code> - השהיית קבלת פוסטים\n\n"
                            "👇 <b>ניתן ללחוץ על הכפתורים למטה לניהול מהיר:</b>"
                        )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=help_html,
                            reply_markup=get_main_menu_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/ready"):
                        if hasattr(repository, "confirm_subscriber_ready"):
                            repository.confirm_subscriber_ready(chat_id)
                        summary["ready_confirmed"] += 1
                        ready_html = (
                            "🚀 <b>מוכנותך אושרה!</b> החשבון שלך פעיל ויקבל פוסטים בסבב הקרוב.\n"
                            "זכור ללחוץ על <b>✅ הגבתי ב-X</b> לאחר פרסום תגובה."
                        )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=ready_html,
                            reply_markup=get_main_menu_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/stop"):
                        repository.deactivate_subscriber(chat_id)
                        summary["stopped"] += 1
                        stop_html = "🛑 <b>המנוי שלך ב-zioX הושהה.</b> תוכל לחזור בכל עת באמצעות שליחת <code>/start</code> או <code>/ready</code>."
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=stop_html,
                            reply_markup={"inline_keyboard": [[{"text": "🚀 הפעל מחדש", "callback_data": "ready:confirm"}]]},
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/style"):
                        parts = lower_text.split()
                        requested_style = parts[1].strip() if len(parts) > 1 else ""
                        if requested_style in VALID_STYLES:
                            if hasattr(repository, "get_subscriber") and repository.get_subscriber(chat_id) is None:
                                repository.upsert_subscriber(
                                    chat_id=chat_id,
                                    username=str(username),
                                    tier="admin" if chat_id in self.chat_ids else "free",
                                    daily_limit=100 if chat_id in self.chat_ids else default_daily_limit,
                                    preferred_style=requested_style,
                                    preferred_lang="en",
                                    active=True,
                                )
                            repository.update_subscriber_style(chat_id, requested_style)
                            summary["style_updated"] += 1
                            style_html = (
                                f"🎨 <b>סגנון התגובות שלך עודכן ל-<code>{html.escape(requested_style)}</code>!</b>\n"
                                "בסבבים הבאים נתעדף עבורך וריאציות בסגנון זה.\n"
                                "תוכל להחליף סגנון בכל עת בכפתורים למטה:"
                            )
                        else:
                            style_html = (
                                "🎨 <b>בחירת סגנון תגובה ב-zioX:</b>\n"
                                "בחר את הסגנון המועדף עליך באמצעות הכפתורים למטה, או שלח <code>/style &lt;name&gt;</code>:"
                            )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=style_html,
                            reply_markup=get_style_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/lang"):
                        parts = lower_text.split()
                        requested_lang = parts[1].strip() if len(parts) > 1 else ""
                        if requested_lang in VALID_LANGS:
                            if hasattr(repository, "get_subscriber") and repository.get_subscriber(chat_id) is None:
                                repository.upsert_subscriber(
                                    chat_id=chat_id,
                                    username=str(username),
                                    preferred_lang=requested_lang,
                                    active=True,
                                )
                            if hasattr(repository, "update_subscriber_language"):
                                repository.update_subscriber_language(chat_id, requested_lang)
                            summary["lang_updated"] += 1
                            lang_desc = "אנגלית בלבד" if requested_lang == "en" else ("ערבית בלבד" if requested_lang == "ar" else "שתי השפות")
                            lang_html = (
                                f"🌐 <b>שפת הפוסטים שלך עודכנה ל-<code>{html.escape(requested_lang)}</code> ({lang_desc})!</b>\n"
                                "תוכל להחליף שפה בכל עת בכפתורים למטה:"
                            )
                        else:
                            lang_html = (
                                "🌐 <b>בחירת שפת פוסטים ב-zioX:</b>\n"
                                "ברירת המחדל היא <b>אנגלית בלבד</b> (<code>en</code>).\n"
                                "בחר שפה באמצעות הכפתורים למטה, או שלח <code>/lang &lt;en|ar|both&gt;</code>:"
                            )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=lang_html,
                            reply_markup=get_lang_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/limit"):
                        parts = lower_text.split()
                        arg_num = parts[1].strip() if len(parts) > 1 else ""
                        if arg_num.isdigit() and int(arg_num) >= 1:
                            req_val = int(arg_num)
                            if hasattr(repository, "get_subscriber") and repository.get_subscriber(chat_id) is None:
                                repository.upsert_subscriber(
                                    chat_id=chat_id,
                                    username=str(username),
                                    daily_limit=min(req_val, max_user_daily_limit),
                                    preferred_lang="en",
                                    active=True,
                                )
                            effective_limit = (
                                repository.update_subscriber_daily_limit(
                                    chat_id,
                                    requested_limit=req_val,
                                    max_ceiling=max_user_daily_limit,
                                )
                                if hasattr(repository, "update_subscriber_daily_limit")
                                else min(req_val, max_user_daily_limit)
                            )
                            summary["limit_updated"] += 1
                            if effective_limit < req_val:
                                limit_html = (
                                    f"📊 <b>המכסה היומית שלך עודכנה ל-<code>{effective_limit}</code> פוסטים ביום</b> "
                                    f"(התקרה המרכזית המותרת למנוי שלך היא {effective_limit}).\n"
                                    "תוכל לעדכן בכל עת בכפתורים למטה:"
                                )
                            else:
                                limit_html = (
                                    f"📊 <b>המכסה היומית שלך עודכנה ל-<code>{effective_limit}</code> פוסטים ביום!</b>\n"
                                    "תוכל לעדכן בכל עת בכפתורים למטה:"
                                )
                        else:
                            limit_html = (
                                f"ℹ️ <b>עדכון מכסה יומית:</b> שלח <code>/limit &lt;1-{max_user_daily_limit}&gt;</code> "
                                f"(לדוגמה: <code>/limit 4</code>).\n"
                                "או בחר ישירות באחד הכפתורים למטה:"
                            )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=limit_html,
                            reply_markup=get_limit_keyboard(max_user_daily_limit),
                            http_client=client,
                            repository=repository,
                        )

                    elif lower_text.startswith("/quota"):
                        sub_info = repository.get_subscriber(chat_id) if hasattr(repository, "get_subscriber") else None
                        today_used = repository.get_subscriber_daily_count(chat_id) if hasattr(repository, "get_subscriber_daily_count") else 0
                        d_limit = int(sub_info.get("daily_limit", default_daily_limit)) if sub_info else default_daily_limit
                        p_style = (sub_info.get("preferred_style") if sub_info else "any") or "any"
                        p_lang = (sub_info.get("preferred_lang") if sub_info else "en") or "en"
                        total_conf = int(sub_info.get("total_confirmed_replies", 0)) if sub_info else 0
                        quota_html = (
                            "📊 <b>סטטוס המנוי שלך ב-zioX:</b>\n"
                            f"• <b>פוסטים היום:</b> <code>{today_used} / {d_limit}</code>\n"
                            f"• <b>תגובות שאושרו ב-X:</b> <code>{total_conf}</code>\n"
                            f"• <b>סגנון מועדף:</b> <code>{html.escape(p_style)}</code>\n"
                            f"• <b>שפה מועדפת:</b> <code>{html.escape(p_lang)}</code>"
                        )
                        self._send_direct_message(
                            chat_id=chat_id,
                            text_html=quota_html,
                            reply_markup=get_main_menu_keyboard(),
                            http_client=client,
                            repository=repository,
                        )

                if max_update_id is not None:
                    repository.set_state("telegram_last_update_id", str(max_update_id))
                    current_offset = max_update_id + 1

                # If Telegram returned fewer than 100 items, no more pages are waiting
                if len(updates) < 100:
                    break

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
                logger.warning(f"[TelegramDispatcher] Could not query admin chat IDs: {mask_telegram_token(e)}")

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
        include_ack_button: bool = False,
        repository: Optional[Any] = None,
    ) -> bool:
        """
        Dispatches a review card to `target_chat_ids` (or all configured `self.chat_ids`)
        with an Inline Keyboard button for one-tap X Web Intent, and optionally an action
        confirmation button (`✅ הגבתי ב-X` / `ack:<tweet_id>`).
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

        keyboard_rows = [
            [{"text": "🚀 צייץ תגובה ב-X", "url": intent_url}],
            [{"text": "👀 צפה בציוץ המקורי", "url": original_tweet_url}],
        ]
        if include_ack_button:
            keyboard_rows.insert(
                1,
                [{"text": "✅ הגבתי ב-X", "callback_data": f"ack:{tweet_id}"}],
            )

        reply_markup = {"inline_keyboard": keyboard_rows}

        def _send(client: httpx.Client) -> bool:
            overall_success = True
            for chat_id in recipients:
                clean_cid = str(chat_id).strip()
                try:
                    payload = {
                        "chat_id": clean_cid,
                        "text": message_html,
                        "parse_mode": "HTML",
                        "reply_markup": reply_markup,
                        "disable_web_page_preview": True,
                    }
                    resp = client.post(self.api_url, json=payload)
                    if resp.status_code == 403 and repository is not None and hasattr(repository, "deactivate_subscriber"):
                        logger.warning(
                            f"[TelegramDispatcher] Chat {clean_cid} returned 403 Forbidden (bot blocked). Deactivating subscriber."
                        )
                        repository.deactivate_subscriber(clean_cid)
                        overall_success = False
                        continue
                    resp.raise_for_status()
                    logger.info(f"[TelegramDispatcher] Dispatched review card to chat {clean_cid}")
                except Exception as e:
                    logger.error(f"[TelegramDispatcher] Failed to send to chat {clean_cid}: {mask_telegram_token(e)}")
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
        cohort_limit: int = 25,
        max_unconfirmed: int = 5,
    ) -> int:
        """
        Distribute unique reply variations for `tweet_id` across a horizontal cohort of eligible subscribers:
        - Auto-pauses any non-admin subscribers who have reached `max_unconfirmed` consecutive unconfirmed
          dispatches and sends them a wake-up prompt (`🔔 חזרתי - שלח לי פוסטים`).
        - Selects eligible subscribers in a single consolidated SQL query (`get_eligible_subscribers_for_tweet`)
          matching the tweet's language (`en` or `ar`), readiness state, daily limit, and deduplication.
        - Matches each subscriber's `preferred_style` when available, otherwise assigns the next unused variation.
        - Includes the `✅ הגבתי ב-X` (`ack:<tweet_id>`) inline confirmation button on every dispatched card.
        - Never assigns the same `variation_hash` to two different subscribers on the same `tweet_id`.
        - Records each successful delivery in the `dispatches` table.
        Returns the number of subscribers who received a unique variation.
        """
        if not self.api_url or not variations:
            return 0

        # 1. Auto-pause subscribers who exceeded consecutive_unconfirmed streak before selecting cohort
        if hasattr(repository, "pause_unresponsive_subscribers"):
            paused_chat_ids = repository.pause_unresponsive_subscribers(max_unconfirmed=max_unconfirmed)
            if paused_chat_ids:
                wakeup_html = (
                    "⏸️ <b>שמנו לב שלא אישרת תגובה ב-5 הפוסטים האחרונים שנשלחו אליך.</b>\n"
                    "כדי לשמור על איכות התגובות של הקהילה, השהינו זמנית את שליחת הפוסטים אליך.\n\n"
                    "👇 <b>מוכן לחזור להגיב?</b> לחץ על הכפתור למטה (או שלח <code>/ready</code>) ונחדש מיד את השליחה!"
                )
                wakeup_markup = {
                    "inline_keyboard": [
                        [{"text": "🔔 חזרתי - שלח לי פוסטים", "callback_data": "ready:confirm"}]
                    ]
                }
                for p_cid in paused_chat_ids:
                    self._send_direct_message(
                        chat_id=p_cid,
                        text_html=wakeup_html,
                        reply_markup=wakeup_markup,
                        http_client=http_client,
                        repository=repository,
                    )

        # Detect tweet language ('ar' if Arabic characters present, else 'en')
        is_arabic = any("\u0600" <= c <= "\u06ff" for c in (tweet_text or ""))
        tweet_lang = "ar" if is_arabic else "en"

        # 2. Fetch eligible cohort in a single SQL query (zero N+1 queries!)
        if hasattr(repository, "get_eligible_subscribers_for_tweet"):
            eligible_subscribers = repository.get_eligible_subscribers_for_tweet(
                tweet_id=tweet_id,
                lang=tweet_lang,
                limit=cohort_limit,
                max_unconfirmed=max_unconfirmed,
            )
            # Fallback: if no subscribers exist in the DB at all yet, seed static operator chat_ids
            if not eligible_subscribers and self.chat_ids and not repository.get_active_subscribers():
                for cid in self.chat_ids:
                    repository.upsert_subscriber(
                        chat_id=cid,
                        username="operator_admin",
                        tier="admin",
                        daily_limit=100,
                        preferred_style="any",
                        preferred_lang="en",
                        ready_confirmed=True,
                        active=True,
                    )
                eligible_subscribers = repository.get_eligible_subscribers_for_tweet(
                    tweet_id=tweet_id,
                    lang=tweet_lang,
                    limit=cohort_limit,
                    max_unconfirmed=max_unconfirmed,
                )
        else:
            eligible_subscribers = repository.get_active_subscribers()[:cohort_limit]

        if not eligible_subscribers:
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

        for sub in eligible_subscribers:
            if not available_vars:
                break

            chat_id = str(sub["chat_id"]).strip()
            pref_style = (sub.get("preferred_style") or "any").strip().lower()

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
                include_ack_button=True,
                repository=repository,
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
