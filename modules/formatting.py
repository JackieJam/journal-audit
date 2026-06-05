"""通用展示格式化工具。

纯函数，无 Streamlit / session 依赖，可被任意层调用并单独测试。
从 app.py 抽离；app.py 通过 alias 保留原调用名（_format_money 等），调用点不变。
"""

from __future__ import annotations

from typing import Any


def format_money(value: Any) -> str:
    """金额按亿/万/元自动分档，保留符号；非数值原样返回。"""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1e8:
        return f"{sign}{amount / 1e8:.2f}亿元"
    if amount >= 1e4:
        return f"{sign}{amount / 1e4:.1f}万元"
    return f"{sign}{amount:,.0f}元"


def format_percent(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return str(value)


def format_multiplier(value: Any) -> str:
    try:
        return f"{float(value):.1f}倍"
    except (TypeError, ValueError):
        return str(value)


def format_list(values: Any) -> str:
    if isinstance(values, list):
        return "、".join(str(v) for v in values)
    return str(values)


def plain_value(value: Any) -> Any:
    """Convert numpy/pandas scalars into UI-friendly Python values."""
    if isinstance(value, dict):
        return {str(plain_value(k)): plain_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain_value(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            return value
    return value


def format_years(values: Any) -> str:
    years = plain_value(values)
    if not years:
        return "未标明"
    if not isinstance(years, list):
        years = [years]
    return "、".join(str(year) for year in years)


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "&#10;")
    )
