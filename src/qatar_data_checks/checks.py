"""The check model and the general checks.

A column check gets the column's values (blank cells removed, except for not_null)
and returns a boolean Series marking bad values, or a Series of reasons where an
empty string means the value is fine. A table check gets the whole DataFrame.
"""
from __future__ import annotations

import datetime as dt
import difflib
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from .readers import read_table
from .text import as_text, canonical, shorten

SEVERITIES = ("error", "warn")


class ConfigError(ValueError):
    """A check file or a check's parameters are wrong."""


class MissingColumn(LookupError):
    pass


@dataclass
class Result:
    check: str
    column: str | None
    severity: str
    passed: bool
    failed: int = 0
    total: int = 0
    message: str = ""
    samples: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        if self.passed:
            return "pass"
        return "fail" if self.severity == "error" else "warn"

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "column": self.column,
            "status": self.status,
            "severity": self.severity,
            "failed": self.failed,
            "total": self.total,
            "message": self.message,
            "details": self.details,
            "samples": self.samples,
        }


@dataclass
class Context:
    """What a check may need beyond the data: where to find referenced files."""

    base_dir: Path | None = None
    config_dir: Path | None = None
    samples: int = 5
    _typed: dict[int, pd.DataFrame] = field(default_factory=dict)
    _refs: dict[tuple, set] = field(default_factory=dict)

    def typed(self, frame: pd.DataFrame) -> pd.DataFrame:
        if id(frame) not in self._typed:
            self._typed[id(frame)] = typed(frame)
        return self._typed[id(frame)]

    def find(self, path: str) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        for folder in (self.base_dir, self.config_dir, Path.cwd()):
            if folder is not None and (folder / candidate).is_file():
                return folder / candidate
        return candidate


@dataclass
class Spec:
    fn: Callable
    table: bool
    main: str | None
    describe: str
    nulls: bool


REGISTRY: dict[str, Spec] = {}


def register(name: str, *, describe: str, table: bool = False, main: str | None = None, nulls: bool = False):
    """Add a check. `main` is the parameter a bare value fills in YAML, as in
    `regex: "[0-9]+"`. `nulls=True` passes blank cells to the check as well."""

    def deco(fn: Callable) -> Callable:
        REGISTRY[name] = Spec(fn, table, main, describe, nulls)
        return fn

    return deco


@dataclass
class Check:
    kind: str
    column: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"
    label: str | None = None

    def __post_init__(self) -> None:
        spec = REGISTRY.get(self.kind)
        if spec is None:
            raise ConfigError(f"unknown check {self.kind!r}; known checks: {', '.join(sorted(REGISTRY))}")
        if self.severity not in SEVERITIES:
            raise ConfigError(f"severity must be error or warn, not {self.severity!r}")
        if spec.table and self.column is not None:
            raise ConfigError(f"{self.kind} is a table check and goes under 'table', not under a column")
        if not spec.table and self.column is None:
            raise ConfigError(f"{self.kind} needs a column")
        try:
            inspect.signature(spec.fn).bind(None, None, None, **self.params)
        except TypeError as exc:
            raise ConfigError(f"{self.kind}: {exc}") from None

    @property
    def name(self) -> str:
        return self.label or self.kind

    def run(self, frame: pd.DataFrame, ctx: Context | None = None) -> Result:
        ctx = ctx or Context()
        spec = REGISTRY[self.kind]
        result = Result(self.name, self.column, self.severity, passed=True, message=spec.describe)
        try:
            if spec.table:
                values = None
                out = spec.fn(frame, None, ctx, **self.params)
            else:
                values = frame[resolve_column(frame, self.column)]
                if not spec.nulls:
                    values = values[~blank(values)]
                out = spec.fn(values, frame, ctx, **self.params)
        except MissingColumn as exc:
            result.passed, result.message = False, str(exc)
            return result
        details: dict[str, Any] = {}
        own_details = isinstance(out, tuple)  # (reasons, details): the check counts for itself
        if own_details:
            out, details = out
        if isinstance(out, dict):  # a table check that counted for itself
            result.failed, result.total = out["failed"], out["total"]
            result.samples = out.get("samples", [])[: ctx.samples]
            result.message = out.get("message", result.message)
            details = {**out.get("details", {}), **details}
        else:
            source = values if values is not None else frame
            _fill_from_series(result, out, source, ctx)
            if out.dtype == object and not own_details:
                counts = out[out.astype(bool)].str.split("; ").explode().value_counts()
                details = {**{k: int(v) for k, v in counts.items()}, **details}
        result.details = details
        result.passed = result.failed == 0
        return result


