from engine.humanizer import Humanizer


def test_strip_em_dashes():
    raw = "Israel did not close the crossing—it was closed by local militia."
    cleaned = Humanizer.strip_em_dashes(raw)
    assert "—" not in cleaned
    assert "Israel did not close the crossing, it was closed by local militia." == cleaned


def test_clean_robotic_phrases():
    raw = "It's crucial to understand that COGAT published the numbers. Moreover, aid continues to enter."
    cleaned = Humanizer.clean_robotic_phrases(raw)
    assert "crucial to understand" not in cleaned.lower()
    assert "Moreover" not in cleaned


def test_sentence_limit():
    raw = "Sentence one. Sentence two! Sentence three? Sentence four."
    enforced = Humanizer.enforce_sentence_limit(raw, max_sentences=3)
    assert enforced == "Sentence one. Sentence two! Sentence three?"


def test_full_sanitize_with_link():
    raw = "Delving into the history—facts remain clear. Over 20,000 trucks entered."
    link = "https://govextra.gov.il/cogat/"
    sanitized = Humanizer.sanitize(raw, link=link)

    assert "—" not in sanitized
    assert "delving into" not in sanitized.lower()
    assert link in sanitized
