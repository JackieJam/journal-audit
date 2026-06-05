"""modules.formatting 纯函数单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from modules.formatting import (
    escape_html,
    format_list,
    format_money,
    format_multiplier,
    format_percent,
    format_years,
    plain_value,
)

pytestmark = pytest.mark.unit


def test_format_money_buckets():
    assert format_money(1234) == "1,234元"
    assert format_money(12345) == "1.2万元"
    assert format_money(123_456_789) == "1.23亿元"
    assert format_money(-50000) == "-5.0万元"
    assert format_money("not-a-number") == "not-a-number"


def test_format_percent():
    assert format_percent(0.25) == "25%"
    assert format_percent(1) == "100%"
    assert format_percent("x") == "x"


def test_format_multiplier():
    assert format_multiplier(2.5) == "2.5倍"
    assert format_multiplier("x") == "x"


def test_format_list():
    assert format_list(["a", "b", "c"]) == "a、b、c"
    assert format_list("single") == "single"
    assert format_list([]) == ""


def test_plain_value_unwraps_numpy_scalars():
    assert plain_value(np.int64(7)) == 7
    assert isinstance(plain_value(np.int64(7)), int)
    assert plain_value({"a": np.float64(1.5)}) == {"a": 1.5}
    assert plain_value([np.int64(1), np.int64(2)]) == [1, 2]
    assert plain_value("plain") == "plain"


def test_format_years():
    assert format_years([2022, 2023]) == "2022、2023"
    assert format_years([]) == "未标明"
    assert format_years(2024) == "2024"


def test_escape_html():
    assert escape_html("<a>&\"b\"") == "&lt;a&gt;&amp;&quot;b&quot;"
    assert escape_html("line1\nline2") == "line1&#10;line2"
