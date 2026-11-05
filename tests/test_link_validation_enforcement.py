"""Unit tests for live link validation enforcement during variation diversification."""

from unittest.mock import patch
from engine.humanizer import Humanizer


def test_diversify_links_with_validate_links_purges_dead_links():
    """Verify that when validate_links=True, inaccessible links are stripped, preserving clean text."""
    variations = [
        {"style": "factual", "text": "This is a factual claim about hostages.", "recommended_link": "https://example.com/dead-link-404"},
        {"style": "sharp", "text": "This is a sharp counter claim about hostages.", "recommended_link": "https://example.com/live-link-200"}
    ]

    def mock_check_url(url, timeout=4.0, use_cache=True, verify_content=True):
        if "live-link-200" in url or "ajc.org" in url or "nbcnews.com" in url:
            return True, 200
        return False, 404

    with patch("engine.link_validator.LinkValidator.check_url", side_effect=mock_check_url):
        # Pass validate_links=True
        results = Humanizer.diversify_links_for_variations(
            variations=variations,
            tweet_text="A post talking about hostages in October 7",
            validate_links=True,
            max_length=280,
            no_link_variation_ratio=0.0
        )

        assert len(results) == 2
        for r in results:
            # None of the results should contain the dead link
            assert "dead-link-404" not in r["text"]
            assert r["link"] != "https://example.com/dead-link-404"
            if r["link"]:
                assert r["link"] in r["text"]


def test_diversify_links_all_dead_returns_clean_text():
    """Verify that if all candidate links fail HTTP checks, variations are delivered as clean text without crashing."""
    variations = [
        {"style": "factual", "text": "Factual reply text without valid links.", "recommended_link": "https://invalid-domain.xyz/test"}
    ]

    with patch("engine.link_validator.LinkValidator.check_url", return_value=(False, 0)):
        results = Humanizer.diversify_links_for_variations(
            variations=variations,
            tweet_text="Unrelated text without keyword match",
            validate_links=True,
            max_length=280,
            no_link_variation_ratio=0.0
        )

        assert len(results) == 1
        assert results[0]["link"] is None
        assert "http" not in results[0]["text"]
        assert results[0]["text"] == "Factual reply text without valid links."
