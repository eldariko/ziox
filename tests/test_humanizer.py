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


def test_arabic_sentence_limit_and_robotic_phrases():
    raw = "من الجدير بالذكر أن الشاحنات دخلت بالفعل. هل تم توزيعها بشكل صحيح؟ هذا هو السؤال. جملة رابعة إضافية."
    cleaned = Humanizer.clean_robotic_phrases(raw)
    assert "من الجدير بالذكر" not in cleaned

    enforced = Humanizer.enforce_sentence_limit(cleaned, max_sentences=2)
    assert "جملة رابعة" not in enforced


def test_whitelisted_link_auto_attach():
    # English test for aid claim
    raw_en = "Over 30,000 aid trucks entered via Kerem Shalom crossing."
    sanitized_en = Humanizer.sanitize(raw_en)
    assert "https://govextra.gov.il/cogat/humanitarian-efforts/home/" in sanitized_en

    # Arabic test for partition claim
    raw_ar = "وافقت إسرائيل على قرار التقسيم رقم 181 عام 1947."
    sanitized_ar = Humanizer.sanitize(raw_ar)
    assert "https://www.un.org/unispal/document/auto-insert-179838/" in sanitized_ar


