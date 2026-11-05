"""Command line entry point: qdc run, qdc profile, qdc drift."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .checks import ConfigError
from .drift import compare
from .profile import suggest_yaml
from .readers import ReadError, read_table
from .report import to_html, to_json, to_text
from .suite import Suite

EXIT_OK, EXIT_FAILED, EXIT_ERROR = 0, 1, 2


def _utf8_output() -> None:
    """Windows consoles default to a code page that cannot print Arabic."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def cmd_run(args) -> int:
    suite = Suite.from_yaml(args.checks)
    data = Path(args.data)
    report = suite.run(read_table(data), dataset=suite.name or data.name, base_dir=data.parent, samples=max(args.samples, 10))
    if args.json == "-":
        print(to_json(report))
    else:
        print(to_text(report, samples=args.samples))
        if args.json:
            _write(args.json, to_json(report) + "\n")
    if args.html:
        _write(args.html, to_html(report))
    return report.exit_code(args.fail_on)


def cmd_profile(args) -> int:
    data = Path(args.data)
    text = suggest_yaml(read_table(data), data.name)
    if args.output:
        _write(args.output, text)
        print(f"wrote {args.output}")
    else:
        print(text, end="")
    return EXIT_OK


def cmd_drift(args) -> int:
    old, new = Path(args.reference), Path(args.current)
    columns = [c.strip() for c in args.columns.split(",")] if args.columns else None
    report = compare(read_table(old), read_table(new), columns=columns, bins=args.bins,
                     moderate=args.moderate, major=args.major)
    if args.json == "-":
        print(report.to_json())
    else:
        print(report.to_text(old.name, new.name))
        if args.json:
            _write(args.json, report.to_json() + "\n")
    return report.exit_code(args.fail_on)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qdc", description="Data quality checks for CSV, JSON Lines, Parquet and Excel files.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a check file against a dataset")
    run.add_argument("data", help="csv, tsv, jsonl, json, parquet or xlsx file")
    run.add_argument("-c", "--checks", required=True, help="YAML check file")
    run.add_argument("--json", metavar="PATH", help="write the JSON report to PATH; - prints it instead of the text report")
    run.add_argument("--html", metavar="PATH", help="write a self-contained HTML report to PATH")
    run.add_argument("--fail-on", choices=("error", "warn"), default="error", help="exit 1 on failed errors (default) or on warnings too")
    run.add_argument("--samples", type=int, default=3, help="failing values to show per check (default 3)")
    run.set_defaults(func=cmd_run)

    prof = sub.add_parser("profile", help="profile a dataset and suggest a starting check file")
    prof.add_argument("data")
    prof.add_argument("-o", "--output", metavar="PATH", help="write the YAML to PATH instead of printing it")
    prof.set_defaults(func=cmd_profile)

    drift = sub.add_parser("drift", help="compare two versions of a dataset")
    drift.add_argument("reference", help="the older or expected version")
    drift.add_argument("current", help="the version to check")
    drift.add_argument("--columns", help="comma separated columns to compare (default: all shared columns)")
    drift.add_argument("--bins", type=int, default=10, help="quantile bins for numeric PSI (default 10)")
    drift.add_argument("--moderate", type=float, default=0.1, help="PSI from which a shift is moderate (default 0.1)")
    drift.add_argument("--major", type=float, default=0.25, help="PSI from which a shift is major (default 0.25)")
    drift.add_argument("--fail-on", choices=("major", "moderate"), default="major",
                       help="exit 1 on major shifts (default) or on moderate ones too")
    drift.add_argument("--json", metavar="PATH", help="write the JSON report to PATH; - prints it instead")
    drift.set_defaults(func=cmd_drift)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, ReadError) as exc:
        print(f"qdc: error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
