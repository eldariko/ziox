"""Security and privacy utilities for logging and credential protection."""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Matches Telegram Bot Token pattern in URLs or text: bot<bot_id>:<token_hash>
TELEGRAM_TOKEN_REGEX = re.compile(r"bot\d+:[A-Za-z0-9_-]+", re.IGNORECASE)


def mask_telegram_token(text: Any) -> str:
    """Mask Telegram bot token in strings, URLs, exceptions, and text objects."""
    if text is None:
        return ""
    return TELEGRAM_TOKEN_REGEX.sub("bot[REDACTED]", str(text))


class SensitiveDataRedactor(logging.Filter):
    """
    Global logging filter that intercepts log records across all loggers
    and redacts Telegram bot tokens (and sensitive URLs) before output.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "bot" in record.msg.lower():
            record.msg = mask_telegram_token(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (mask_telegram_token(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    mask_telegram_token(v) if isinstance(v, str) else v
                    for v in record.args
                )
        return True


def setup_secure_logging(level: int = logging.INFO) -> None:
    """
    Configures root logging with SensitiveDataRedactor and mutes noisy network
    libraries (httpx, httpcore, urllib3) to WARNING level to prevent token leakage.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    redactor = SensitiveDataRedactor()
    root_logger = logging.getLogger()
    root_logger.addFilter(redactor)
    for handler in root_logger.handlers:
        handler.addFilter(redactor)

    # Mute chatty network libraries that log full request URLs containing bot tokens
    for noisy_logger in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
