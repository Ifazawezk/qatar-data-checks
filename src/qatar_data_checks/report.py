"""Render a Report as text for a terminal, JSON for CI, or one HTML file."""
from __future__ import annotations

import html
import json

from .suite import Report

LABELS = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}


def _where(result) -> str:
    return result.column if result.column is not None else "(table)"


def _details(details: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in details.items())


def _sample(sample: dict) -> str:
    head = f"row {sample['row']}: " if sample.get("row") is not None else ""
    tail = f"  ({sample['reason']})" if sample.get("reason") else ""
    return f"{head}{sample['value'] or '(blank)'}{tail}"


def _summary(report: Report) -> str:
    c = report.counts
    warn = "warning" if c["warn"] == 1 else "warnings"
    return f"{len(report.results)} checks: {c['pass']} passed, {c['fail']} failed, {c['warn']} {warn}"


def _problem(result) -> str:
    if result.total <= 1 or result.failed == 0:
        return result.message
    return f"{result.failed} of {result.total}: {result.message}"


def to_text(report: Report, samples: int = 3) -> str:
    width = min(max([len(_where(r)) for r in report.results] + [7]), 28)
    check_width = min(max([len(r.check) for r in report.results] + [5]), 24)
    lines = [f"{report.dataset}: {report.rows} rows, {len(report.columns)} columns", ""]
    for r in report.results:
        line = f"{LABELS[r.status]}  {_where(r):<{width}}  {r.check:<{check_width}}"
        if not r.passed:
            line += f"  {_problem(r)}"
        lines.append(line.rstrip())
        if r.passed:
            continue
        pad = " " * 6
        if len(r.details) > 1:  # one reason is already clear from the samples
            lines.append(pad + _details(r.details))
        lines += [pad + _sample(s) for s in r.samples[:samples]]
    lines += ["", _summary(report)]
    return "\n".join(lines)


def to_json(report: Report) -> str:
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)


CSS = """
:root { --bg: #ffffff; --fg: #1d232a; --muted: #5b6672; --line: #dde2e7; --chip: #f2f4f6;
  --pass: #1a7f37; --fail: #c62828; --warn: #9a6700; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #14181c; --fg: #e6e9ec; --muted: #9aa5b1; --line: #2c333a; --chip: #1e242a;
    --pass: #4ac26b; --fail: #ff7b72; --warn: #e3b341; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, "Segoe UI", Tahoma, "Noto Naskh Arabic", "Geeza Pro", sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 24px 16px 48px; }
h1 { font-size: 1.4rem; margin: 0 0 4px; }
.meta { color: var(--muted); margin: 0 0 16px; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }
.chip { background: var(--chip); border-radius: 999px; padding: 2px 12px; }
.wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: start; vertical-align: top; padding: 8px; border-bottom: 1px solid var(--line); }
th { color: var(--muted); font-weight: 600; font-size: 0.85rem; }
.status { font-weight: 700; white-space: nowrap; }
.pass { color: var(--pass); } .fail { color: var(--fail); } .warn { color: var(--warn); }
.num { font-variant-numeric: tabular-nums; white-space: nowrap; }
.detail { color: var(--muted); font-size: 0.9rem; }
ul { margin: 4px 0 0; padding-inline-start: 18px; }
li { unicode-bidi: plaintext; }
"""


def to_html(report: Report, samples: int = 10) -> str:
    e = html.escape
    rows = []
    for r in report.results:
        body = [f"<div>{e(r.message)}</div>"]
        if r.details:
            body.append(f'<div class="detail" dir="auto">{e(_details(r.details))}</div>')
        if r.samples and not r.passed:
            items = "".join(f"<li>{e(_sample(s))}</li>" for s in r.samples[:samples])
            body.append(f"<ul>{items}</ul>")
        count = f"{r.failed} / {r.total}" if r.total else ""
        rows.append(
            f'<tr><td class="status {r.status}">{LABELS[r.status]}</td>'
            f'<td dir="auto">{e(_where(r))}</td><td>{e(r.check)}</td>'
            f'<td class="num">{count}</td><td>{"".join(body)}</td></tr>'
        )
    c = report.counts
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data checks: {e(report.dataset)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1 dir="auto">{e(report.dataset)}</h1>
<p class="meta">{report.rows} rows, {len(report.columns)} columns, checked {e(report.created)}</p>
<div class="chips"><span class="chip pass">{c['pass']} passed</span><span class="chip fail">{c['fail']} failed</span><span class="chip warn">{c['warn']} warnings</span></div>
<div class="wrap"><table>
<thead><tr><th>Status</th><th>Column</th><th>Check</th><th>Failed</th><th>Detail</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table></div>
</main>
</body>
</html>
"""
