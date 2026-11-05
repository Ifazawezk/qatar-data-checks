import datetime as dt

import pandas as pd
import pytest

from qatar_data_checks import Check, ConfigError
from qatar_data_checks.qatar import phone_kind, qar_problem, qatar_id_problem

TODAY = dt.date(2026, 11, 4)


@pytest.mark.parametrize(
    "value, problem",
    [
        ("28763400001", ""),  # born 1987, Qatari (ISO 3166 numeric 634)
        ("30581800123", ""),  # born 2005, Egyptian (818)
        (28763400001, ""),  # read from JSON as a number
        ("2876340000", "not 11 digits"),
        ("2876340000a", "not 11 digits"),
        ("18763400001", "first digit is not 2 or 3"),
        ("32763400001", "birth year 2027 is in the future"),
        ("28700000001", "nationality code 000"),
        ("٢٨٧٦٣٤٠٠٠٠١", "Arabic-Indic digits"),
    ],
)
def test_qatar_id(value, problem):
    assert qatar_id_problem(value, today=TODAY) == problem


def test_qatar_id_options():
    assert qatar_id_problem("٢٨٧٦٣٤٠٠٠٠١", arabic_digits=True, today=TODAY) == ""
    assert qatar_id_problem("30581800123", nationalities=[634], today=TODAY).startswith("nationality code 818")


@pytest.mark.parametrize(
    "value, kind, problem",
    [
        ("+974 5512 3456", "mobile", ""),
        ("0097433123456", "mobile", ""),
        ("97466123456", "mobile", ""),
        ("7712-3456", "mobile", ""),
        ("4444 1234", "landline", ""),
        ("800 1234", "toll_free", ""),
        ("+974 2512 3456", None, "starts with 2, not a mobile (3, 5, 6, 7) or landline (4) prefix"),
        ("5512345", None, "7 digits, expected 8"),
        ("+974 ٥٥١٢٣٤٥٦", None, "Arabic-Indic digits"),
        ("call me", None, "not a phone number"),
    ],
)
def test_phone_kind(value, kind, problem):
    assert phone_kind(value) == (kind, problem)


def test_phone_country_code_rules():
    assert phone_kind("55123456", country_code="required") == (None, "no +974 country code")
    assert phone_kind("+97455123456", country_code="forbidden") == (None, "has a country code")
    assert phone_kind("٥٥١٢٣٤٥٦", arabic_digits=True) == ("mobile", "")


def test_phone_check_by_kind():
    df = pd.DataFrame({"الهاتف": ["+974 5512 3456", "4444 1234", "800 1234", None]})
    r = Check("qatar_phone", "الهاتف", {"kind": "mobile"}).run(df)
    assert (r.failed, r.total) == (2, 3)
    assert r.details == {"landline number": 1, "toll free number": 1}
    with pytest.raises(ConfigError):
        Check("qatar_phone", "الهاتف", {"kind": "fax"}).run(df)


@pytest.mark.parametrize(
    "value, problem",
    [
        ("1,250.50", ""),
        ("QAR 99", ""),
        ("75.5 ر.ق", ""),
        ("12 ريال قطري", ""),
        (19.99, ""),
        (6.528, "more than 2 decimal places"),
        ("6.528", "3 decimal places, expected at most 2"),
        ("-5", "negative amount"),
        ("1,25.00", "not an amount"),
        ("١٢٫٥٠", "Arabic-Indic digits"),
        ("free", "not an amount"),
    ],
)
def test_qar_amount(value, problem):
    assert qar_problem(value) == problem


def test_qar_options():
    assert qar_problem("6.528", decimals=3) == ""
    assert qar_problem("-5", negative=True) == ""
    assert qar_problem("QAR 5", currency=False) == "currency text in the value"
    assert qar_problem("١٢٫٥٠", arabic_digits=True) == ""


def test_qatar_checks_in_a_suite():
    from qatar_data_checks import Suite

    df = pd.DataFrame({"qid": ["28763400001", "1234"], "amount": ["10.00", "10.005"]})
    suite = Suite.from_dict({"columns": {"qid": ["qatar_id"], "amount": ["qar_amount"]}})
    assert [r.failed for r in suite.run(df).results] == [1, 1]
