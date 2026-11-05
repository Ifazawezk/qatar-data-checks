import json
from html.parser import HTMLParser

import pandas as pd
import pytest

from qatar_data_checks import Suite
from qatar_data_checks.report import to_html, to_json, to_text


@pytest.fixture
def report():
    df = pd.DataFrame({"الاسم": ["مريم", "قـانون", None], "phone": ["+974 5512 3456", "1234", "4444 1234"]})
    suite = (
        Suite(name="عملاء")
        .add("not_null", "الاسم")
        .add("arabic_text", "الاسم", severity="warn")
        .add("qatar_phone", "phone")
        .add("row_count", min=1)
    )
    return suite.run(df)


def test_text(report):
    text = to_text(report)
    lines = text.splitlines()
    assert lines[0] == "عملاء: 3 rows, 2 columns"
    assert any(line.startswith("FAIL  الاسم") and "1 of 3: missing or blank values" in line for line in lines)
    assert "      row 2: قـانون  (tatweel)" in lines
    assert lines[-1] == "4 checks: 1 passed, 2 failed, 1 warning"


def test_json_keeps_arabic(report):
    text = to_json(report)
    assert "الاسم" in text  # not escaped as \u0627...
    data = json.loads(text)
    assert data["summary"] == {"pass": 1, "fail": 2, "warn": 1}
    assert data["results"][2]["samples"][0] == {"row": 2, "value": "1234", "reason": "4 digits, expected 8"}


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.text, self.external = [], [], []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        for name, value in attrs:
            if name in ("src", "href") and value:
                self.external.append(value)

    def handle_data(self, data):
        self.text.append(data)


def test_html_is_self_contained(report):
    page = to_html(report)
    parser = Collector()
    parser.feed(page)
    assert parser.external == []  # no scripts, fonts or stylesheets from elsewhere
    assert parser.tags.count("tr") == 5 and "style" in parser.tags
    text = "".join(parser.text)
    assert "عملاء" in text and "row 2: قـانون  (tatweel)" in text
    assert 'dir="auto"' in page and "<script" not in page


def test_html_escapes_values():
    df = pd.DataFrame({"x": ["<b>bold</b>"]})
    page = to_html(Suite().add("allowed", "x", values=["a"]).run(df))
    assert "&lt;b&gt;bold&lt;/b&gt;" in page and "<b>bold</b>" not in page
