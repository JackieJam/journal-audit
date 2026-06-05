"""图表 / 表格交互的选择解析工具。

从 Plotly on_select 事件与 st.dataframe 选择中提取业务含义（被选中的标签、
月份+方向、行索引等）。除 toggle_chart_selection 需要读写 st.session_state 外，
其余均为纯解析函数，可直接单元测试。

从 app.py 抽离；app.py 通过 alias 保留原调用名（_parse_event_points 等），
注入给各子页签的 helper key 不变。
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def parse_event_points(event) -> list[dict] | None:
    """从 Plotly 图表 on_select 事件中提取 points 列表。"""
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    points = selection.get("points", []) if hasattr(selection, "get") else []
    return points if points else None


def selected_bar_label(event) -> str | None:
    points = parse_event_points(event)
    if not points:
        return None
    label = points[0].get("y")
    return str(label) if label else None


def selected_expense_cross_year_point(event) -> tuple[int, str] | None:
    points = parse_event_points(event)
    if not points:
        return None
    point = points[0]
    category = str(point.get("y", "") or point.get("x", ""))
    year = point.get("legendgroup")
    if not category or not year:
        return None
    try:
        return int(str(year)), str(category)
    except (TypeError, ValueError):
        return None


def toggle_chart_selection(state_key: str, current_value: Any | None) -> Any | None:
    """保存图表选择；再次点中同一项时收起明细。"""
    previous_value = st.session_state.get(state_key)
    if current_value is None:
        st.session_state.pop(state_key, None)
        return None
    if previous_value == current_value:
        st.session_state.pop(state_key, None)
        return None
    st.session_state[state_key] = current_value
    return current_value


def selected_bar_label_and_direction(event, direction_map: dict[int, str]) -> tuple[str, str] | None:
    points = parse_event_points(event)
    if not points:
        return None
    point = points[0]
    label = point.get("y")
    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction = direction_map.get(curve_number)
    return (str(label), direction) if label and direction else None


def selected_monthly_metric_point(event, direction_map: dict[int, str]) -> tuple[int, str] | None:
    points = parse_event_points(event)
    if not points:
        return None
    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None
    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction = direction_map.get(curve_number)
    return (month, direction) if direction else None


def selected_ap_accrual_point(event) -> tuple[int, str] | None:
    points = parse_event_points(event)
    if not points:
        return None
    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None
    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction_map = {0: "credit", 1: "debit", 2: "net"}
    direction = direction_map.get(curve_number, "net")
    return month, direction


def selected_income_cost_abnormal_point(event) -> tuple[int, str] | None:
    points = parse_event_points(event)
    if not points:
        return None
    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None
    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction_map = {0: "income_s", 1: "cost_h"}
    direction = direction_map.get(curve_number)
    return (month, direction) if direction else None


def selected_dataframe_row_index(event) -> int | None:
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    rows = selection.get("rows", []) if hasattr(selection, "get") else []
    if not rows:
        return None
    try:
        return int(rows[0])
    except (TypeError, ValueError):
        return None


def selected_dataframe_row_indices(event) -> list[int]:
    if not event:
        return []
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    rows = selection.get("rows", []) if hasattr(selection, "get") else []
    selected_rows: list[int] = []
    for row in rows:
        try:
            selected_rows.append(int(row))
        except (TypeError, ValueError):
            continue
    return selected_rows


def selected_dataframe_focus_row_index(event) -> int | None:
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    if hasattr(selection, "get"):
        cells = selection.get("cells", [])
        rows = selection.get("rows", [])
    else:
        cells = []
        rows = []

    if cells:
        cell = cells[0]
        if isinstance(cell, str):
            row_text = cell.split(":", 1)[0]
        elif isinstance(cell, dict):
            row_text = cell.get("row", cell.get("rowIndex", ""))
        else:
            row_text = ""
        try:
            return int(row_text)
        except (TypeError, ValueError):
            pass

    if rows:
        try:
            return int(rows[-1])
        except (TypeError, ValueError):
            return None
    return None
