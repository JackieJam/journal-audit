"""components.candidate_actions 纯函数单元测试。

detail_metrics / detail_amount_series / style_selected_detail_rows 不依赖 st，
可直接单测；其余依赖 st.session_state 的渲染函数由 AppTest 间接覆盖，此处不单测。
"""

from __future__ import annotations

import pandas as pd
import pytest

from components.candidate_actions import (
    detail_amount_series,
    detail_metrics,
    style_selected_detail_rows,
)

pytestmark = pytest.mark.unit


class TestDetailMetrics:
    def test_empty_returns_zeros(self):
        assert detail_metrics(pd.DataFrame()) == {"rows": 0, "vouchers": 0, "amount": 0.0}

    def test_counts_rows_vouchers_and_amount(self):
        df = pd.DataFrame({
            "凭证编号": ["A", "A", "B"],
            "收入影响": [100, -50, 200],
        })
        out = detail_metrics(df)
        assert out["rows"] == 3
        assert out["vouchers"] == 2
        # 取首个命中金额列，绝对值求和：100 + 50 + 200
        assert out["amount"] == 350.0

    def test_uses_first_matching_amount_column(self):
        # 同时存在两列时，按 amount_cols 顺序取"收入影响"优先
        df = pd.DataFrame({
            "凭证编号": ["A"],
            "收入影响": [10],
            "成本发生额": [999],
        })
        assert detail_metrics(df)["amount"] == 10.0

    def test_no_amount_column_amount_zero(self):
        df = pd.DataFrame({"凭证编号": ["A", "B"]})
        out = detail_metrics(df)
        assert out["rows"] == 2 and out["vouchers"] == 2 and out["amount"] == 0.0

    def test_no_voucher_column_vouchers_zero(self):
        df = pd.DataFrame({"收入影响": [100, 200]})
        out = detail_metrics(df)
        assert out["rows"] == 2 and out["vouchers"] == 0 and out["amount"] == 300.0

    def test_non_numeric_amount_coerced(self):
        df = pd.DataFrame({"凭证编号": ["A"], "收入影响": ["bad"]})
        assert detail_metrics(df)["amount"] == 0.0


class TestDetailAmountSeries:
    def test_returns_abs_of_first_matching_column(self):
        df = pd.DataFrame({"成本发生额": [-100, 50]})
        series = detail_amount_series(df)
        assert series.tolist() == [100.0, 50.0]

    def test_no_amount_column_returns_zero_series(self):
        df = pd.DataFrame({"无关列": [1, 2, 3]})
        series = detail_amount_series(df)
        assert series.tolist() == [0.0, 0.0, 0.0]
        assert len(series) == len(df)

    def test_non_numeric_filled_with_zero(self):
        df = pd.DataFrame({"收入影响": ["x", -20]})
        assert detail_amount_series(df).tolist() == [0.0, 20.0]


class TestStyleSelectedDetailRows:
    def test_selected_row_gets_highlight(self):
        styler = style_selected_detail_rows({"A"})
        row = pd.Series({"__voucher_id_raw": "A", "col1": 1})
        styles = styler(row)
        assert all("background-color" in s for s in styles)
        assert len(styles) == len(row)

    def test_unselected_row_blank(self):
        styler = style_selected_detail_rows({"A"})
        row = pd.Series({"__voucher_id_raw": "B", "col1": 1})
        assert styler(row) == ["", ""]

    def test_missing_voucher_key_treated_as_unselected(self):
        styler = style_selected_detail_rows({"A"})
        row = pd.Series({"col1": 1})
        assert styler(row) == [""]
