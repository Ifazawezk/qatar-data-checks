import numpy as np
import pandas as pd
import pytest
from scipy.stats import entropy

from qatar_data_checks.cli import main
from qatar_data_checks.drift import compare, psi

CITIES = ["الدوحة", "الريان", "الوكرة"]


def test_psi_hand_value():
    # (0.6 - 0.5) ln(0.6 / 0.5) + (0.4 - 0.5) ln(0.4 / 0.5) = 0.018232 + 0.022314
    assert psi([50, 50], [60, 40]) == pytest.approx(0.040546, abs=1e-6)


def test_psi_is_symmetric_kl_divergence():
    e, a = np.array([0.1, 0.2, 0.3, 0.4]), np.array([0.25, 0.25, 0.25, 0.25])
    assert psi(e, a) == pytest.approx(entropy(a, e) + entropy(e, a))


def frames(shift=0.0, seed=1):
    rng = np.random.default_rng(seed)

    def one(mean):
        return pd.DataFrame({"basket_qar": rng.normal(mean, 40, 4000), "city": rng.choice(CITIES, 4000, p=[0.6, 0.3, 0.1])})

    return one(250), one(250 + shift)


def test_same_distribution_is_stable():
    report = compare(*frames(shift=0.0))
    assert [c.status for c in report.columns] == ["stable", "stable"]
    assert report.exit_code() == 0


def test_identical_data():
    ref, _ = frames()
    report = compare(ref, ref.copy())
    assert report.columns[0].psi == pytest.approx(0) and report.columns[0].p_value == pytest.approx(1)


def test_shift_is_major_and_ks_matches_known_case():
    report = compare(*frames(shift=40))  # one standard deviation
    basket = report.columns[0]
    assert basket.status == "major" and basket.p_value < 1e-6
    assert report.exit_code() == 1
    small = compare(pd.DataFrame({"x": [1.0, 2, 3]}), pd.DataFrame({"x": [4.0, 5, 6]})).columns[0]
    assert small.statistic == 1.0  # disjoint samples: KS D = 1


def test_chi_square_known_table():
    ref = pd.DataFrame({"label": ["a"] * 10 + ["b"] * 20})
    cur = pd.DataFrame({"label": ["a"] * 20 + ["b"] * 10})
    col = compare(ref, cur).columns[0]
    # expected count 15 in every cell: 4 * 25 / 15 = 6.667 on 1 degree of freedom, p = 0.0098
    assert col.statistic == pytest.approx(20 / 3) and col.p_value == pytest.approx(0.009823, abs=1e-5)


def test_arabic_categories_and_ids_skipped():
    ref = pd.DataFrame({"id": [f"r{i}" for i in range(100)], "city": ["الدوحة"] * 80 + ["الريان"] * 20})
    cur = pd.DataFrame({"id": [f"c{i}" for i in range(100)], "city": ["الدوحة"] * 40 + ["الريان"] * 60, "new": 1})
    report = compare(ref, cur)
    assert {c.column: c.status for c in report.columns} == {"id": "skipped", "city": "major"}
    assert report.only_in == {"reference": [], "current": ["new"]}
    assert "city" in report.to_text()


def test_drift_cli(tmp_path, capsys):
    ref, cur = frames(shift=40)
    ref.to_csv(tmp_path / "a.csv", index=False, encoding="utf-8")
    cur.to_csv(tmp_path / "b.csv", index=False, encoding="utf-8")
    assert main(["drift", str(tmp_path / "a.csv"), str(tmp_path / "b.csv")]) == 1
    out = capsys.readouterr().out
    assert "basket_qar" in out and "major" in out
    assert main(["drift", str(tmp_path / "a.csv"), str(tmp_path / "b.csv"), "--columns", "city"]) == 0
