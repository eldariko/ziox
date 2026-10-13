"""Anti-Bot Humanizer and Text Sanitation Engine."""

import re
from typing import List, Optional

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
    r"\bit'?s important to remember\b\s*"
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
        # Split on sentence terminators (. ! ?)
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        if len(sentences) > max_sentences:
            return " ".join(sentences[:max_sentences])
        return text

    @classmethod
    def sanitize(
        cls,
        text: str,
        link: Optional[str] = None
    ) -> str:
        """Run complete sanitation pipeline on draft reply text."""
        sanitized = cls.strip_em_dashes(text)
        sanitized = cls.clean_robotic_phrases(sanitized)
        sanitized = cls.enforce_sentence_limit(sanitized, max_sentences=3)

        if link and link.strip() and link not in sanitized:
            sanitized = f"{sanitized} {link.strip()}"

        return sanitized.strip()
