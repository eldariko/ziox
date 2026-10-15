"""Link Validation and Verification Engine for zioX."""

import re
import logging
import urllib.request
import urllib.error
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default timeout for checking URL availability
DEFAULT_TIMEOUT_SECONDS = 4.0

# Browser-like User-Agent to avoid spurious blocks from CDNs
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Minimum word count required in body to be considered a real article/document
MIN_ARTICLE_WORDS = 60


class LinkValidator:
    """Validates HTTP/HTTPS links and verifies that they contain real, substantive articles."""

    # In-memory validation cache: {url: (is_valid, status_code)}
    _cache: Dict[str, Tuple[bool, int]] = {}

    @classmethod
    def is_valid_url_syntax(cls, url: str) -> bool:
        """Check if string is a syntactically valid HTTP/HTTPS URL."""
        if not url or not isinstance(url, str):
            return False
        try:
            parsed = urlparse(url.strip())
            return parsed.scheme in ("http", "https") and bool(parsed.netloc)
        except Exception:
            return False

    @classmethod
    def check_url(
        cls,
        url: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        use_cache: bool = True,
        verify_content: bool = True
    ) -> Tuple[bool, int]:
        """
        Verify that a URL is alive, accessible, and contains substantive content (not an empty page or bot challenge).
        Returns:
            (is_healthy, status_code)
            is_healthy: True if HTTP status is 200..399 and page contains real content.
            status_code: HTTP response code or 0 on network/DNS failure.
        """
        if not cls.is_valid_url_syntax(url):
            return False, 0

        clean_url = url.strip()

        if use_cache and clean_url in cls._cache:
            return cls._cache[clean_url]

        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        # Perform GET request to inspect headers and body content
        try:
            get_req = urllib.request.Request(clean_url, headers=headers, method="GET")
            with urllib.request.urlopen(get_req, timeout=timeout) as resp:
                status = resp.status
                if not (200 <= status < 400):
                    if use_cache:
                        cls._cache[clean_url] = (False, status)
                    return False, status

                if verify_content:
                    # Read sample from response body (up to 40KB)
                    raw_sample = resp.read(40000)
                    try:
                        text_sample = raw_sample.decode("utf-8", errors="ignore")
                    except Exception:
                        text_sample = ""

                    # Detect empty Incapsula / Cloudflare JS challenge stubs with no article content
                    is_empty_incapsula = (
                        "_Incapsula_Resource" in text_sample
                        and len(text_sample) < 2000
                        and "<body" in text_sample.lower()
                        and "</body>" in text_sample.lower()
                    )
                    if is_empty_incapsula:
                        logger.warning(f"URL {clean_url} returned empty Incapsula challenge stub without article.")
                        if use_cache:
                            cls._cache[clean_url] = (False, status)
                        return False, status

                    # Strip HTML tags and count substantive visible words
                    clean_text = re.sub(r"<[^>]+>", " ", text_sample)
                    clean_text = re.sub(r"\s+", " ", clean_text).strip()
                    word_count = len(clean_text.split())

                    if word_count < MIN_ARTICLE_WORDS:
                        logger.warning(
                            f"URL {clean_url} is too thin/empty ({word_count} words < {MIN_ARTICLE_WORDS}). Rejected."
                        )
                        if use_cache:
                            cls._cache[clean_url] = (False, status)
                        return False, status

                if use_cache:
                    cls._cache[clean_url] = (True, status)
                return True, status

        except urllib.error.HTTPError as e:
            logger.warning(f"URL {clean_url} is dead/inaccessible: HTTP {e.code}")
            if use_cache:
                cls._cache[clean_url] = (False, e.code)
            return False, e.code
        except Exception as e:
            logger.warning(f"URL {clean_url} failed accessibility check: {e}")
            if use_cache:
                cls._cache[clean_url] = (False, 0)
            return False, 0

    @classmethod
    def is_alive(cls, url: Optional[str], verify_content: bool = True) -> bool:
        """Convenience method returning True only if URL is accessible and substantive."""
        if not url:
            return False
        is_ok, _ = cls.check_url(url, verify_content=verify_content)
        return is_ok

    @classmethod
    def clear_cache(cls) -> None:
        """Clear memory cache of validated URLs."""
        cls._cache.clear()
