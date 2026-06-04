"""年份归集与 Period 13 标记的回归测试。

跨年调账凭证的年份归集（会计年度优先于过账日期）和 Period 13 识别，
直接决定多年分析的分片正确性。归错年 = 跨年勾稽全错。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.ingestion import _tag_years

pytestmark = pytest.mark.unit


def test_period13_flagged_from_period_column() -> None:
    df = pd.DataFrame(
        {
            "过账期间": [1, 12, 13],
            "过账日期": pd.to_datetime(["2024-01-10", "2024-12-20", "2024-12-31"]),
        }
    )
    out = _tag_years(df)
    assert out["_is_period13"].tolist() == [False, False, True]


def test_fiscal_year_takes_priority_over_posting_date() -> None:
    # 业务发生在 2024 年，但 2025-01 才过账的跨年调账凭证
    df = pd.DataFrame(
        {
            "会计年度": [2024],
            "过账日期": pd.to_datetime(["2025-01-15"]),
        }
    )
    out = _tag_years(df)
    assert out["_year"].tolist() == [2024]  # 归 2024 而非 2025


def test_falls_back_to_posting_year_when_fiscal_missing() -> None:
    df = pd.DataFrame(
        {
            "会计年度": [pd.NA],
            "过账日期": pd.to_datetime(["2023-07-01"]),
        }
    )
    out = _tag_years(df)
    assert out["_year"].tolist() == [2023]


def test_no_period_column_means_no_period13() -> None:
    df = pd.DataFrame({"过账日期": pd.to_datetime(["2024-06-01"])})
    out = _tag_years(df)
    assert out["_is_period13"].tolist() == [False]


def test_does_not_mutate_input() -> None:
    df = pd.DataFrame({"过账日期": pd.to_datetime(["2024-06-01"])})
    _tag_years(df)
    assert "_year" not in df.columns
