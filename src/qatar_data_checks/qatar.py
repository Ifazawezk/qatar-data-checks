"""Format checks for Qatar ID numbers, Qatar phone numbers and QAR amounts.

These look at the shape of a value only. A value that passes can still be a number
that was never issued or a phone line that does not exist; nothing here contacts
any registry.

Sources for each rule:
- Qatar ID: Microsoft Purview, "Qatari ID card number entity definition"
  (learn.microsoft.com/en-us/purview/sit-defn-qatari-id-card-number): 11 digits,
  a 2 or 3, two digits for the year of birth, a three digit ISO country code,
  then five digits, with no checksum. Reading the first digit as the birth century
  (2 for 1900s, 3 for 2000s) is the common public explanation, not an official one.
- Phone: the national numbering plan Qatar filed with the ITU (itu.int/oth/T02020000AB),
  as summarised on Wikipedia, "Telephone numbers in Qatar": country code +974, no
  trunk prefix, 8 digit numbers since 2010, mobile numbers start with 3, 5, 6 or 7,
  fixed lines with 4, and toll free numbers are 800 plus 4 digits.
- QAR: ISO 4217 lists the Qatari riyal as QAR, numeric code 634, with 2 minor units
  (100 dirham).
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from .checks import ConfigError, register
from .text import as_text, has_eastern_digits, to_ascii_digits

PHONE_KINDS = ("mobile", "landline", "toll_free")
_SEPARATORS = re.compile(r"[\s\-.() ]")
_CURRENCY = r"(?:QAR|QR|ر\.?\s?ق\.?|ريال(?:\s+قطري)?)"
_CURRENCY_EDGE = re.compile(rf"^{_CURRENCY}\s*|\s*{_CURRENCY}$", re.IGNORECASE)
_GROUPED = re.compile(r"-?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
_PLAIN = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")


def _reasons(values: pd.Series, fn) -> pd.Series:
    return values.map(fn).astype(object)


def qatar_id_problem(value, nationalities=None, arabic_digits=False, today: dt.date | None = None) -> str:
    text = as_text(value).strip()
    if has_eastern_digits(text):
        if not arabic_digits:
            return "Arabic-Indic digits"
        text = to_ascii_digits(text)
    if not re.fullmatch(r"[0-9]{11}", text):
        return "not 11 digits"
    if text[0] not in "23":
        return "first digit is not 2 or 3"
    year = (1900 if text[0] == "2" else 2000) + int(text[1:3])
    if year > (today or dt.date.today()).year:
        return f"birth year {year} is in the future"
    code = int(text[3:6])
    if code == 0:
        return "nationality code 000"
    if nationalities is not None and code not in {int(c) for c in nationalities}:
        return f"nationality code {text[3:6]} not in the allowed list"
    return ""


def phone_kind(value, country_code: str = "optional", arabic_digits: bool = False) -> tuple[str | None, str]:
    """Return (kind, problem). kind is mobile, landline or toll_free."""
    text = _SEPARATORS.sub("", as_text(value).strip())
    if has_eastern_digits(text):
        if not arabic_digits:
            return None, "Arabic-Indic digits"
        text = to_ascii_digits(text)
    has_code = False
    for prefix in ("+974", "00974"):
        if text.startswith(prefix):
            text, has_code = text[len(prefix):], True
            break
    else:
        if text.startswith("974") and len(text) == 11:
            text, has_code = text[3:], True
    if country_code == "required" and not has_code:
        return None, "no +974 country code"
    if country_code == "forbidden" and has_code:
        return None, "has a country code"
    if not re.fullmatch(r"[0-9]+", text):
        return None, "not a phone number"
    if len(text) == 7 and text.startswith("800"):
        return "toll_free", ""
    if len(text) != 8:
        return None, f"{len(text)} digits, expected 8"
    if text[0] in "3567":
        return "mobile", ""
    if text[0] == "4":
        return "landline", ""
    return None, f"starts with {text[0]}, not a mobile (3, 5, 6, 7) or landline (4) prefix"


def qar_problem(value, decimals=2, negative=False, currency=True, arabic_digits=False) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if abs(round(number, decimals) - number) > 1e-9 * max(1.0, abs(number)):
            return f"more than {decimals} decimal places"
        return "negative amount" if number < 0 and not negative else ""
    text = as_text(value).strip()
    stripped = _CURRENCY_EDGE.sub("", text).strip()
    if stripped != text and not currency:
        return "currency text in the value"
    if has_eastern_digits(stripped) or "٫" in stripped or "٬" in stripped:
        if not arabic_digits:
            return "Arabic-Indic digits"
        stripped = to_ascii_digits(stripped).replace("٫", ".").replace("٬", ",")
    if not (_PLAIN.fullmatch(stripped) or _GROUPED.fullmatch(stripped)):
        return "not an amount"
    places = len(stripped.split(".")[1]) if "." in stripped else 0
    if places > decimals:
        return f"{places} decimal places, expected at most {decimals}"
    if stripped.startswith("-") and not negative:
        return "negative amount"
    return ""


@register("qatar_id", describe="values not in the Qatar ID format")
def qatar_id(values, frame, ctx, nationalities=None, arabic_digits=False):
    """11 digits: 2 or 3, birth year, ISO 3166 numeric nationality code, serial.
    `nationalities` limits the code, for example [634] for Qatari citizens."""
    return _reasons(values, lambda v: qatar_id_problem(v, nationalities, arabic_digits))


@register("qatar_phone", describe="values not in the Qatar phone number format")
def qatar_phone(values, frame, ctx, kind="any", country_code="optional", arabic_digits=False):
    """+974 is optional by default; country_code can be required or forbidden.
    kind is any, mobile, landline, toll_free or a list of those."""
    wanted = set(PHONE_KINDS) if kind == "any" else set([kind] if isinstance(kind, str) else kind)
    if not wanted <= set(PHONE_KINDS):
        raise ConfigError(f"qatar_phone kind must be any or one of {', '.join(PHONE_KINDS)}")

    def problem(v) -> str:
        found, issue = phone_kind(v, country_code, arabic_digits)
        if issue:
            return issue
        return "" if found in wanted else f"{found.replace('_', ' ')} number"

    return _reasons(values, problem)


@register("qar_amount", describe="values not in the QAR amount format")
def qar_amount(values, frame, ctx, decimals=2, negative=False, currency=True, arabic_digits=False):
    """A number with at most `decimals` places (2 for QAR). Accepts 1,250.50 and
    a QAR, QR or ر.ق marker unless currency is false."""
    return _reasons(values, lambda v: qar_problem(v, decimals, negative, currency, arabic_digits))
