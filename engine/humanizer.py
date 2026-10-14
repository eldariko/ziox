"""Anti-Bot Humanizer and Text Sanitation Engine."""

import re
import json
from pathlib import Path
from typing import List, Optional

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
    def sanitize(
        cls,
        text: str,
        link: Optional[str] = None,
        auto_attach_whitelist: bool = True
    ) -> str:
        """Run complete sanitation pipeline on draft reply text."""
        sanitized = cls.strip_em_dashes(text)
        sanitized = cls.clean_robotic_phrases(sanitized)
        sanitized = cls.enforce_sentence_limit(sanitized, max_sentences=3)

        effective_link = link
        if not effective_link and auto_attach_whitelist:
            is_arabic = any("\u0600" <= c <= "\u06ff" for c in sanitized)
            lang = "ar" if is_arabic else "en"
            effective_link = cls.match_whitelisted_link(sanitized, lang=lang)

        if effective_link and effective_link.strip() and effective_link not in sanitized:
            sanitized = f"{sanitized} {effective_link.strip()}"

        return sanitized.strip()
