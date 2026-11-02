"""Anti-Bot Humanizer and Text Sanitation Engine."""

import re
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

WHITELIST_PATH = Path(__file__).resolve().parent.parent / "assets" / "proofs" / "whitelisted_sources.json"

INLINE_URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

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
        urls = INLINE_URL_PATTERN.findall(text)
        text_without_urls = INLINE_URL_PATTERN.sub("", text)

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
        cleaned = text.replace("—", ", ").replace("–", " - ")
        cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def strip_inline_urls(text: str) -> str:
        """Remove any raw HTTP/HTTPS URLs embedded inside the narrative text."""
        if not text:
            return ""
        cleaned = INLINE_URL_PATTERN.sub("", text)
        return re.sub(r"\s+", " ", cleaned).strip()

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
                trimmed = narrative[:max(1, budget - 3)] + "..."

        if url_suffix:
            result = f"{trimmed} {url_suffix}".strip()
        else:
            result = trimmed.strip()

        return result

    @staticmethod
    def match_whitelisted_link(text_or_claim: str, lang: str = "en") -> Optional[str]:
        """
        Find a verified primary-source URL matching keywords in the text/claim.
        Uses boundary checking to prevent substring collisions (e.g. 'aid' in 'said').
        """
        if not WHITELIST_PATH.exists():
            return None
        try:
            with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
                vault = json.load(f)
            lower_text = text_or_claim.lower()
            for key, data in vault.items():
                for kw in data.get("keywords", []):
                    pattern = r"(?<!\w)" + re.escape(kw.lower()) + r"(?!\w)"
                    if re.search(pattern, lower_text):
                        sources = data.get("sources", {})
                        return sources.get(lang) or sources.get("en")
        except Exception:
            return None
        return None

    @staticmethod
    def match_whitelisted_links_pool(text_or_claim: str, lang: str = "en") -> List[str]:
        """
        Return a pool of distinct whitelisted URLs matching keywords in `text_or_claim`.
        Used to diversify proof URLs across multiple community reply variations.
        Strictly requires keyword matching; never falls back to arbitrary unrelated categories.
        """
        if not WHITELIST_PATH.exists():
            return []
        try:
            with open(WHITELIST_PATH, "r", encoding="utf-8") as f:
                vault = json.load(f)
            lower_text = text_or_claim.lower()
            pool: List[str] = []
            for key, data in vault.items():
                matched = False
                for kw in data.get("keywords", []):
                    pattern = r"(?<!\w)" + re.escape(kw.lower()) + r"(?!\w)"
                    if re.search(pattern, lower_text):
                        matched = True
                        break
                if matched:
                    sources = data.get("sources", {})
                    primary = sources.get(lang) or sources.get("en")
                    if primary and primary not in pool:
                        pool.append(primary)
                    for alt in data.get("alternate_sources", []):
                        if alt and alt not in pool:
                            pool.append(alt)
            return pool
        except Exception:
            return []

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
        """
        Run complete sanitation pipeline on draft reply text.
        Guarantees at most ONE proof URL is present at the end of the reply.
        """
        sanitized = cls.strip_em_dashes(text)
        sanitized = cls.clean_robotic_phrases(sanitized)
        sanitized = cls.enforce_sentence_limit(sanitized, max_sentences=3)

        # Extract any inline URL if no explicit link was passed, then strip ALL inline URLs from narrative
        found_urls = INLINE_URL_PATTERN.findall(sanitized)
        if found_urls:
            if not link:
                link = found_urls[-1]
            sanitized = cls.strip_inline_urls(sanitized)

        effective_link = cls.resolve_valid_link(
            proposed_link=link,
            text_context=sanitized,
            auto_attach_whitelist=auto_attach_whitelist,
            validate_http=validate_links
        )

        if effective_link and effective_link.strip():
            sanitized = f"{sanitized} {effective_link.strip()}"

        # Strictly enforce Twitter's 280-character limit
        sanitized = cls.enforce_length_limit(sanitized, max_length=max_length)

        return sanitized.strip()

    @classmethod
    def diversify_links_for_variations(
        cls,
        variations: List[Any],
        tweet_text: str,
        validate_links: bool = False,
        max_length: int = 280,
        no_link_variation_ratio: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        Sanitize a list of `DraftVariation` objects (or dicts), stripping any accidental
        inline URLs from each variation's `text`, attaching diversified whitelisted proof URLs
        across the variations (or omitting links for `no_link_variation_ratio` of variations),
        and enforcing the 280-character limit.

        Returns a list of dicts:
          [{"style": str, "text": str, "link": Optional[str]}, ...]
        """
        is_arabic = any("\u0600" <= c <= "\u06ff" for c in tweet_text)
        lang = "ar" if is_arabic else "en"
        link_pool = cls.match_whitelisted_links_pool(tweet_text, lang=lang)

        # Filter valid variations first so we know the exact count
        valid_items = []
        for var in variations:
            style = getattr(var, "style", None) or (var.get("style") if isinstance(var, dict) else "factual") or "factual"
            raw_text = getattr(var, "text", None) if not isinstance(var, dict) else var.get("text", "")
            var_link = getattr(var, "recommended_link", None) if not isinstance(var, dict) else var.get("recommended_link")
            clean_narrative = cls.strip_inline_urls(raw_text or "")
            if clean_narrative:
                valid_items.append((style, clean_narrative, var_link))

        total_valid = len(valid_items)
        clamped_ratio = max(0.0, min(1.0, float(no_link_variation_ratio)))
        target_linkless_count = int(round(total_valid * clamped_ratio))

        # Distribute linkless slots evenly across the cohort (selecting from the end/interleaved)
        linkless_indices = set()
        if target_linkless_count > 0 and total_valid > 0:
            for k in range(target_linkless_count):
                # Spread evenly across indices
                idx_slot = int(((k + 1) * total_valid) // (target_linkless_count + 1))
                while idx_slot in linkless_indices and idx_slot < total_valid - 1:
                    idx_slot += 1
                while idx_slot in linkless_indices and idx_slot > 0:
                    idx_slot -= 1
                linkless_indices.add(idx_slot)

        sanitized_variations: List[Dict[str, Any]] = []
        used_links: List[str] = []
        link_idx = 0

        for idx, (style, clean_narrative, var_link) in enumerate(valid_items):
            if idx in linkless_indices:
                final_text = cls.sanitize(
                    text=clean_narrative,
                    link=None,
                    auto_attach_whitelist=False,
                    validate_links=False,
                    max_length=max_length,
                )
                sanitized_variations.append({
                    "style": style,
                    "text": final_text,
                    "link": None,
                })
                continue

            # Pick a diversified link from the pool if available
            chosen_link: Optional[str] = None
            if link_pool:
                for candidate in link_pool:
                    if candidate not in used_links:
                        chosen_link = candidate
                        break
                if not chosen_link:
                    chosen_link = link_pool[link_idx % len(link_pool)]
                link_idx += 1
            elif var_link:
                chosen_link = var_link

            if chosen_link:
                used_links.append(chosen_link)

            final_text = cls.sanitize(
                text=clean_narrative,
                link=chosen_link,
                auto_attach_whitelist=(chosen_link is None),
                validate_links=validate_links,
                max_length=max_length,
            )

            sanitized_variations.append({
                "style": style,
                "text": final_text,
                "link": chosen_link,
            })

        return sanitized_variations
