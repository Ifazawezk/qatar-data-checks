# qatar-data-checks

Data quality checks for pandas DataFrames, written in a small YAML file or in Python. Next to the usual null, unique, range and rule checks it has format checks for Qatar ID numbers, Qatar phone numbers, QAR amounts and Arabic text, and outlier checks that can leave out Ramadan and Eid.

## Install

```
pip install .
```

Python 3.10 or newer. Parquet needs `pip install .[parquet]`, Excel needs `.[excel]`.

## Usage

The consumer price index by expenditure group from the Qatar Open Data Portal, 2020 to 2025:

```yaml
# examples/qatar-open-data/cpi_monthly.yaml
dataset: Qatar CPI by group, monthly (data.gov.qa)
table:
  - missing_dates: {columns: [year, month], format: "%Y-%b", freq: M, by: group_code}
  - duplicate_timestamps: {columns: [year, month], format: "%Y-%b", by: group_code}
columns:
  group_code:
    - regex: "[0-9]{3}"
  group:
    - one_value_per: group_code
  lmjmw:
    - one_value_per: group_code
    - arabic_text: {severity: warn}
  cpi_index:
    - range: {min: 1, max: 500}
    - outliers: {by: group_code, severity: warn}
```

```
$ qdc run examples/qatar-open-data/cpi_monthly.csv -c examples/qatar-open-data/cpi_monthly.yaml
Qatar CPI by group, monthly (data.gov.qa): 936 rows, 7 columns

PASS  (table)     missing_dates
PASS  (table)     duplicate_timestamps
FAIL  group_code  regex                 72 of 936: values that do not match the pattern
      row 37: 0
      row 47: 0
      row 85: 0
PASS  group       one_value_per
PASS  lmjmw       one_value_per
WARN  lmjmw       arabic_text           72 of 936: Arabic text quality issues
      row 5: السلع والخدمات الأخرى  (extra_spaces)
      row 13: السلع والخدمات الأخرى  (extra_spaces)
      row 25: السلع والخدمات الأخرى  (extra_spaces)
PASS  cpi_index   range
WARN  cpi_index   outliers              24 of 936: values far from the median
      high: 12; low: 12; groups_with_zero_mad: 1
      row 8: 99.72  (robust z -4.4)
      row 30: 98.0  (robust z -5.2)
      row 38: 98.67  (robust z -4.9)

8 checks: 5 passed, 1 failed, 2 warnings
```

The general index is coded `0` while every other group is zero padded (`001` to `012`), and one Arabic group name carries extra spaces. Rows are counted from 1 without the header. `--json report.json` and `--html report.html` write the same result for CI and for people; the HTML file has no external assets.

The same checks from Python:

```python
from qatar_data_checks import Suite, read_table

suite = Suite.from_yaml("checks.yaml")  # or build one:
suite = Suite().add("unique", "رقم_الهوية").add("qatar_id", "رقم_الهوية").add("rule", expr="`المبلغ` >= 0")
report = suite.run(read_table("customers.csv"))
print(report.counts, report.exit_code())
```

## Checks

Column checks go under `columns`, table checks under `table`. Every check takes `severity: warn` and `name:`. A bare value fills the main parameter, so `allowed: [a, b]` and `regex: "[0-9]+"` work.

| Check | Parameters |
| --- | --- |
| `not_null` | blank strings and empty lists count as missing |
| `unique` | `with_columns`, `normalize` |
| `range` | `min`, `max`, `exclusive`; dates when the bounds are dates |
| `allowed` | `values`, `normalize` |
| `regex` | `pattern`, `ascii`; whole value must match |
| `length` | `min`, `max` |
| `references` | `path`, `column`; values must exist in another file |
| `one_value_per` | `key`, `normalize`; one label per comment, one name per code |
| `row_count` (table) | `min`, `max` |
| `rule` (table) | `expr`, `where`; a pandas expression such as `shipped >= placed` |
| `qatar_id` | `nationalities`, `arabic_digits` |
| `qatar_phone` | `kind` (any, mobile, landline, toll_free), `country_code` (optional, required, forbidden), `arabic_digits` |
| `qar_amount` | `decimals` (2), `negative`, `currency`, `arabic_digits` |
| `arabic_text` | `ignore` |
| `script` | `expect` (arabic, latin), `min_share` |
| `missing_dates` (table) | `column` or `columns`, `format`, `freq` (D, W, M, Q, Y), `by` |
| `duplicate_timestamps` (table) | `column` or `columns`, `format`, `by` |
| `outliers` | `threshold` (3.5), `date`, `exclude`, `by`, `split_weekend` |

