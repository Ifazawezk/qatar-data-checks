"""Generate the two example files in this folder. Every row is made up.

customers.csv     customers of a made-up Doha online shop, with Arabic headers
daily_orders.csv  daily orders from December 2025 to April 2026, across Ramadan 1447

The Qatar ID and phone numbers follow the formats but are random. Some rows are
broken on purpose so the checks have something to find.

    python examples/generated/make_data.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
from hijridate import Gregorian

HERE = Path(__file__).parent
rng = np.random.default_rng(2026)

FIRST = ["محمد", "أحمد", "فاطمة", "مريم", "علي", "نورة", "خالد", "سارة", "يوسف", "عائشة", "حمد", "ريم"]
FAMILY = ["الكواري", "المري", "الهاجري", "النعيمي", "الحسن", "عبدالله", "إبراهيم", "الشمري", "خان", "سانتوس"]
CITIES = ["الدوحة", "الريان", "الوكرة", "الخور", "أم صلال", "الظعاين", "الشمال", "الشحانية"]
NATIONALITY = [634, 818, 356, 586, 608, 400, 729, 524, 50, 760]  # ISO 3166-1 numeric codes

n = 240
qid = [
    f"{2 if year < 2000 else 3}{year % 100:02d}{code:03d}{rng.integers(0, 100000):05d}"
    for year, code in zip(rng.integers(1965, 2006, n), rng.choice(NATIONALITY, n))
]
phone = [f"+974 {rng.choice(list('3567'))}{rng.integers(0, 1000):03d} {rng.integers(0, 10000):04d}" for _ in range(n)]
customers = pd.DataFrame(
    {
        "رقم_العميل": [f"C{i:04d}" for i in range(1, n + 1)],
        "رقم_الهوية": qid,
        "الاسم": [f"{rng.choice(FIRST)} {rng.choice(FAMILY)}" for _ in range(n)],
        "الهاتف": phone,
        "المدينة": rng.choice(CITIES, n, p=[0.45, 0.25, 0.1, 0.05, 0.06, 0.04, 0.03, 0.02]),
        "إجمالي_المشتريات": [f"{v:.2f}" for v in rng.lognormal(6.5, 0.8, n)],
        "تاريخ_التسجيل": pd.to_datetime("2024-01-01") + pd.to_timedelta(rng.integers(0, 700, n), unit="D"),
    }
)
customers["تاريخ_التسجيل"] = customers["تاريخ_التسجيل"].dt.strftime("%Y-%m-%d")
broken = {
    5: {"الهاتف": "+974 2512 3456"},  # 2 is not a mobile or landline prefix
    17: {"الهاتف": "٥٥١٢٣٤٥٦"},  # Arabic-Indic digits from a phone keyboard
    23: {"الاسم": "مـريم الكواري"},  # tatweel
    31: {"رقم_الهوية": "2876340001"},  # 10 digits
    44: {"رقم_الهوية": qid[3]},  # duplicate ID
    52: {"إجمالي_المشتريات": "1,250.505"},
    60: {"الاسم": "علی المري"},  # Persian yeh
    71: {"المدينة": "Doha"},
    88: {"إجمالي_المشتريات": "-35.00"},
    95: {"الهاتف": "4444 1234"},  # a landline
}
for row, values in broken.items():
    for column, value in values.items():
        customers.loc[row, column] = value
customers.loc[110, "الاسم"] = None
customers.to_csv(HERE / "customers.csv", index=False, encoding="utf-8")


def label(day: pd.Timestamp) -> str:
    h = Gregorian(day.year, day.month, day.day).to_hijri()
    if h.month == 9:
        return "ramadan"
    if h.month == 10 and h.day <= 3:
        return "eid"
    return ""


days = pd.date_range("2025-12-01", "2026-04-30")
weekend = days.day_of_week.isin([4, 5])  # Friday and Saturday
orders = np.where(weekend, 1500, 1200) * rng.normal(1, 0.04, len(days))
season = np.array([label(d) for d in days])
orders[season == "ramadan"] *= 1.35  # late evening grocery orders
orders[season == "eid"] *= 0.55
orders[days == "2025-12-18"] *= 0.7  # National Day
orders[days == "2026-01-14"] = 310  # a made-up outage
daily = pd.DataFrame({"date": days.strftime("%Y-%m-%d"), "orders": orders.round().astype(int)})
daily["revenue_qar"] = (daily["orders"] * rng.normal(185, 6, len(days))).round(2).map(lambda v: f"{v:.2f}")
daily = daily[daily["date"] != "2026-04-07"]  # a day the export missed
daily = pd.concat([daily, daily[daily["date"] == "2026-01-20"]]).sort_values("date")  # and one it wrote twice
daily.to_csv(HERE / "daily_orders.csv", index=False, encoding="utf-8")
print(f"wrote customers.csv ({len(customers)} rows) and daily_orders.csv ({len(daily)} rows)")
