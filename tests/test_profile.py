import pandas as pd
import yaml

from qatar_data_checks import Suite
from qatar_data_checks.cli import main
from qatar_data_checks.profile import profile, suggest_yaml


def customers():
    return pd.DataFrame(
        {
            "customer_id": ["C1", "C2", "C3", "C4"],
            "qid": ["28763400001", "29081800002", "30535600003", "28463400004"],
            "phone": ["+974 5512 3456", "33123456", "66123456", "77123456"],
            "price_qar": ["12.500", "8.250", "99.990", "5.000"],
            "city": ["الدوحة", "الريان", "الدوحة", "الدوحة"],
            "note": ["طلب سريع", None, "قـانون", "تم"],
            "joined": ["2026-01-02", "2026-02-03", "2026-03-04", "2026-04-05"],
        }
    )


def test_profile_finds_known_properties():
    p = {c.name: c for c in profile(customers())}
    assert p["customer_id"].checks == ["not_null", "unique"] and "likely id" in p["customer_id"].notes
    assert p["qid"].checks == ["not_null", "unique", "qatar_id"]
    assert p["phone"].checks[-1] == {"qatar_phone": {"kind": "mobile"}}
    assert p["price_qar"].kind == "number" and p["price_qar"].decimals == 3
    assert p["price_qar"].checks[-1] == {"qar_amount": {"decimals": 3}}
    assert {"allowed": ["الدوحة", "الريان"]} in p["city"].checks
    assert p["note"].nulls == 1 and "tatweel 1" in p["note"].notes
    assert p["joined"].kind == "date" and p["joined"].notes == ["dates 2026-01-02 to 2026-04-05"]


def test_suggested_file_runs_and_passes_on_its_own_data():
    text = suggest_yaml(customers(), "customers.csv")
    assert text.startswith("# Suggested by qdc profile from customers.csv")
    report = Suite.from_dict(yaml.safe_load(text)).run(customers())
    assert report.counts["fail"] == 0
    assert report.counts["warn"] == 1  # the tatweel in note


def test_profile_cli(tmp_path, capsys):
    path = tmp_path / "c.csv"
    customers().to_csv(path, index=False, encoding="utf-8")
    assert main(["profile", str(path), "-o", str(tmp_path / "s.yaml")]) == 0
    assert "qatar_id" in (tmp_path / "s.yaml").read_text(encoding="utf-8")
