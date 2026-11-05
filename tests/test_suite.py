import pandas as pd
import pytest

from qatar_data_checks import ConfigError, Suite

YAML = """
dataset: orders
table:
  - row_count: {min: 1}
  - rule: {expr: "`الكمية` > 0", name: positive quantity}
columns:
  رقم_الطلب: [not_null, unique]
  الحالة:
    - allowed: [مدفوع, مسترد]
  الكمية:
    - range: {min: 1, max: 10, severity: warn}
"""


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "رقم_الطلب": ["1", "2", "2"],
            "الحالة": ["مدفوع", "مسترد", "ملغي"],
            "الكمية": ["3", "0", "12"],
        }
    )


def test_yaml_with_arabic_names(tmp_path, df):
    path = tmp_path / "checks.yaml"
    path.write_text(YAML, encoding="utf-8")
    report = Suite.from_yaml(path).run(df)
    by_name = {(r.column, r.check): r for r in report.results}
    assert report.dataset == "orders" and len(report.results) == 6
    assert by_name[(None, "positive quantity")].failed == 1
    assert by_name[("رقم_الطلب", "unique")].failed == 2
    assert by_name[("الحالة", "allowed")].samples[0]["value"] == "ملغي"
    assert by_name[("الكمية", "range")].status == "warn"
    assert report.counts == {"pass": 2, "fail": 3, "warn": 1}
    assert report.exit_code() == 1


def test_warnings_only_fail_when_asked(df):
    suite = Suite().add("range", "الكمية", min=0, max=10, severity="warn")
    report = suite.run(df)
    assert report.exit_code() == 0
    assert report.exit_code(fail_on="warn") == 1


def test_python_api_matches_yaml(df):
    suite = Suite(name="orders").add("unique", "رقم_الطلب").add("rule", expr="`الكمية` > 0")
    assert [r.failed for r in suite.run(df).results] == [2, 1]


@pytest.mark.parametrize(
    "data",
    [
        {"colums": {}},
        {"columns": {"a": [{"range": 5}]}},
        {"columns": {"a": [{"not_a_check": {}}]}},
        {"columns": {"a": [{"range": {"min": 1}, "unique": None}]}},
        {"table": ["unique"]},
    ],
)
def test_config_errors(data):
    with pytest.raises(ConfigError):
        Suite.from_dict(data)


def test_bad_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("columns: [a\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        Suite.from_yaml(path)
    with pytest.raises(ConfigError):
        Suite.from_yaml(tmp_path / "missing.yaml")


def test_report_dict(df):
    report = Suite().add("not_null", "الحالة").run(df, dataset="orders.csv")
    out = report.to_dict()
    assert out["summary"] == {"pass": 1, "fail": 0, "warn": 0} and out["rows"] == 3
