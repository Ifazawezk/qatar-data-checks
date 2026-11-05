import json

import pandas as pd
import pytest

from qatar_data_checks import Check, ConfigError, Context, read_table


@pytest.fixture
def orders():
    return pd.DataFrame(
        {
            "order_id": ["A1", "A2", "A2", "A4", None],
            "status": ["paid", "paid", "refunded", "lost", "paid"],
            "amount": ["120.5", "80", "-5", "abc", "60"],
            "placed": ["2026-01-02", "2026-01-03", "2026-01-03", "2026-01-05", "2026-01-06"],
            "shipped": ["2026-01-03", "2026-01-02", "2026-01-04", None, "2026-01-07"],
        }
    )


def run(df, kind, column=None, **params):
    return Check(kind, column, params).run(df, Context())


def test_not_null_counts_blank_strings(orders):
    df = orders.copy()
    df.loc[1, "order_id"] = "   "
    r = run(df, "not_null", "order_id")
    assert (r.failed, r.total, r.status) == (2, 5, "fail")
    assert [s["row"] for s in r.samples] == [2, 5]


def test_unique_marks_every_duplicate_row(orders):
    r = run(orders, "unique", "order_id")
    assert r.failed == 2 and r.total == 4  # the null row is skipped


def test_unique_with_columns_and_normalize():
    df = pd.DataFrame({"name": ["محمد", "محـمد", "علي"], "city": ["الدوحة"] * 3})
    assert run(df, "unique", "name").passed
    r = run(df, "unique", "name", normalize=True, with_columns=["city"])
    assert r.failed == 2


def test_range_reasons(orders):
    r = run(orders, "range", "amount", min=0, max=100)
    assert r.failed == 3
    assert r.details == {"above 100": 1, "below 0": 1, "not a number": 1}
    assert run(pd.DataFrame({"x": ["1,250.50"]}), "range", "x", max=2000).passed


def test_range_with_dates():
    df = pd.DataFrame({"d": ["2025-12-31", "2026-03-01", "not a date"]})
    import datetime

    r = run(df, "range", "d", min=datetime.date(2026, 1, 1))
    assert r.details == {"below 2026-01-01": 1, "not a date": 1}


def test_allowed_compares_as_text():
    df = pd.DataFrame({"polarity": ["1", "-1", "0", "2"]})
    r = run(df, "allowed", "polarity", values=[-1, 0, 1])
    assert r.failed == 1 and r.samples[0]["value"] == "2"


def test_regex_full_match_and_ascii_digits():
    df = pd.DataFrame({"code": ["123", "12a", "١٢٣"]})
    assert run(df, "regex", "code", pattern=r"\d{3}").failed == 1  # Python's \d accepts Arabic-Indic digits
    assert run(df, "regex", "code", pattern=r"\d{3}", ascii=True).failed == 2


def test_length():
    df = pd.DataFrame({"text": ["نص قصير", "a", "  b  "]})
    assert run(df, "length", "text", min=2).failed == 2


def test_rule_and_where(orders):
    r = run(orders, "rule", expr="shipped >= placed")
    assert r.failed == 2  # one shipped before placed, one not shipped yet
    r = run(orders, "rule", expr="shipped >= placed", where="status == 'paid'")
    assert (r.failed, r.total) == (1, 3)


def test_rule_with_arabic_column_names():
    df = pd.DataFrame({"المبلغ": ["10", "-3"], "الخصم": ["2", "1"]})
    r = run(df, "rule", expr="`المبلغ` > `الخصم`")
    assert r.failed == 1 and "المبلغ=-3" in r.samples[0]["value"]


def test_rule_errors():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(ConfigError):
        run(df, "rule", expr="a >")
    r = run(df, "rule", expr="b > 0")
    assert not r.passed and "could not run" in r.message


def test_row_count():
    df = pd.DataFrame({"a": range(3)})
    assert run(df, "row_count", min=1, max=3).passed
    r = run(df, "row_count", min=5)
    assert not r.passed and r.message == "3 rows, expected at least 5"


def test_references(tmp_path):
    (tmp_path / "laws.json").write_text(json.dumps([{"key": "labour-2004"}, {"key": "min-wage-2020"}]), encoding="utf-8")
    df = pd.DataFrame({"law": ["labour-2004", "residency-2015", "labour-2004"]})
    r = Check("references", "law", {"path": "laws.json", "column": "key"}).run(df, Context(base_dir=tmp_path))
    assert r.failed == 1 and r.samples[0]["value"] == "residency-2015"


def test_one_value_per():
    df = pd.DataFrame({"text": ["good", "good", "bad", "ok"], "label": ["1", "-1", "-1", "0"]})
    r = run(df, "one_value_per", "label", key="text")
    assert r.failed == 2
    names = pd.DataFrame({"code": ["001", "001", "002"], "ar": ["الأغذية والمشروبات", "الأغذية  والمشروبات", "التبغ"]})
    assert run(names, "one_value_per", "ar", key="code").failed == 2
    assert run(names, "one_value_per", "ar", key="code", normalize=True).passed


def test_missing_column_fails_with_hint(orders):
    r = run(orders, "not_null", "order")
    assert not r.passed and "did you mean order_id" in r.message


def test_column_found_through_bom_and_tatweel():
    df = pd.DataFrame({"﻿الاسـم": ["x"]})
    assert run(df, "not_null", "الاسم").passed


def test_bad_parameters_are_config_errors():
    with pytest.raises(ConfigError):
        Check("range", "a", {"minimum": 1})
    with pytest.raises(ConfigError):
        Check("nope", "a")
    with pytest.raises(ConfigError):
        Check("row_count", "a")


def test_lists_from_json_lines(tmp_path):
    path = tmp_path / "a.jsonl"
    rows = [{"id": 1, "tags": ["x"]}, {"id": 2, "tags": ["x"]}, {"id": 3, "tags": []}]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    df = read_table(path)
    assert run(df, "not_null", "tags").failed == 1
    assert run(df, "unique", "tags").failed == 2
