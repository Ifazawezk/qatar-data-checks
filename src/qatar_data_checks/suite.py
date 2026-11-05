"""A suite is a list of checks, built in Python or loaded from YAML.

    dataset: orders
    table:
      - row_count: {min: 1}
      - rule: "shipped >= placed"
    columns:
      order_id: [not_null, unique]
      status:
        - allowed: [paid, refunded]
      المبلغ:
        - range: {min: 0, severity: warn}
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from .checks import REGISTRY, Check, ConfigError, Context, Result


@dataclass
class Report:
    dataset: str
    rows: int
    columns: list[str]
    results: list[Result]
    seconds: float = 0.0
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    @property
    def counts(self) -> dict[str, int]:
        counts = {"pass": 0, "fail": 0, "warn": 0}
        for r in self.results:
            counts[r.status] += 1
        return counts

    def exit_code(self, fail_on: str = "error") -> int:
        """1 when an error-level check failed, or any check with fail_on="warn"."""
        counts = self.counts
        if counts["fail"] or (fail_on == "warn" and counts["warn"]):
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "rows": self.rows,
            "columns": len(self.columns),
            "created": self.created,
            "seconds": round(self.seconds, 3),
            "summary": self.counts,
            "results": [r.to_dict() for r in self.results],
        }


class Suite:
    def __init__(self, checks: Iterable[Check] = (), name: str | None = None, config_dir: Path | None = None):
        self.checks = list(checks)
        self.name = name
        self.config_dir = config_dir

    def add(self, kind: str, column: str | None = None, severity: str = "error", name: str | None = None, **params) -> "Suite":
        self.checks.append(Check(kind, column, params, severity, name))
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Suite":
        path = Path(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ConfigError(f"check file not found: {path}") from None
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path} is not valid YAML: {exc}") from None
        return cls.from_dict(data or {}, config_dir=path.parent)

    @classmethod
    def from_dict(cls, data: dict, config_dir: Path | None = None) -> "Suite":
        if not isinstance(data, dict):
            raise ConfigError("a check file is a mapping with 'columns' and/or 'table'")
        unknown = set(data) - {"dataset", "columns", "table"}
        if unknown:
            raise ConfigError(f"unknown top-level keys: {', '.join(sorted(map(str, unknown)))}")
        checks = [_parse(item, None) for item in data.get("table") or []]
        for column, items in (data.get("columns") or {}).items():
            if isinstance(items, (str, dict)):
                items = [items]
            checks += [_parse(item, str(column)) for item in items or []]
        return cls(checks, name=data.get("dataset"), config_dir=config_dir)

    def run(self, frame: pd.DataFrame, dataset: str | None = None, base_dir: Path | None = None, samples: int = 5) -> Report:
        start = time.perf_counter()
        frame = frame.reset_index(drop=True)
        ctx = Context(base_dir=base_dir, config_dir=self.config_dir, samples=samples)
        results = [check.run(frame, ctx) for check in self.checks]
        return Report(
            dataset=dataset or self.name or "data",
            rows=len(frame),
            columns=[str(c) for c in frame.columns],
            results=results,
            seconds=time.perf_counter() - start,
        )


def _parse(item: Any, column: str | None) -> Check:
    if isinstance(item, str):
        kind, params = item, {}
    elif isinstance(item, dict) and len(item) == 1:
        kind, params = next(iter(item.items()))
    else:
        raise ConfigError(f"each check is a name or a single-key mapping, got {item!r}")
    spec = REGISTRY.get(kind)
    if spec is None:
        raise ConfigError(f"unknown check {kind!r}; known checks: {', '.join(sorted(REGISTRY))}")
    if params is None:
        params = {}
    elif not isinstance(params, dict):
        if spec.main is None:
            raise ConfigError(f"{kind} takes named parameters, for example {kind}: {{...}}")
        params = {spec.main: params}
    params = dict(params)
    severity = params.pop("severity", "error")
    label = params.pop("name", None)
    return Check(kind, column, params, severity, label)
