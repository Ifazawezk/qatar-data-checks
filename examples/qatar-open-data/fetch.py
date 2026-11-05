"""Download the two Qatar Open Data Portal datasets used in the examples.

Source: Qatar Open Data Portal (data.gov.qa), published by the National Planning
Council under CC BY 4.0 (creativecommons.org/licenses/by/4.0). Downloaded on
2026-11-04 through the portal's export API.

    python examples/qatar-open-data/fetch.py
"""
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

HERE = Path(__file__).parent
API = "https://www.data.gov.qa/api/explore/v2.1/catalog/datasets/{}/exports/csv?delimiter=%2C"
HEADERS = {"User-Agent": "qatar-data-checks example download (Python urllib)"}
DATASETS = {
    "commodity_prices.csv": "annual_average_consumer_prices_selected_commodities",
    "cpi_monthly.csv": "consumer-price-index-cpi-by-expenditure-group-monthly",
}

for name, dataset in DATASETS.items():
    with urlopen(Request(API.format(dataset), headers=HEADERS), timeout=60) as response:
        (HERE / name).write_bytes(response.read())
    print(f"saved {name}")

cpi = pd.read_csv(HERE / "cpi_monthly.csv", dtype=str, encoding="utf-8-sig")
for year in ("2024", "2025"):
    cpi[cpi["year"] == year].to_csv(HERE / f"cpi_{year}.csv", index=False, encoding="utf-8")
    print(f"saved cpi_{year}.csv")
