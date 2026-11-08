"""Unit tests for Tier-1 Gemini Multi-Model Fallback, Schema Enforcement, and Bare-Homepage Rejection."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from engine.grounding import GroundingEngine, FactCheckResult, DraftVariation
from engine.humanizer import Humanizer
from engine.link_validator import LinkValidator


class _MockModelsAPI:
    def __init__(self, side_effects):
        self.side_effects = list(side_effects)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        effect = self.side_effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


def _make_gemini_response(payload: dict):
    return SimpleNamespace(
        text=json.dumps(payload),
        candidates=[],
    )


def test_multi_model_fallback_rotates_on_503_or_404():
    """When primary model returns 404 NOT_FOUND or 503 UNAVAILABLE, GroundingEngine rotates to the next fallback model."""
    engine = GroundingEngine(
        api_key="",
        model_name="gemini-3.8-flash",
        fallback_models=["gemini-3.5-flash", "gemini-3.5-flash-lite"],
        enable_search=False,
    )
    valid_payload = {
        "is_worth_replying": True,
        "claim_identified": "False claim about arrest",
        "verified_facts": ["Arrests follow judicial warrants."],
        "recommended_link": None,
        "draft_reply": "Arrests are based on security investigations and judicial oversight, not op-eds.",
        "draft_variations": [
            {
                "style": "factual",
                "text": "Arrests are based on security investigations and judicial oversight, not op-eds.",
                "recommended_link": None,
            }
        ],
    }
    mock_models = _MockModelsAPI(
        [
            RuntimeError("404 NOT_FOUND: This model is no longer available. Please update your code to use gemini-3.8-flash"),
            _make_gemini_response(valid_payload),
        ]
    )
    engine.client = SimpleNamespace(models=mock_models)

    with patch("time.sleep", return_value=None):
        result = engine.evaluate_and_draft(
            tweet_text="Israel arrested him just for writing an article!",
            author_handle="testuser",
            num_variations=1,
        )

    assert result.is_worth_replying is True
    assert len(mock_models.calls) == 2
    assert mock_models.calls[0]["model"] == "gemini-3.8-flash"
    assert mock_models.calls[1]["model"] == "gemini-3.5-flash"


def test_search_available_preserved_on_transient_503_but_disabled_on_429():
    """Transient 503 should NOT permanently disable self.search_available, whereas 429 RESOURCE_EXHAUSTED does."""
    engine = GroundingEngine(
        api_key="",
        model_name="gemini-3.8-flash",
        fallback_models=["gemini-3.5-flash-lite"],
        enable_search=True,
    )
    valid_payload = {
        "is_worth_replying": True,
        "claim_identified": "Test claim",
        "verified_facts": ["Fact 1"],
        "recommended_link": None,
        "draft_reply": "Verified rebuttal sentence.",
        "draft_variations": [{"style": "factual", "text": "Verified rebuttal sentence.", "recommended_link": None}],
    }

    # Case 1: 503 followed by success -> search_available remains True
    mock_models_503 = _MockModelsAPI(
        [
            RuntimeError("503 UNAVAILABLE"),
            _make_gemini_response(valid_payload),
        ]
    )
    engine.client = SimpleNamespace(models=mock_models_503)

    with patch("time.sleep", return_value=None):
        res1 = engine.evaluate_and_draft("Test tweet 1", "user1", num_variations=1)
    assert res1.is_worth_replying is True
    assert engine.search_available is True

    # Case 2: 429 RESOURCE_EXHAUSTED when tools active -> search_available becomes False
    mock_models_429 = _MockModelsAPI(
        [
            RuntimeError("429 RESOURCE_EXHAUSTED: Search quota exceeded"),
            _make_gemini_response(valid_payload),
        ]
    )
    engine.client = SimpleNamespace(models=mock_models_429)

    with patch("time.sleep", return_value=None):
        res2 = engine.evaluate_and_draft("Test tweet 2", "user2", num_variations=1)
    assert res2.is_worth_replying is True
    assert engine.search_available is False


def test_bare_homepage_rejected_without_network_call():
    """Bare domain homepages like https://www.timesofisrael.com are rejected without HTTP requests, while whitelisted roots pass."""
    LinkValidator.clear_cache()

    assert LinkValidator.is_bare_homepage("https://www.timesofisrael.com") is True
    assert LinkValidator.is_bare_homepage("https://www.timesofisrael.com/") is True
    assert LinkValidator.is_bare_homepage("https://www.bbc.com") is True

    # Deep article path is NOT a bare homepage
    assert LinkValidator.is_bare_homepage("https://www.timesofisrael.com/some-specific-article-2026/") is False

    # Whitelisted root URL in whitelisted_sources.json is permitted
    assert LinkValidator.is_bare_homepage("https://gaza-aid-data.gov.il/") is False

    # GroundingEngine._normalize_result strips bare homepages from recommended_link
    engine = GroundingEngine(api_key="")
    raw_result = FactCheckResult(
        is_worth_replying=True,
        claim_identified="Claim",
        verified_facts=["Fact"],
        recommended_link="https://www.timesofisrael.com",
        draft_reply="Short factual reply.",
        draft_variations=[
            DraftVariation(
                style="factual",
                text="Short factual reply.",
                recommended_link="https://www.timesofisrael.com",
            )
        ],
    )
    normalized = engine._normalize_result(raw_result)
    assert normalized.recommended_link is None
    assert normalized.draft_variations[0].recommended_link is None


def test_humanizer_skips_bare_homepage_without_http_403():
    """Humanizer.diversify_links_for_variations strips bare homepages before LinkValidator HTTP checks."""
    variations = [
        DraftVariation(
            style="factual",
            text="Arrests are based on security investigations and judicial oversight, not op-eds.",
            recommended_link="https://www.timesofisrael.com",
        )
    ]
    with patch.object(LinkValidator, "is_alive") as mock_alive:
        sanitized = Humanizer.diversify_links_for_variations(
            variations=variations,
            tweet_text="Unrelated topic without whitelist match",
            validate_links=True,
            no_link_variation_ratio=0.0,
        )
        # Should not even call LinkValidator.is_alive on https://www.timesofisrael.com
        mock_alive.assert_not_called()
        assert len(sanitized) == 1
        assert sanitized[0]["link"] is None
        assert "timesofisrael.com" not in sanitized[0]["text"]
