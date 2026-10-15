"""Anti-Bot Humanizer and Text Sanitation Engine."""

import re
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

WHITELIST_PATH = Path(__file__).resolve().parent.parent / "assets" / "proofs" / "whitelisted_sources.json"

ROBOTIC_PHRASES = [
    r"\bit'?s crucial to understand that\b\s*",
    r"\bit is crucial to understand that\b\s*",
    r"\bdelving into\b\s*",
    r"\bfurthermore,?\s*",
    r"\bmoreover,?\s*",
    r"\bin conclusion,?\s*",
    r"\bit is worth noting that\b\s*",
    r"\bas an ai\b\s*",
    r"\blet'?s unpack this\b\s*",
    r"\bit'?s important to remember\b\s*",
    r"من الجدير بالذكر\s*",
    r"تجدر الإشارة إلى أن\s*",
    r"من المهم أن نفهم\s*",
    r"في الختام،?\s*"
]


class Humanizer:
    """Applies strict anti-bot styling rules to generated responses."""

    TWITTER_MAX_LENGTH: int = 280
    TWITTER_URL_WEIGHT: int = 23

    @classmethod
    def calculate_tweet_length(cls, text: str) -> int:
        """
        Calculate Twitter weighted character count.
        - HTTP/HTTPS URLs count as 23 characters (standard t.co length).
        - Wide characters (Emoji, CJK) count as 2.
        - Standard characters (Latin, Arabic, Hebrew, digits, punctuation, whitespace) count as 1.
        """
        if not text:
            return 0
        url_pattern = re.compile(r"https?://\S+")
        urls = url_pattern.findall(text)
        text_without_urls = url_pattern.sub("", text)

        length = len(urls) * cls.TWITTER_URL_WEIGHT
        for char in text_without_urls:
            code = ord(char)
            # Emojis (0x1F000-0x1FAFF, 0x2600-0x27BF) and CJK ideographs count as 2
            if (0x1F000 <= code <= 0x1FAFF) or (0x2600 <= code <= 0x27BF) or (0x4E00 <= code <= 0x9FFF):
                length += 2
            else:
                length += 1
        return length

    @staticmethod
    def strip_em_dashes(text: str) -> str:
        """Replace all em-dashes and en-dashes with natural punctuation."""
        # Replace em-dash and en-dash with comma or standard dash
        cleaned = text.replace("—", ", ").replace("–", " - ")
        # Clean up possible double spaces or awkward comma spacing
        cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def clean_robotic_phrases(text: str) -> str:
        """Remove common LLM canned transition phrases."""
        result = text
        for pattern in ROBOTIC_PHRASES:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)
        # Fix leading lowercase or punctuation if phrase was stripped at start of sentence
        result = re.sub(r"^\s*,\s*", "", result)
        result = re.sub(r"\s+", " ", result).strip()
        if result and result[0].islower():
            result = result[0].upper() + result[1:]
        return result

    @staticmethod
    def enforce_sentence_limit(text: str, max_sentences: int = 3) -> str:
        """Ensure reply does not exceed the allowed sentence count."""
        # Split on sentence terminators (. ! ? and Arabic ؟ ۔)
        sentences = re.split(r"(?<=[.!?؟۔])\s+", text.strip())
        if len(sentences) > max_sentences:
            return " ".join(sentences[:max_sentences])
        return text

    @classmethod
    def enforce_length_limit(cls, text: str, max_length: int = 280) -> str:
        """
        Ensure tweet text does not exceed Twitter's maximum weighted length (280 chars).
        If a URL is attached at the end, preserves the URL while trimming
        the narrative text to sentence boundaries, or word boundaries if necessary.
        """
        if not text:
            return ""
        if cls.calculate_tweet_length(text) <= max_length:
            return text.strip()

        # Extract trailing URL if present to preserve proof citation
        url_pattern = re.compile(r"(https?://\S+)\s*$")
        match = url_pattern.search(text)
        url_suffix = ""
        narrative = text
        if match:
            url_suffix = match.group(1)
            narrative = text[:match.start()].strip()
            budget = max_length - cls.TWITTER_URL_WEIGHT - 1  # 1 for separating space
        else:
            budget = max_length

        # 1. Try sentence reduction (drop later sentences to keep complete thoughts)
        sentences = re.split(r"(?<=[.!?؟۔])\s+", narrative.strip())
        trimmed = None
        for i in range(len(sentences) - 1, 0, -1):
            candidate = " ".join(sentences[:i]).strip()
            if cls.calculate_tweet_length(candidate) <= budget:
                trimmed = candidate
                break

        # 2. If even a single sentence is too long, trim at word boundary
        if trimmed is None:
            words = narrative.split()
            candidate_words = []
            for w in words:
                cleaned_w = w.rstrip(".,;!?؟۔")
                candidate = (" ".join(candidate_words + [cleaned_w])).strip() + "..."
                if cls.calculate_tweet_length(candidate) <= budget:
                    candidate_words.append(cleaned_w)
                else:
                    break
            if candidate_words:
                trimmed = " ".join(candidate_words) + "..."
            else:
                # Extreme fallback: hard character slice
                trimmed = narrative[:max(1, budget - 3)] + "..."

        if url_suffix:
            result = f"{trimmed} {url_suffix}".strip()
        else:
            result = trimmed.strip()

        return result

    @staticmethod
    def match_whitelisted_link(text_or_claim: str, lang: str = "en") -> Optional[str]:
        """Find a verified primary-source URL matching keywords in the text/claim."""
        if not WHITELIST_PATH.exists():
            return None
        try:
            with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
                vault = json.load(f)
            lower_text = text_or_claim.lower()
            for key, data in vault.items():
                for kw in data.get("keywords", []):
                    if kw.lower() in lower_text:
                        sources = data.get("sources", {})
                        return sources.get(lang) or sources.get("en")
        except Exception:
            return None
        return None

    @classmethod
    def resolve_valid_link(
        cls,
        proposed_link: Optional[str],
        text_context: str,
        auto_attach_whitelist: bool = True,
        validate_http: bool = True
    ) -> Optional[str]:
        """
        Verify that a proposed or whitelisted link is alive (HTTP 200..399).
        If proposed link is dead/inaccessible, falls back to a verified whitelisted link.
        If no verified link is live, returns None.
        """
        # Local import to prevent circular dependencies
        from engine.link_validator import LinkValidator

        is_arabic = any("\u0600" <= c <= "\u06ff" for c in text_context)
        lang = "ar" if is_arabic else "en"

        # 1. Check proposed link first if given
        if proposed_link and proposed_link.strip():
            candidate = proposed_link.strip()
            if not validate_http or LinkValidator.is_alive(candidate):
                return candidate
            logger.warning(f"Proposed link '{candidate}' failed health check. Attempting whitelist fallback.")

        # 2. Whitelist fallback based on text keywords
        if auto_attach_whitelist:
            whitelisted = cls.match_whitelisted_link(text_context, lang=lang)
            if whitelisted and whitelisted.strip():
                candidate = whitelisted.strip()
                if not validate_http or LinkValidator.is_alive(candidate):
                    return candidate
                logger.warning(f"Whitelisted link '{candidate}' failed health check.")

        return None

    @classmethod
    def sanitize(
        cls,
        text: str,
        link: Optional[str] = None,
        auto_attach_whitelist: bool = True,
        validate_links: bool = True,
        max_length: int = 280
    ) -> str:
        """Run complete sanitation pipeline on draft reply text."""
        sanitized = cls.strip_em_dashes(text)
        sanitized = cls.clean_robotic_phrases(sanitized)
        sanitized = cls.enforce_sentence_limit(sanitized, max_sentences=3)

        # Check existing trailing URL if present in text
        url_match = re.search(r"(https?://\S+)\s*$", sanitized)
        extracted_link = url_match.group(1) if url_match else None
        if extracted_link:
            # Strip trailing URL from narrative before resolving validated link
            sanitized = sanitized[:url_match.start()].strip()
            if not link:
                link = extracted_link

        effective_link = cls.resolve_valid_link(
            proposed_link=link,
            text_context=sanitized,
            auto_attach_whitelist=auto_attach_whitelist,
            validate_http=validate_links
        )

        if effective_link and effective_link.strip() and effective_link not in sanitized:
            sanitized = f"{sanitized} {effective_link.strip()}"

        # Strictly enforce Twitter's 280-character limit
        sanitized = cls.enforce_length_limit(sanitized, max_length=max_length)

        return sanitized.strip()
