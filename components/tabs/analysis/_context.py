"""Shared render context for the 序时账分析 sub-tabs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class AnalysisContext:
    """运营资本/收入成本等内层页签共享的渲染上下文。

    把页签真正入口在 setup 阶段计算出的本地状态打包传给各子渲染函数，
    避免每个子函数都重复一长串 keyword 参数。helpers 仍是 app.py 注入的私有 helper 字典。
    """

    audit_year_sel: int
    df_audit: pd.DataFrame
    audit_cache: dict[str, pd.DataFrame]
    audit_work: pd.DataFrame
    income_cost_category: str
    monthly_view: pd.DataFrame
    financials: dict[int, Any]
    profiles: dict[int, Any]
    findings: list[Any]
    helpers: dict[str, Any]
