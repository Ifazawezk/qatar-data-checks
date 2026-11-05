import datetime as dt

import numpy as np
import pandas as pd
import pytest
from scipy.stats import median_abs_deviation

from qatar_data_checks import Check, ConfigError
from qatar_data_checks.qatar_calendar import day_label, is_weekend
from qatar_data_checks.timeseries import robust_z


@pytest.mark.parametrize(
    "day, label",
    [
        (dt.date(2024, 3, 11), "ramadan"),  # 1 Ramadan 1445 in Umm al-Qura and in Qatar
        (dt.date(2024, 4, 9), "ramadan"),
        (dt.date(2024, 4, 10), "eid_al_fitr"),  # 1 Shawwal 1445
        (dt.date(2024, 6, 15), "eid_al_adha"),  # Arafat Day 1445
        (dt.date(2024, 6, 19), ""),
        (dt.date(2024, 12, 18), "national_day"),
        (dt.date(2026, 2, 10), "sport_day"),  # second Tuesday of February 2026
        (dt.date(2026, 2, 3), ""),
        (dt.date(1900, 1, 1), ""),  # outside the Umm al-Qura table
    ],
)
def test_day_label(day, label):
    assert day_label(day) == label


def test_weekend_is_friday_and_saturday():
    days = pd.Series(pd.date_range("2026-11-01", periods=7))  # Sunday to Saturday
    assert is_weekend(days).tolist() == [False] * 5 + [True, True]


def test_robust_z_matches_iglewicz_hoaglin():
    x = pd.Series([1, 1, 2, 2, 4, 6, 9], dtype=float)  # median 2, MAD 1
    assert median_abs_deviation(x) == 1
    assert robust_z(x).iloc[-1] == pytest.approx(0.6745 * 7)
    assert robust_z(pd.Series([5.0, 5.0, 5.0, 9.0])) is None


def test_missing_dates_daily():
    df = pd.DataFrame({"date": ["2026-01-01", "2026-01-02", "2026-01-05", "bad"]})
    r = Check("missing_dates", params={"column": "date"}).run(df)
    assert r.failed == 3  # 3 and 4 January, and one unreadable date
    assert [s["value"] for s in r.samples] == ["2026-01-03", "2026-01-04"]
    assert r.details["unreadable_dates"] == 1


def test_missing_months_by_group_from_year_and_month():
    df = pd.DataFrame(
        {
            "year": ["2024"] * 3 + ["2024"] * 2,
            "month": ["Jan", "Feb", "Mar", "Jan", "Mar"],
            "group": ["food"] * 3 + ["rent"] * 2,
        }
    )
    params = {"columns": ["year", "month"], "format": "%Y-%b", "freq": "M", "by": "group"}
    r = Check("missing_dates", params=params).run(df)
    assert (r.failed, r.total) == (1, 6)
    assert r.samples[0] == {"row": None, "value": "2024-02", "reason": "missing for rent"}


def test_duplicate_timestamps():
    df = pd.DataFrame({"ts": ["2026-01-01 10:00", "2026-01-01 10:00", "2026-01-01 11:00"], "shop": ["a", "a", "a"]})
    assert Check("duplicate_timestamps", params={"column": "ts", "by": "shop"}).run(df).failed == 2


def daily_orders():
    rng = np.random.default_rng(7)
    days = pd.date_range("2024-02-01", "2024-05-31")
    orders = rng.normal(1000, 30, len(days)).round()
    labels = pd.Series(days).map(lambda d: day_label(d.date()))
    orders[(labels == "ramadan").to_numpy()] *= 1.6  # evening orders jump in Ramadan
    orders[(labels == "eid_al_fitr").to_numpy()] *= 0.4
    return pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "orders": orders})


def test_outliers_flag_ramadan_unless_excluded():
    df = daily_orders()
    plain = Check("outliers", "orders").run(df)
    assert plain.failed >= 30  # every Ramadan day and the Eid days look odd
    aware = Check("outliers", "orders", {"date": "date", "exclude": ["ramadan", "eid"]}).run(df)
    assert aware.failed == 0
    assert aware.details["skipped_days"] == 33  # 30 days of Ramadan 1445 and 3 days of Eid


def test_outliers_split_weekend():
    days = pd.date_range("2026-01-04", periods=56)  # eight weeks from a Sunday
    orders = np.where(days.day_of_week.isin([4, 5]), 2000.0, 1000.0) + np.tile([0, 5, -5, 10, -10, 3, -3], 8)
    df = pd.DataFrame({"date": days, "orders": orders})
    df.loc[10, "orders"] = 1400.0  # a Wednesday
    plain = Check("outliers", "orders").run(df)
    assert plain.failed == 17  # all 16 Fridays and Saturdays, and the Wednesday
    split = Check("outliers", "orders", {"date": "date", "split_weekend": True}).run(df)
    assert split.failed == 1 and split.samples[0]["row"] == 11 and split.details["high"] == 1


def test_outliers_needs_a_date_to_exclude():
    with pytest.raises(ConfigError):
        Check("outliers", "orders", {"exclude": ["ramadan"]}).run(daily_orders())
    with pytest.raises(ConfigError):
        Check("outliers", "orders", {"date": "date", "exclude": ["summer"]}).run(daily_orders())
