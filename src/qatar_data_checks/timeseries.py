"""Checks for time-indexed data: gaps, repeated timestamps and outliers.

The outlier flag is the modified z-score of Iglewicz and Hoaglin (1993), "How to
Detect and Handle Outliers": z = 0.6745 (x - median) / MAD, flagged when |z| > 3.5.
Median and MAD are not pulled around by the outliers themselves, which is the
point of using them instead of mean and standard deviation.
"""
from __future__ import annotations

import pandas as pd

from . import qatar_calendar
from .checks import ConfigError, register, resolve_column
from .text import as_text, shorten

PERIODS = {"D": "D", "W": "W-SAT", "M": "M", "MS": "M", "Q": "Q", "Y": "Y"}  # W-SAT: weeks run Sunday to Saturday


def parse_dates(frame: pd.DataFrame, column=None, columns=None, format=None) -> pd.Series:
    """Dates from one column, or from several joined with "-", such as year and month."""
    if (column is None) == (columns is None):
        raise ConfigError("give either column or columns for the dates")
    if columns:
        names = [resolve_column(frame, c) for c in columns]
        text = frame[names].apply(lambda row: "-".join(as_text(v) for v in row), axis=1)
    else:
        text = frame[resolve_column(frame, column)]
        if pd.api.types.is_datetime64_any_dtype(text):
            return text
    return pd.to_datetime(text, format=format, errors="coerce")


def _groups(frame: pd.DataFrame, by) -> list[str]:
    return [resolve_column(frame, c) for c in ([by] if isinstance(by, str) else by or [])]


@register("missing_dates", describe="periods with no rows", table=True)
def missing_dates(frame, _, ctx, column=None, columns=None, format=None, freq="D", by=None):
    """Every period between the first and last date must have a row; with `by`,
    every group must have a row for every period in the whole range."""
    if freq not in PERIODS:
        raise ConfigError(f"freq must be one of {', '.join(PERIODS)}")
    dates = parse_dates(frame, column, columns, format)
    unparsed = int(dates.isna().sum())
    periods = dates.dropna().dt.to_period(PERIODS[freq])
    if periods.empty:
        return {"failed": unparsed, "total": len(frame), "message": "no dates could be read"}
    expected = pd.period_range(periods.min(), periods.max(), freq=PERIODS[freq])
    keys = _groups(frame, by)
    groups = frame.loc[periods.index].groupby(keys, dropna=False) if keys else [("", None)]
    missing, total = [], 0
    for name, part in groups:
        have = set(periods if part is None else periods.loc[part.index])
        total += len(expected)
        label = "" if part is None else ", ".join(map(as_text, name if isinstance(name, tuple) else (name,)))
        missing += [(str(p), label) for p in expected if p not in have]
    samples = [{"row": None, "value": p, "reason": f"missing for {g}" if g else "missing"} for p, g in missing]
    details = {"expected_periods": len(expected), "first": str(expected[0]), "last": str(expected[-1])}
    if unparsed:
        details["unreadable_dates"] = unparsed
    return {"failed": len(missing) + unparsed, "total": total, "samples": samples, "details": details}


@register("duplicate_timestamps", describe="timestamps that appear more than once", table=True)
def duplicate_timestamps(frame, _, ctx, column=None, columns=None, format=None, by=None):
    dates = parse_dates(frame, column, columns, format)
    key = pd.concat([frame[_groups(frame, by)], dates.rename("__date")], axis=1)
    bad = key.duplicated(keep=False) & dates.notna()
    samples = [
        {"row": int(i) + 1, "value": shorten(", ".join(as_text(v) for v in key.loc[i]))} for i in bad[bad].index[: ctx.samples]
    ]
    return {"failed": int(bad.sum()), "total": len(frame), "samples": samples}


def robust_z(values: pd.Series) -> pd.Series | None:
    """Modified z-scores, or None when the MAD is 0 and the score is undefined."""
    median = values.median()
    mad = (values - median).abs().median()
    if not mad:
        return None
    return 0.6745 * (values - median) / mad


@register("outliers", describe="values far from the median")
def outliers(values, frame, ctx, threshold=3.5, date=None, exclude=(), by=None, split_weekend=False):
    """Robust outliers. With `date`, days in `exclude` (ramadan, eid, eid_al_fitr,
    eid_al_adha, holidays) are left out of the baseline and never flagged, and
    `split_weekend` gives Friday and Saturday their own baseline."""
    numbers = pd.to_numeric(values.map(lambda v: as_text(v).strip()), errors="coerce")
    reasons = pd.Series("", index=values.index, dtype=object)
    reasons[numbers.isna()] = "not a number"
    keep = numbers.notna()
    keys: list[pd.Series] = [frame.loc[values.index, c] for c in _groups(frame, by)]
    details: dict[str, int] = {}
    if exclude or split_weekend:
        if date is None:
            raise ConfigError("outliers needs `date` to exclude days or split the weekend")
        days = parse_dates(frame.loc[values.index], column=date)
        if exclude:
            try:
                names = qatar_calendar.expand(exclude)
            except ValueError as exc:
                raise ConfigError(str(exc)) from None
            skipped = qatar_calendar.labels(days).isin(names)
            details["skipped_days"] = int((skipped & keep).sum())
            keep &= ~skipped
        if split_weekend:
            keys.append(qatar_calendar.is_weekend(days).map({True: "weekend", False: "weekday"}))
    grouped = numbers[keep].groupby([k[keep] for k in keys]) if keys else [(None, numbers[keep])]
    flat = []
    for _, part in grouped:
        z = robust_z(part)
        if z is None:
            flat.append(len(part))
            continue
        hits = z[z.abs() > threshold]
        reasons[hits.index] = hits.map(lambda s: f"robust z {s:+.1f}")
        details["high"] = details.get("high", 0) + int((hits > 0).sum())
        details["low"] = details.get("low", 0) + int((hits < 0).sum())
    if "not a number" in set(reasons):
        details["not a number"] = int((reasons == "not a number").sum())
    if flat:
        details["groups_with_zero_mad"] = len(flat)
    return reasons, details
