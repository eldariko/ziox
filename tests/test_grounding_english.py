"""Unit tests for English-only prompt enforcement in Gemini Grounding Engine."""

from engine.grounding import SYSTEM_PROMPT


def test_system_prompt_strictly_requires_english():
    """Verify that SYSTEM_PROMPT restricts replies and evaluations strictly to English only."""
    assert "ENGLISH ONLY" in SYSTEM_PROMPT
    assert "NEVER generate replies in Arabic, Hebrew, or any other non-English language" in SYSTEM_PROMPT
    assert "rebutting the claim in English only" in SYSTEM_PROMPT
    assert "Restrict replies strictly to ENGLISH and ARABIC only" not in SYSTEM_PROMPT