def _fill_from_series(result: Result, out: pd.Series, source, ctx: Context) -> None:
    reasons = out if out.dtype == object else None
    bad = out.astype(bool) if reasons is not None else out.fillna(False).astype(bool)
    result.total = len(out)
    result.failed = int(bad.sum())
    for idx in bad[bad].index[: ctx.samples]:
        value = source.loc[idx] if isinstance(source, pd.Series) else _row_preview(source, idx)
        sample = {"row": int(idx) + 1, "value": shorten(as_text(value))}
        if reasons is not None:
            sample["reason"] = reasons.loc[idx]
        result.samples.append(sample)


def _row_preview(frame: pd.DataFrame, idx, columns=None) -> str:
    columns = columns or list(frame.columns)[:4]
    return ", ".join(f"{c}={as_text(frame.at[idx, c])}" for c in columns)


# helpers used by checks in other modules too


def blank(values: pd.Series) -> pd.Series:
    """Missing cells, blank strings and empty lists."""

    def empty(v) -> bool:
        if isinstance(v, str):
            return not v.strip()
        if isinstance(v, (list, dict, tuple)):
            return len(v) == 0
        return False

    missing = values.isna()
    if is_text(values):
        missing = missing | values.map(empty).astype(bool)
    return missing


def is_text(values: pd.Series) -> bool:
    """Object or string dtype; pandas 3 reads text as a string dtype, not object."""
    return values.dtype == object or pd.api.types.is_string_dtype(values)


def resolve_column(frame: pd.DataFrame, name: str) -> str:
    """Find a column by exact name, then by its canonical form, so a header saved
    with a BOM, tatweel or a different Unicode normalisation still matches."""
    if name in frame.columns:
        return name
    by_canonical = {canonical(str(c)): c for c in frame.columns}
    if canonical(name) in by_canonical:
        return by_canonical[canonical(name)]
    close = difflib.get_close_matches(name, [str(c) for c in frame.columns], n=3)
    hint = f"; did you mean {', '.join(close)}?" if close else ""
    raise MissingColumn(f"column {name!r} not found{hint}")


