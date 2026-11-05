"""Qatar calendar labels for dates: Ramadan, the two Eids and fixed holidays.

Hijri dates come from the Umm al-Qura calendar through the hijridate package. Qatar
announces Ramadan and the Eids from moon sightings, so the real first day can be a
day off the calculated one, and the official Eid holiday is often longer than the
days used here.

- Ramadan: every day of Hijri month 9
- Eid al-Fitr: 1 to 3 Shawwal
- Eid al-Adha: 9 Dhu al-Hijjah (Arafat Day) to 12 Dhu al-Hijjah
- National Day: 18 December; National Sport Day: second Tuesday of February
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import pandas as pd
from hijridate import Gregorian

GROUPS = {
    "ramadan": {"ramadan"},
    "eid": {"eid_al_fitr", "eid_al_adha"},
    "eid_al_fitr": {"eid_al_fitr"},
    "eid_al_adha": {"eid_al_adha"},
    "holidays": {"national_day", "sport_day"},
}


@lru_cache(maxsize=None)
def day_label(day: dt.date) -> str:
    if day.month == 12 and day.day == 18:
        return "national_day"
    if day.month == 2 and day.weekday() == 1 and 8 <= day.day <= 14:
        return "sport_day"
    try:
        hijri = Gregorian(day.year, day.month, day.day).to_hijri()
    except (OverflowError, ValueError):  # outside 1343 to 1500 AH
        return ""
    if hijri.month == 9:
        return "ramadan"
    if hijri.month == 10 and hijri.day <= 3:
        return "eid_al_fitr"
    if hijri.month == 12 and 9 <= hijri.day <= 12:
        return "eid_al_adha"
    return ""


def labels(dates: pd.Series) -> pd.Series:
    """A label per date, "" for ordinary days and for missing dates."""
    days = pd.to_datetime(dates, errors="coerce")
    return days.map(lambda d: "" if pd.isna(d) else day_label(d.date())).astype(object)


def expand(names) -> set[str]:
    out: set[str] = set()
    for name in [names] if isinstance(names, str) else names:
        if name not in GROUPS:
            raise ValueError(f"unknown day group {name!r}; use {', '.join(GROUPS)}")
        out |= GROUPS[name]
    return out


def is_weekend(dates: pd.Series) -> pd.Series:
    """Friday and Saturday, the weekend in Qatar."""
    return pd.to_datetime(dates, errors="coerce").dt.day_of_week.isin([4, 5])
