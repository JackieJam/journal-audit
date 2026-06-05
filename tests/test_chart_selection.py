"""components.chart_selection 纯解析函数单元测试。

toggle_chart_selection 依赖 st.session_state，由 AppTest 渲染层间接覆盖，此处不单测。
"""

from __future__ import annotations

import pytest

from components.chart_selection import (
    parse_event_points,
    selected_ap_accrual_point,
    selected_bar_label,
    selected_bar_label_and_direction,
    selected_dataframe_focus_row_index,
    selected_dataframe_row_index,
    selected_dataframe_row_indices,
    selected_expense_cross_year_point,
    selected_income_cost_abnormal_point,
    selected_monthly_metric_point,
)

pytestmark = pytest.mark.unit


def _plot(points: list[dict]) -> dict:
    return {"selection": {"points": points}}


def _table(**selection) -> dict:
    return {"selection": selection}


def test_parse_event_points():
    assert parse_event_points(_plot([{"x": 1}])) == [{"x": 1}]
    assert parse_event_points(None) is None
    assert parse_event_points(_plot([])) is None


def test_selected_bar_label():
    assert selected_bar_label(_plot([{"y": "科目A"}])) == "科目A"
    assert selected_bar_label(_plot([{"y": ""}])) is None
    assert selected_bar_label(None) is None


def test_selected_expense_cross_year_point():
    ev = _plot([{"y": "差旅费", "legendgroup": "2023"}])
    assert selected_expense_cross_year_point(ev) == (2023, "差旅费")
    assert selected_expense_cross_year_point(_plot([{"y": "x"}])) is None


def test_selected_bar_label_and_direction():
    ev = _plot([{"y": "客户A", "curveNumber": 1}])
    assert selected_bar_label_and_direction(ev, {1: "debit"}) == ("客户A", "debit")
    assert selected_bar_label_and_direction(ev, {0: "credit"}) is None


def test_selected_monthly_metric_point():
    ev = _plot([{"x": "3月", "curveNumber": 0}])
    assert selected_monthly_metric_point(ev, {0: "income"}) == (3, "income")
    assert selected_monthly_metric_point(_plot([{"x": "bad"}]), {0: "income"}) is None


def test_selected_ap_accrual_point():
    assert selected_ap_accrual_point(_plot([{"x": "5月", "curveNumber": 0}])) == (5, "credit")
    assert selected_ap_accrual_point(_plot([{"x": "5月", "curveNumber": 9}])) == (5, "net")


def test_selected_income_cost_abnormal_point():
    assert selected_income_cost_abnormal_point(_plot([{"x": "7月", "curveNumber": 1}])) == (7, "cost_h")
    assert selected_income_cost_abnormal_point(_plot([{"x": "7月", "curveNumber": 5}])) is None


def test_selected_dataframe_row_index():
    assert selected_dataframe_row_index(_table(rows=[2, 4])) == 2
    assert selected_dataframe_row_index(_table(rows=[])) is None
    assert selected_dataframe_row_index(None) is None


def test_selected_dataframe_row_indices():
    assert selected_dataframe_row_indices(_table(rows=[1, 3, 5])) == [1, 3, 5]
    assert selected_dataframe_row_indices(_table(rows=["bad", 2])) == [2]
    assert selected_dataframe_row_indices(None) == []


def test_selected_dataframe_focus_row_index():
    assert selected_dataframe_focus_row_index(_table(cells=["3:0"])) == 3
    assert selected_dataframe_focus_row_index(_table(cells=[{"row": 4}])) == 4
    assert selected_dataframe_focus_row_index(_table(rows=[6, 8])) == 8
    assert selected_dataframe_focus_row_index(None) is None