def columns_of(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def hashable(values: pd.Series) -> pd.Series:
    if values.map(lambda v: isinstance(v, (list, dict))).any():
        return values.map(as_text)
    return values


def typed(frame: pd.DataFrame) -> pd.DataFrame:
    """A copy where text columns that hold only numbers become numeric.
    Text with leading zeros, such as "004", stays text."""
    out = frame.copy()
    for col in out.columns:
        series = out[col]
        if not is_text(series):
            continue
        present = series[~blank(series)]
        if present.empty or not present.map(lambda v: isinstance(v, str)).all():
            continue
        stripped = present.str.strip()
        if stripped.str.match(r"^-?0[0-9]").any():
            continue
        numbers = pd.to_numeric(stripped, errors="coerce")
        if numbers.notna().all():
            out[col] = pd.to_numeric(series.where(~blank(series)).str.strip(), errors="coerce")
    return out


def _bound(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return pd.Timestamp(value)
    return value


# general checks


@register("not_null", describe="missing or blank values", nulls=True)
def not_null(values, frame, ctx):
    return blank(values)


@register("unique", describe="values that appear more than once")
def unique(values, frame, ctx, with_columns=None, normalize=False):
    """Every row involved in a duplicate fails. `normalize` compares canonical
    forms, so Arabic text that differs only in invisible marks counts as equal."""
    key = hashable(values)
    if normalize:
        key = key.map(lambda v: canonical(as_text(v)))
    parts = [key] + [hashable(frame.loc[values.index, resolve_column(frame, c)]) for c in columns_of(with_columns)]
    return pd.concat(parts, axis=1).duplicated(keep=False)


@register("range", describe="values outside the range")
def value_range(values, frame, ctx, min=None, max=None, exclusive=False):
    low, high = _bound(min), _bound(max)
    if isinstance(low, pd.Timestamp) or isinstance(high, pd.Timestamp):
        numbers = pd.to_datetime(values.map(as_text), errors="coerce")
        kind = "not a date"
    else:
        numbers = pd.to_numeric(values.map(lambda v: as_text(v).strip()), errors="coerce")
        kind = "not a number"
    reasons = pd.Series("", index=values.index, dtype=object)
    reasons[numbers.isna()] = kind
    if low is not None:
        below = numbers <= low if exclusive else numbers < low
        reasons[below.fillna(False)] = f"below {min}"
    if high is not None:
        above = numbers >= high if exclusive else numbers > high
        reasons[above.fillna(False)] = f"above {max}"
    return reasons


@register("allowed", describe="values outside the allowed set", main="values")
def allowed_values(column, frame, ctx, values, normalize=False):
    fold = (lambda v: canonical(as_text(v))) if normalize else as_text
    permitted = {fold(v) for v in values}
    return ~column.map(fold).isin(permitted)


@register("regex", describe="values that do not match the pattern", main="pattern")
def regex(values, frame, ctx, pattern, ascii=False):
    """Whole-value match. Python's \\d also matches Arabic-Indic digits; pass
    ascii: true, or write [0-9], when only 0-9 are valid."""
    compiled = re.compile(pattern, re.ASCII if ascii else 0)
    return ~values.map(lambda v: compiled.fullmatch(as_text(v)) is not None).astype(bool)


@register("length", describe="values with the wrong length")
def length(values, frame, ctx, min=None, max=None):
    sizes = values.map(lambda v: len(as_text(v).strip()))
    reasons = pd.Series("", index=values.index, dtype=object)
    if min is not None:
        reasons[sizes < min] = f"shorter than {min} characters"
    if max is not None:
        reasons[sizes > max] = f"longer than {max} characters"
    return reasons


@register("references", describe="values not found in the referenced file", main="path")
def references(values, frame, ctx, path, column=None):
    """Like a foreign key: every value must exist in a column of another file.
    A relative path is looked up next to the data, then next to the check file."""
    target = ctx.find(path)
    key = (str(target), column or values.name)
    if key not in ctx._refs:
        other = read_table(target)
        ctx._refs[key] = set(other[resolve_column(other, key[1])].map(as_text))
    return ~values.map(as_text).isin(ctx._refs[key])


@register("one_value_per", describe="keys that map to more than one value", main="key")
def one_value_per(values, frame, ctx, key):
    """Each key has a single value in this column, for example one label per
    comment text. Every row of a conflicting key fails."""
    keys = [resolve_column(frame, k) for k in columns_of(key)]
    data = pd.concat([hashable(frame.loc[values.index, k]) for k in keys] + [hashable(values)], axis=1)
    data.columns = [f"k{i}" for i in range(len(keys))] + ["v"]
    counts = data.groupby([f"k{i}" for i in range(len(keys))], dropna=False)["v"].transform("nunique")
    reasons = pd.Series("", index=values.index, dtype=object)
    reasons[counts > 1] = counts[counts > 1].map(lambda n: f"{n} different values for the same {', '.join(keys)}")
    return reasons


@register("row_count", describe="row count outside the range", table=True)
def row_count(frame, _, ctx, min=None, max=None):
    rows = len(frame)
    bad = (min is not None and rows < min) or (max is not None and rows > max)
    limits = " and ".join(p for p in (f"at least {min}" if min is not None else "", f"at most {max}" if max is not None else "") if p)
    return {"failed": int(bad), "total": 1, "message": f"{rows} rows, expected {limits}" if bad else f"{rows} rows"}


@register("rule", describe="rows that break the rule", table=True, main="expr")
def rule(frame, _, ctx, expr, where=None):
    """A pandas expression over columns, such as `end_date >= start_date`.
    Names that are not plain identifiers go in backticks. Rows where the rule is
    False or cannot be decided (a missing value) fail."""
    data = ctx.typed(frame)

    def evaluate(text: str) -> pd.Series:
        try:
            out = data.eval(text, engine="python")
        except SyntaxError as exc:
            raise ConfigError(f"rule {text!r} is not a valid expression: {exc.msg}") from None
        except Exception as exc:  # an unknown column or a type clash is a data problem
            raise MissingColumn(f"rule {text!r} could not run: {exc}") from None
        if not isinstance(out, pd.Series):
            raise ConfigError(f"rule {text!r} must give one True or False per row")
        return out.astype("boolean").fillna(False).astype(bool)

    rows = evaluate(where) if where else pd.Series(True, index=data.index)
    bad = ~evaluate(expr) & rows
    used = [c for c in data.columns if str(c) in expr] or list(data.columns)[:4]
    samples = [{"row": int(i) + 1, "value": shorten(_row_preview(frame, i, used))} for i in bad[bad].index[: ctx.samples]]
    return {"failed": int(bad.sum()), "total": int(rows.sum()), "samples": samples, "message": f"rows where {expr} is not true"}
