"""Arabic text quality and script checks.

Code point ranges come from the Unicode Standard code charts: Arabic (U+0600 to
U+06FF), Arabic Supplement (U+0750 to U+077F), Arabic Extended-A (U+08A0 to U+08FF)
and Arabic Presentation Forms-A and -B (U+FB50 to U+FDFF, U+FE70 to U+FEFF).
Normalisation follows Unicode UAX #15. Presentation forms usually mean the text
was copied out of a PDF; NFKC maps them back to ordinary letters.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd

from .checks import ConfigError, register
from .text import ARABIC_INDIC_DIGITS, INVISIBLE, PERSIAN_DIGITS, TATWEEL, as_text

ISSUES = {
    "mixed_script_word": "a word mixes Arabic and Latin letters",
    "arabic_indic_digits": "Arabic-Indic digits (U+0660 to U+0669)",
    "persian_digits": "Persian digits (U+06F0 to U+06F9)",
    "mixed_digits": "ASCII and Arabic-Indic digits in one value",
    "presentation_forms": "presentation forms (U+FB50 to U+FDFF, U+FE70 to U+FEFE)",
    "tatweel": "tatweel (U+0640)",
    "invisible": "invisible or bidi control characters",
    "persian_letters": "Persian yeh or keheh (U+06CC, U+06A9) instead of Arabic yeh or kaf",
    "not_nfc": "not in NFC form",
    "extra_spaces": "leading, trailing or repeated spaces",
}

_PRESENTATION = re.compile("[ﭐ-﷿ﹰ-﻾]")
_REPEATED_SPACE = re.compile(r"[ \t ]{2,}")


def is_arabic_letter(ch: str) -> bool:
    code = ord(ch)
    in_block = (
        0x0600 <= code <= 0x06FF
        or 0x0750 <= code <= 0x077F
        or 0x08A0 <= code <= 0x08FF
        or 0xFB50 <= code <= 0xFDFF
        or 0xFE70 <= code <= 0xFEFF
    )
    return in_block and unicodedata.category(ch).startswith("L")


def is_latin_letter(ch: str) -> bool:
    code = ord(ch)
    return (code <= 0x024F or 0x1E00 <= code <= 0x1EFF) and unicodedata.category(ch).startswith("L")


def text_issues(text: str, ignore=()) -> list[str]:
    """Names of the issues found in one value, in ISSUES order."""
    found = set()
    for word in text.split():
        if any(map(is_arabic_letter, word)) and any(map(is_latin_letter, word)):
            found.add("mixed_script_word")
            break
    has_ascii_digit = any("0" <= ch <= "9" for ch in text)
    has_indic = any(ch in ARABIC_INDIC_DIGITS for ch in text)
    has_persian = any(ch in PERSIAN_DIGITS for ch in text)
    if has_indic:
        found.add("arabic_indic_digits")
    if has_persian:
        found.add("persian_digits")
    if has_ascii_digit and (has_indic or has_persian):
        found.add("mixed_digits")
    if _PRESENTATION.search(text):
        found.add("presentation_forms")
    if TATWEEL in text:
        found.add("tatweel")
    if INVISIBLE.search(text):
        found.add("invisible")
    if "ی" in text or "ک" in text:
        found.add("persian_letters")
    if not unicodedata.is_normalized("NFC", text):
        found.add("not_nfc")
    if text != text.strip() or _REPEATED_SPACE.search(text):
        found.add("extra_spaces")
    return [name for name in ISSUES if name in found and name not in ignore]


@register("arabic_text", describe="Arabic text quality issues")
def arabic_text(values, frame, ctx, ignore=()):
    """Flags the issues in ISSUES. `ignore` turns some off, for example
    [arabic_indic_digits] for a column where those digits are expected."""
    unknown = set(ignore) - set(ISSUES)
    if unknown:
        raise ConfigError(f"arabic_text cannot ignore {', '.join(sorted(unknown))}; issues are {', '.join(ISSUES)}")
    return values.map(lambda v: "; ".join(text_issues(as_text(v), ignore))).astype(object)


def script_share(text: str, script: str) -> float | None:
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    if not letters:
        return None
    test = is_arabic_letter if script == "arabic" else is_latin_letter
    return sum(map(test, letters)) / len(letters)


@register("script", describe="values not mostly in the expected script", main="expect")
def script(values, frame, ctx, expect="arabic", min_share=0.5):
    """A rough language check: the share of letters in the expected script.
    It cannot tell Arabic from Persian or English from French."""
    if expect not in ("arabic", "latin"):
        raise ConfigError("script expect must be arabic or latin")

    def problem(v) -> str:
        share = script_share(as_text(v), expect)
        if share is None:
            return "no letters"
        return f"{share:.0%} {expect} letters" if share < min_share else ""

    return values.map(problem).astype(object)


def issue_counts(values: pd.Series) -> dict[str, int]:
    """How many values have each issue; used by the profiler."""
    counts: dict[str, int] = {}
    for v in values.dropna():
        for name in text_issues(as_text(v)):
            counts[name] = counts.get(name, 0) + 1
    return counts
