import json

import pytest

from qatar_data_checks.cli import main

CHECKS = """
dataset: customers
columns:
  رقم_الهوية: [not_null, unique, qatar_id]
  الهاتف:
    - qatar_phone: {severity: warn}
"""


@pytest.fixture
def files(tmp_path):
    data = tmp_path / "customers.csv"
    data.write_text("رقم_الهوية,الهاتف\n28763400001,+974 5512 3456\n30581800123,1234\n", encoding="utf-8-sig")
    checks = tmp_path / "checks.yaml"
    checks.write_text(CHECKS, encoding="utf-8")
    return data, checks


def test_exit_codes(files, tmp_path, capsys):
    data, checks = files
    assert main(["run", str(data), "-c", str(checks)]) == 0  # only a warning
    out = capsys.readouterr().out
    assert "WARN  الهاتف" in out and out.strip().endswith("4 checks: 3 passed, 0 failed, 1 warning")
    assert main(["run", str(data), "-c", str(checks), "--fail-on", "warn"]) == 1


def test_failure_and_reports(files, tmp_path, capsys):
    data, checks = files
    data.write_text("رقم_الهوية,الهاتف\n28763400001,55123456\n28763400001,55123457\n", encoding="utf-8")
    html, js = tmp_path / "r.html", tmp_path / "r.json"
    assert main(["run", str(data), "-c", str(checks), "--html", str(html), "--json", str(js)]) == 1
    assert json.loads(js.read_text(encoding="utf-8"))["summary"]["fail"] == 1
    assert "<html" in html.read_text(encoding="utf-8")


def test_json_to_stdout(files, capsys):
    data, checks = files
    main(["run", str(data), "-c", str(checks), "--json", "-"])
    assert json.loads(capsys.readouterr().out)["dataset"] == "customers"


def test_errors_exit_2(files, tmp_path, capsys):
    data, checks = files
    assert main(["run", str(tmp_path / "nope.csv"), "-c", str(checks)]) == 2
    bad = tmp_path / "bad.yaml"
    bad.write_text("columns:\n  a: [no_such_check]\n", encoding="utf-8")
    assert main(["run", str(data), "-c", str(bad)]) == 2
    assert "unknown check 'no_such_check'" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exc:
        main(["run", str(data)])
    assert exc.value.code == 2
