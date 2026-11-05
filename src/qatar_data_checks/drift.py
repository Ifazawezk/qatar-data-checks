"""Compare two versions of a dataset column by column.

Numeric columns get the population stability index (PSI) over deciles of the
reference data and a two-sample Kolmogorov-Smirnov test. Categorical columns get
PSI over categories and a chi-square test of homogeneity.

PSI = sum((actual - expected) * ln(actual / expected)) over bins, which is the
symmetric Kullback-Leibler divergence. The usual reading, from Siddiqi (2006),
"Credit Risk Scorecards", is below 0.1 stable, 0.1 to 0.25 a moderate shift and
above 0.25 a major shift. Status here follows PSI only: with thousands of rows the
test p-values fall below 0.01 for shifts too small to matter, so they are shown
as supporting evidence.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .checks import blank, typed
from .text import as_text

EPS = 1e-4  # stands in for an empty bin, so the logarithm stays finite
FEW = 10


def psi(expected, actual) -> float:
    e = np.asarray(expected, dtype=float)
    a = np.asarray(actual, dtype=float)
    e = np.clip(e / e.sum(), EPS, None)
    a = np.clip(a / a.sum(), EPS, None)
    return float(np.sum((a - e) * np.log(a / e)))


def numeric_bins(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> tuple[np.ndarray, np.ndarray]:
    edges = np.unique(np.quantile(reference, np.linspace(0, 1, bins + 1)[1:-1]))
    edges = np.concatenate([[-np.inf], edges, [np.inf]])
    return np.histogram(reference, edges)[0], np.histogram(current, edges)[0]


def category_counts(reference: pd.Series, current: pd.Series, limit: int = 20) -> pd.DataFrame:
    """Counts per category in both versions; categories past the most common
    `limit` are pooled as (other)."""
    top = pd.concat([reference, current]).value_counts().index[:limit]
    fold = lambda s: s.where(s.isin(top), "(other)")  # noqa: E731
    table = pd.DataFrame({"reference": fold(reference).value_counts(), "current": fold(current).value_counts()})
    return table.fillna(0)


@dataclass
class ColumnDrift:
    column: str
    kind: str
    psi: float | None
    test: str
    statistic: float | None
    p_value: float | None
    null_rate: tuple[float, float]
    status: str
    note: str = ""


def status_of(value: float | None, moderate: float, major: float) -> str:
    if value is None:
        return "skipped"
    return "major" if value >= major else "moderate" if value >= moderate else "stable"


def compare(reference: pd.DataFrame, current: pd.DataFrame, columns=None, bins: int = 10,
            moderate: float = 0.1, major: float = 0.25, max_categories: int = 20) -> "DriftReport":
    ref, cur = typed(reference), typed(current)
    shared = [c for c in ref.columns if c in cur.columns]
    names = [c for c in (columns or shared) if c in shared]
    out = []
    for name in names:
        a, b = ref[name], cur[name]
        rates = (round(float(blank(a).mean()), 4), round(float(blank(b).mean()), 4))
        a, b = a[~blank(a)], b[~blank(b)]
        if a.empty or b.empty:
            out.append(ColumnDrift(str(name), "-", None, "-", None, None, rates, "skipped", "no values in one version"))
            continue
        numeric = pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b) and not pd.api.types.is_bool_dtype(a)
        if numeric and a.nunique() > FEW:  # a handful of numbers, such as a year, is compared as categories
            x, y = a.to_numpy(float), b.to_numpy(float)
            value = psi(*numeric_bins(x, y, bins))
            ks = stats.ks_2samp(x, y)
            out.append(ColumnDrift(str(name), "numeric", value, "ks", float(ks.statistic), float(ks.pvalue), rates,
                                   status_of(value, moderate, major)))
            continue
        a, b = a.map(as_text), b.map(as_text)
        if a.nunique() > max(50, 0.5 * len(a)):
            out.append(ColumnDrift(str(name), "text", None, "-", None, None, rates, "skipped", "mostly unique values, likely an id or free text"))
            continue
        table = category_counts(a, b, max_categories)
        value = psi(table["reference"], table["current"])
        if len(table) > 1:
            chi2, p, _, _ = stats.chi2_contingency(table.T.to_numpy(), correction=False)
        else:
            chi2, p = 0.0, 1.0
        out.append(ColumnDrift(str(name), "categorical", value, "chi2", float(chi2), float(p), rates,
                               status_of(value, moderate, major)))
    only = {
        "reference": [str(c) for c in ref.columns if c not in cur.columns],
        "current": [str(c) for c in cur.columns if c not in ref.columns],
    }
    return DriftReport(len(reference), len(current), out, only, moderate, major)


@dataclass
class DriftReport:
    reference_rows: int
    current_rows: int
    columns: list[ColumnDrift]
    only_in: dict[str, list[str]]
    moderate: float
    major: float

    def exit_code(self, fail_on: str = "major") -> int:
        bad = {"major"} if fail_on == "major" else {"major", "moderate"}
        return int(any(c.status in bad for c in self.columns))

    def to_dict(self) -> dict:
        return {
            "reference_rows": self.reference_rows,
            "current_rows": self.current_rows,
            "thresholds": {"moderate": self.moderate, "major": self.major},
            "only_in": self.only_in,
            "columns": [asdict(c) for c in self.columns],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_text(self, reference: str = "reference", current: str = "current") -> str:
        width = max([len(c.column) for c in self.columns] + [6])
        lines = [
            f"{reference}: {self.reference_rows} rows  ->  {current}: {self.current_rows} rows",
            f"PSI below {self.moderate} is stable, {self.moderate} to {self.major} moderate, {self.major} or more major",
            "",
            f"{'column':<{width}}  {'type':<11}  {'PSI':>6}  {'test':<4}  {'stat':>7}  {'p':>9}  {'nulls':>12}  status",
        ]
        for c in self.columns:
            psi_text = f"{c.psi:.3f}" if c.psi is not None else "-"
            stat = f"{c.statistic:.3f}" if c.statistic is not None else "-"
            p = f"{c.p_value:.2g}" if c.p_value is not None else "-"
            nulls = f"{c.null_rate[0]:.0%} -> {c.null_rate[1]:.0%}"
            lines.append(f"{c.column:<{width}}  {c.kind:<11}  {psi_text:>6}  {c.test:<4}  {stat:>7}  {p:>9}  {nulls:>12}  {c.status}"
                         + (f" ({c.note})" if c.note else ""))
        for side, cols in self.only_in.items():
            if cols:
                lines.append(f"only in {side}: {', '.join(cols)}")
        counts = pd.Series([c.status for c in self.columns]).value_counts()
        summary = ", ".join(f"{counts.get(s, 0)} {s}" for s in ("stable", "moderate", "major", "skipped") if counts.get(s, 0))
        lines += ["", f"{len(self.columns)} columns: {summary}"]
        return "\n".join(lines)
