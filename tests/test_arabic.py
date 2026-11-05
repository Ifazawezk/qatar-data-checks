import unicodedata

import pandas as pd
import pytest

from qatar_data_checks import Check, ConfigError
from qatar_data_checks.arabic import script_share, text_issues


@pytest.mark.parametrize(
    "text, issues",
    [
        ("قانون العمل القطري", []),
        ("المادة 14 من القانون", []),
        ("iPhone 15 برو", []),  # Latin and Arabic words side by side are fine
        ("محمدali", ["mixed_script_word"]),
        ("المادة ١٤", ["arabic_indic_digits"]),
        ("سنة ۱۴۰۳", ["persian_digits"]),
        ("2024 ٢٠٢٤", ["arabic_indic_digits", "mixed_digits"]),
        ("ﻟﺎﻣ", ["presentation_forms"]),  # lam alef ... as copied from a PDF
        ("قـــانون", ["tatweel"]),
        ("الدوحة‏", ["invisible"]),
        ("علی", ["persian_letters"]),
        ("كتاب  جديد ", ["extra_spaces"]),
    ],
)
def test_text_issues(text, issues):
    assert text_issues(text) == issues


def test_nfc_order_of_marks():
    # shadda then fatha is how many keyboards type it; NFC puts fatha (ccc 30) first
    typed = "مَّ"
    assert text_issues(typed) == ["not_nfc"]
    assert text_issues(unicodedata.normalize("NFC", typed)) == []


def test_ignore():
    assert text_issues("المادة ١٤", ignore=["arabic_indic_digits"]) == []


def test_arabic_text_check_counts_each_issue():
    df = pd.DataFrame({"النص": ["نص سليم", "قـانون ١", "علی", None]})
    r = Check("arabic_text", "النص").run(df)
    assert (r.failed, r.total) == (2, 3)
    assert r.details == {"tatweel": 1, "arabic_indic_digits": 1, "persian_letters": 1}
    assert r.samples[0]["reason"] == "arabic_indic_digits; tatweel"
    with pytest.raises(ConfigError):
        Check("arabic_text", "النص", {"ignore": ["spelling"]}).run(df)


def test_script_share():
    assert script_share("قانون العمل", "arabic") == 1.0
    assert script_share("Labour law", "arabic") == 0.0
    assert script_share("123", "latin") is None
    assert script_share("قانون law", "latin") == pytest.approx(3 / 8)


def test_script_check():
    df = pd.DataFrame({"text": ["رائع جدا", "great service", "!!!"]})
    r = Check("script", "text", {"expect": "arabic"}).run(df)
    assert r.failed == 2 and r.details == {"under 50% arabic letters": 1, "no letters": 1}
