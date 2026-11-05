"""Read CSV, JSON Lines, JSON, Parquet and Excel files into a DataFrame.

CSV and Excel cells are read as text, so a Qatar ID or a phone number keeps its
exact digits and "QAR 1,250.00" stays as it was written. Checks that need numbers
convert on their own.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


class ReadError(Exception):
    """The file is missing or not in a readable format."""


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise ReadError(f"file not found: {path}")
    suffix = path.suffix.lower()
    try:
        if suffix in (".csv", ".tsv", ".txt"):
            return pd.read_csv(
                path,
                sep="\t" if suffix == ".tsv" else ",",
                dtype=str,
                keep_default_na=False,
                na_values=[""],
                encoding="utf-8-sig",  # Excel saves Arabic CSVs with a BOM
            )
        if suffix in (".jsonl", ".ndjson"):
            return pd.read_json(path, lines=True, dtype=False, encoding="utf-8")
        if suffix == ".json":
            return pd.read_json(path, dtype=False, encoding="utf-8")
        if suffix == ".parquet":
            return pd.read_parquet(path)
        if suffix in (".xlsx", ".xls"):
            return pd.read_excel(path, dtype=str)
    except (ValueError, UnicodeDecodeError, ImportError) as exc:
        raise ReadError(f"could not read {path}: {exc}") from exc
    raise ReadError(f"unsupported file type {suffix!r}; use csv, tsv, jsonl, json, parquet or xlsx")