Python's `\d` also matches `٠` to `٩`, so `regex` takes `ascii: true` when only 0 to 9 are valid. `normalize` compares text after NFKC, without tatweel or invisible marks and with single spaces. A column named in the check file is found even when the header has a BOM or a different Unicode form.

## Qatar formats

These check the shape of a value only. A value that passes can still be a number nobody was issued.

- Qatar ID: 11 digits, a 2 or 3, two digits of birth year, a three digit ISO 3166 nationality code, five more digits, no checksum. The layout is from Microsoft Purview's [Qatari ID card number definition](https://learn.microsoft.com/en-us/purview/sit-defn-qatari-id-card-number). Reading the first digit as the birth century is the common public explanation, and the check uses it only to reject birth years in the future.
- Phone: +974, then 8 digits; mobile numbers start with 3, 5, 6 or 7 and landlines with 4, and toll free numbers are 800 plus 4 digits. This is the plan Qatar filed with the [ITU](https://www.itu.int/oth/T02020000AB/en), as summarised on [Wikipedia](https://en.wikipedia.org/wiki/Telephone_numbers_in_Qatar).
- QAR: ISO 4217 gives the riyal 2 minor units. `1,250.50`, `QAR 99` and `75.5 ر.ق` pass.
- Arabic text: words mixing Arabic and Latin letters, Arabic-Indic or Persian digits, mixed digit systems, presentation forms (text copied out of a PDF), tatweel, invisible and bidi control marks, Persian yeh and keheh, text not in NFC, and stray spaces. Ranges come from the Unicode code charts, normalisation from UAX #15.

On generated customers with Arabic headers (`examples/generated`):

```
$ qdc run examples/generated/customers.csv -c examples/generated/customers.yaml --samples 2
...
FAIL  الهاتف            qatar_phone  3 of 240: values not in the Qatar phone number format
      prefix 2 is not used for mobile (3, 5, 6, 7) or landline (4): 1; Arabic-Indic digits: 1; landline number: 1
      row 6: +974 2512 3456  (prefix 2 is not used for mobile (3, 5, 6, 7) or landline (4))
      row 18: ٥٥١٢٣٤٥٦  (Arabic-Indic digits)
FAIL  المدينة           allowed      1 of 240: values outside the allowed set
      row 72: Doha
FAIL  إجمالي_المشتريات  qar_amount   2 of 240: values not in the QAR amount format
      3 decimal places, expected at most 2: 1; negative amount: 1
      row 53: 1,250.505  (3 decimal places, expected at most 2)
      row 89: -35.00  (negative amount)
PASS  تاريخ_التسجيل     range

13 checks: 6 passed, 6 failed, 1 warning
```

## Ramadan, Eid and the weekend

`outliers` uses the modified z-score of Iglewicz and Hoaglin (1993): 0.6745 (x - median) / MAD, flagged above 3.5. With `date` and `exclude: [ramadan, eid, holidays]` those days are left out of the baseline and never flagged. Hijri dates come from the Umm al-Qura calendar (hijridate); the days announced in Qatar can differ by one. `split_weekend` gives Friday and Saturday their own baseline.

Generated daily orders of a Doha grocery app across Ramadan 1447, with one outage on 14 January:

```
$ qdc run examples/generated/daily_orders.csv -c examples/generated/daily_orders.yaml
daily orders (generated): 151 rows, 3 columns

FAIL  (table)      missing_dates         1 of 151: periods with no rows
      expected_periods: 151; first: 2025-12-01; last: 2026-04-30
      2026-04-07  (missing)
FAIL  (table)      duplicate_timestamps  2 of 151: timestamps that appear more than once
      row 51: 2026-01-20
      row 52: 2026-01-20
WARN  orders       outliers (plain)      10 of 151: values far from the median
      high: 8; low: 2
      row 45: 310  (robust z -5.6)
      row 83: 1927  (robust z +4.1)
      row 84: 1961  (robust z +4.3)
FAIL  orders       outliers (calendar)   1 of 151: values far from the median
      skipped_days: 35; high: 0; low: 1
      row 45: 310  (robust z -17.0)
PASS  revenue_qar  qar_amount

5 checks: 1 passed, 3 failed, 1 warning
```

## Profile and drift

`qdc profile data.csv -o checks.yaml` writes a starting check file: types, null rates, observed ranges and label sets, likely id columns, and the Qatar formats that 90% of a column already follows.

```
$ qdc profile examples/generated/customers.csv
...
# column            type      nulls distinct  notes
# رقم_العميل        text         0%      240  likely id
# رقم_الهوية        integer      0%      239  Qatar ID format
# الاسم             text        <1%      106  Arabic; tatweel 1, persian_letters 1
# الهاتف            text         0%      240  Qatar phone format
# المدينة           text         0%        9  Arabic
# إجمالي_المشتريات  number       0%      240  looks like money
# تاريخ_التسجيل     date         0%      203  dates 2024-01-02 to 2025-11-17
...
```

`qdc drift old.csv new.csv` compares two versions. Numeric columns get the population stability index over deciles of the old data and a Kolmogorov-Smirnov test; categories (and numeric columns with 10 or fewer values) get PSI and a chi-square test. Status follows PSI, read as in Siddiqi (2006): under 0.1 stable, 0.1 to 0.25 moderate, 0.25 or more major. The p-values are printed as support, since with many rows they drop below 0.01 for shifts too small to matter.

```
$ qdc drift examples/qatar-open-data/cpi_2024.csv examples/qatar-open-data/cpi_2025.csv --columns group_code,lmjmw,cpi_index
cpi_2024.csv: 156 rows  ->  cpi_2025.csv: 156 rows
PSI below 0.1 is stable, 0.1 to 0.25 moderate, 0.25 or more major

column      type            PSI  test     stat          p         nulls  status
group_code  categorical   0.000  chi2    0.000          1      0% -> 0%  stable
lmjmw       categorical   0.000  chi2    0.000          1      0% -> 0%  stable
cpi_index   numeric       0.221  ks      0.135       0.12      0% -> 0%  moderate

3 columns: 2 stable, 1 moderate
```

## Examples

`examples/qatar-open-data` holds two datasets from the [Qatar Open Data Portal](https://www.data.gov.qa), published by the National Planning Council under CC BY 4.0 and downloaded on 2026-11-04 with `fetch.py`. On the commodity prices file, the Arabic category and product names often change between years while the English name stays the same: 140 category rows and 349 product rows still differ after spacing is normalised. `examples/generated` is made up by `make_data.py`, with errors planted on purpose.

The check files in `examples/qanun` and `examples/acas` are run against the article corpus of [qanun](https://github.com/Ifazawezk/qanun) and the evaluation data of [ACAS](https://github.com/Ifazawezk/ACAS). On qanun's `articles.jsonl` the ids, law keys and the id rule pass; 30 articles have no English text, `labour-2004:116` has a shadda typed before its kasra (not NFC) and `min-wage-2020:1` has a Persian yeh. In ACAS's data, 293 of the Arabic product reviews contain no Arabic letters, 2 restaurant review rows share a text but not a label, and the airline tweets have 310 rows with a repeated `tweet_id` and 57 rows whose text has more than one sentiment label.

## Exit codes

| Code | `qdc run` | `qdc drift` |
| --- | --- | --- |
| 0 | every error-level check passed (warnings allowed) | no major shift |
| 1 | an error-level check failed, or a warning with `--fail-on warn` | a major shift, or a moderate one with `--fail-on moderate` |
| 2 | bad check file, unreadable data or bad arguments | unreadable data or bad arguments |

`qdc profile` exits 0, or 2 when it cannot read the file.

## Limits

Format checks cannot tell a real ID or phone number from a made-up one. `rule` expressions run through pandas `eval`, so only use check files you trust. `script` counts letters and cannot tell Arabic from Persian or English from French. Holiday dates are calculated, and Qatar's announced Eid holidays are usually longer than the days used here. YAML reads `yes` and `no` as booleans, so quote them in `allowed`.

## License

MIT
