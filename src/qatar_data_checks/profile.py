"""Profile a dataset and suggest a starting check file.

The suggestions describe the data as it is: observed ranges, observed label sets,
the Qatar formats most values already follow. Review them before using them in CI;
a profile of bad data suggests checks that accept bad data.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

import pandas as pd
import yaml

from .arabic import issue_counts, script_share
from .checks import blank
from .qatar import phone_kind, qatar_id_problem
from .text import as_text, ungroup

ID_NAME = re.compile(r"(^|_)(id|key|code|uuid)$|^id_|رقم|معرف", re.IGNORECASE)
MONEY_NAME = re.compile(r"qar|qr$|price|amount|riyal|cost|revenue|sales|total|سعر|مبلغ|ريال|قيمة|مبيعات|مشتريات|إجمالي", re.IGNORECASE)
INTEGER = re.compile(r"-?(0|[1-9][0-9]*)")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?")
SHARE = 0.9  # share of values that must follow a format before it is suggested


@dataclass
class ColumnProfile:
    name: str
    kind: str
    count: int
    nulls: int
    distinct: int
    low: object = None
    high: object = None
    decimals: int = 0
    notes: list[str] = field(default_factory=list)
    checks: list = field(default_factory=list)


def _kind(values: pd.Series) -> str:
    if values.empty:
        return "empty"
    if values.map(lambda v: isinstance(v, (list, dict))).any():
        return "nested"
    if pd.api.types.is_bool_dtype(values):
        return "boolean"
    if pd.api.types.is_integer_dtype(values):
        return "integer"
    if pd.api.types.is_float_dtype(values):
        return "number"
    text = _ungroup(values.map(lambda v: as_text(v).strip()))
    if text.str.lower().isin(["true", "false"]).all():
        return "boolean"
    if text.str.fullmatch(INTEGER).all():
        return "integer"
    if pd.to_numeric(text, errors="coerce").notna().all() and not text.str.match(r"-?0[0-9]").any():
        return "number"
    if text.str.fullmatch(DATE).all() and pd.to_datetime(text, errors="coerce").notna().all():
        return "date"
    return "text"


def _ungroup(text: pd.Series) -> pd.Series:
    return text.map(ungroup)


def _decimals(values: pd.Series) -> int:
    text = values.map(lambda v: as_text(v).strip())
    places = text.str.extract(r"\.([0-9]+)$")[0].dropna().str.len()
    return int(places.max()) if not places.empty else 0


def _share(values: pd.Series, test) -> float:
    return float(values.map(test).mean()) if len(values) else 0.0


def profile_column(name: str, column: pd.Series) -> ColumnProfile:
    present = column[~blank(column)]
    kind = _kind(present)
    distinct = int(present.map(as_text).nunique())
    p = ColumnProfile(str(name), kind, len(column), len(column) - len(present), distinct)
    if kind in ("empty", "nested"):
        return p
    if p.nulls == 0:
        p.checks.append("not_null")
    text = present.map(lambda v: as_text(v).strip())
    is_qid = _share(present, lambda v: qatar_id_problem(v) == "") >= SHARE
    phones = present.map(lambda v: phone_kind(v)[0])
    is_phone = not is_qid and phones.notna().mean() >= SHARE
    code_like = kind == "text" and not is_phone and not text.str.contains(r"\s").any() and text.str.len().mean() <= 20
    if distinct == len(present) > 1 and (ID_NAME.search(p.name) or is_qid or code_like):
        p.checks.append("unique")
        p.notes.append("likely id")
    if is_qid:
        p.notes.append("Qatar ID format")
        p.checks.append("qatar_id")
        return p
    if is_phone:
        kinds = set(phones.dropna())
        p.notes.append("Qatar phone format")
        p.checks.append({"qatar_phone": {"kind": kinds.pop()}} if len(kinds) == 1 else "qatar_phone")
        return p
    if kind in ("integer", "number"):
        numbers = pd.to_numeric(_ungroup(text))
        p.low, p.high = numbers.min().item(), numbers.max().item()
        p.decimals = _decimals(present)
        p.checks.append({"range": {"min": p.low, "max": p.high}})
        if MONEY_NAME.search(p.name):
            p.notes.append("looks like money")
            options = {"decimals": p.decimals} if p.decimals > 2 else {}
            if p.low < 0:
                options["negative"] = True
            p.checks.append({"qar_amount": options} if options else "qar_amount")
        return p
    if kind == "date":
        dates = pd.to_datetime(text)
        p.low, p.high = dates.min().date().isoformat(), dates.max().date().isoformat()
        p.notes.append(f"dates {p.low} to {p.high}")
        return p
    if kind in ("text", "boolean") and distinct <= 20 and distinct <= max(2, len(present) // 2):
        p.checks.append({"allowed": sorted(text.unique().tolist())})
    arabic = text.map(lambda v: script_share(v, "arabic")).dropna()
    if len(arabic) and arabic.mean() >= 0.5:
        p.notes.append("Arabic")
        p.checks.append({"script": {"expect": "arabic"}})
        issues = issue_counts(present)
        if issues:
            p.notes.append(", ".join(f"{k} {v}" for k, v in issues.items()))
        p.checks.append({"arabic_text": {"severity": "warn"}})
    return p


def profile(frame: pd.DataFrame) -> list[ColumnProfile]:
    return [profile_column(name, frame[name]) for name in frame.columns]


def suggest_yaml(frame: pd.DataFrame, dataset: str) -> str:
    profiles = profile(frame)
    width = max([len(p.name) for p in profiles] + [6])
    header = [
        f"# Suggested by qdc profile from {dataset} on {dt.date.today().isoformat()}: {len(frame)} rows, {len(frame.columns)} columns.",
        "# Ranges and label sets describe the data as it is. A format check is suggested when 90% of",
        "# values follow it, so it flags the rest. Review every check before relying on it.",
        "#",
        f"# {'column':<{width}}  {'type':<8} {'nulls':>6} {'distinct':>8}  notes",
    ]
    for p in profiles:
        rate = "-" if not p.count else "<1%" if 0 < p.nulls / p.count < 0.01 else f"{p.nulls / p.count:.0%}"
        header.append(f"# {p.name:<{width}}  {p.kind:<8} {rate:>6} {p.distinct:>8}  {'; '.join(p.notes)}".rstrip())
    body = {
        "dataset": dataset,
        "table": [{"row_count": {"min": 1}}],
        "columns": {p.name: p.checks for p in profiles if p.checks},
    }
    text = yaml.safe_dump(body, allow_unicode=True, sort_keys=False, default_flow_style=None, width=100)
    return "\n".join(header) + "\n\n" + text
