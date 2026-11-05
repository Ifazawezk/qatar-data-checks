"""Small text helpers shared by the checks.

Arabic text often reaches a dataset with invisible marks, tatweel or presentation
forms copied out of PDFs. `canonical` folds those away so two values that look the
same on screen also compare equal.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata

ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"  # U+0660 to U+0669
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"  # U+06F0 to U+06F9
EASTERN_DIGITS = ARABIC_INDIC_DIGITS + PERSIAN_DIGITS
_TO_ASCII = str.maketrans(EASTERN_DIGITS, "0123456789" * 2)

TATWEEL = "ـ"
# Soft hyphen, Arabic letter mark, zero width and directional marks, bidi embeddings
# and isolates, and the byte order mark. Unicode UAX #9 lists the bidi controls.
INVISIBLE = re.compile("[­؜​-‏‪-‮⁦-⁩﻿]")


def to_ascii_digits(text: str) -> str:
    return text.translate(_TO_ASCII)


def has_eastern_digits(text: str) -> bool:
    return any(ch in EASTERN_DIGITS for ch in text)


def canonical(text: str) -> str:
    """NFKC, without invisible marks or tatweel, with single spaces."""
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE.sub("", text).replace(TATWEEL, "")
    return " ".join(text.split())


def as_text(value) -> str:
    """A stable string for any cell: 3.0 becomes "3", lists become JSON."""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if hasattr(value, "item") and not isinstance(value, str):  # numpy scalars
        return as_text(value.item())
    return str(value)


_GROUPING = re.compile(r"(?<=[0-9]),(?=[0-9]{3}(?![0-9]))")


def ungroup(text: str) -> str:
    """1,250.50 becomes 1250.50."""
    return _GROUPING.sub("", text)


def shorten(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."
