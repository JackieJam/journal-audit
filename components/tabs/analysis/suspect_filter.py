"""可疑样本库筛选 top sub-tab（_sub_tab_top == 1）：年份/口径/KPI + 内层分发。"""

from __future__ import annotations

from typing import Any

import streamlit as st

from modules.visual_analysis import (
    build_income_cost_category_options_from_work,
    build_monthly_revenue_cost_view_from_work,
)

from ._context import AnalysisContext
from .adjustment import render_adjustment
from .cross_year import render_cross_year
from .expense import render_expense
from .income_cost import render_income_cost
from .profile import render_profile
from .working_capital import render_working_capital


def render_suspect_filter(
    *,
    financials: dict[int, Any],
    profiles: dict[int, Any],
    findings: list[Any],
    helpers: dict[str, Any],
) -> None:
    _build_audit_cache = helpers["_build_audit_cache"]

    ctl_year, ctl_cat, ctl_kpi1, ctl_kpi2, ctl_kpi3, ctl_kpi4 = st.columns([1, 1.5, 0.8, 0.8, 0.8, 0.8])
    with ctl_year:
        audit_year_sel = st.selectbox("年份", sorted(st.session_state.year_map.keys()), key="audit_year_sel")
    df_audit = st.session_state.year_map[audit_year_sel]
    audit_cache = _build_audit_cache(df_audit)
    audit_work = audit_cache["work"]

    income_cost_options = build_income_cost_category_options_from_work(audit_work)
    with ctl_cat:
        income_cost_category = st.selectbox(
            "口径", income_cost_options,
            key=f"income_cost_category_{audit_year_sel}",
        )
        full_scope = st.toggle(
            "全口径（含费用）",
            value=False,
            key=f"income_cost_full_scope_{audit_year_sel}",
            help="开启后 KPI 显示净收入 / 净成本 / 总费用 / 营业利润，凸显费用对利润的侵蚀",
        )

    monthly_view = (
        audit_cache["monthly"]
        if income_cost_category == "总计"
        else build_monthly_revenue_cost_view_from_work(audit_work, category=income_cost_category)
    )
    total_income_h = monthly_view["收入H影响"].sum()
    total_income_s = monthly_view["收入S影响"].sum()
    total_cost_s = monthly_view["成本S影响"].sum()
    total_cost_h = monthly_view["成本H影响"].sum()

    net_revenue = -(total_income_h + total_income_s)
    net_cost = total_cost_s + total_cost_h  # 显示成本本身的正值
    gross_profit = net_revenue - net_cost
    net_expense = float(monthly_view["净费用"].sum()) if "净费用" in monthly_view.columns else 0.0
    operating_profit = gross_profit - net_expense

    if full_scope:
        with ctl_kpi1:
            st.metric("净收入", f"{net_revenue/1e4:,.0f}万")
        with ctl_kpi2:
            st.metric("净成本", f"{net_cost/1e4:,.0f}万")
        with ctl_kpi3:
            st.metric("总费用", f"{net_expense/1e4:,.0f}万")
        with ctl_kpi4:
            st.metric(
                "营业利润",
                f"{operating_profit/1e4:,.0f}万",
                delta=f"{(operating_profit-gross_profit)/1e4:,.0f}万 vs 毛利",
                delta_color="off",
            )
    else:
        with ctl_kpi1:
            st.metric("净收入", f"{net_revenue/1e4:,.0f}万")
        with ctl_kpi2:
            st.metric("净成本", f"{net_cost/1e4:,.0f}万")
        with ctl_kpi3:
            st.metric("毛利", f"{gross_profit/1e4:,.0f}万")
        with ctl_kpi4:
            voucher_cnt = len(monthly_view) if hasattr(monthly_view, '__len__') else 0
            st.metric("月数", voucher_cnt)

    SUB_TABS_INNER = ["收入成本", "费用", "暂估往来", "调账冲销", "跨年交叉稽核", "统计画像"]
    if "_sub_tab_inner" not in st.session_state:
        st.session_state._sub_tab_inner = 0
    active_inner = st.segmented_control("", SUB_TABS_INNER, default=SUB_TABS_INNER[st.session_state._sub_tab_inner],
                                          selection_mode="single", label_visibility="collapsed")
    if active_inner is not None:
        st.session_state._sub_tab_inner = SUB_TABS_INNER.index(active_inner)

    ctx = AnalysisContext(
        audit_year_sel=audit_year_sel,
        df_audit=df_audit,
        audit_cache=audit_cache,
        audit_work=audit_work,
        income_cost_category=income_cost_category,
        monthly_view=monthly_view,
        financials=financials,
        profiles=profiles,
        findings=findings,
        helpers=helpers,
    )

    if st.session_state._sub_tab_inner == 0:  # 收入成本
        render_income_cost(ctx)
    if st.session_state._sub_tab_inner == 1:  # 费用
        render_expense(ctx)
    if st.session_state._sub_tab_inner == 2:  # 暂估往来
        render_working_capital(ctx)
    if st.session_state._sub_tab_inner == 3:  # 调账冲销
        render_adjustment(ctx)
    if st.session_state._sub_tab_inner == 4:  # 跨年交叉稽核
        render_cross_year(ctx)
    if st.session_state._sub_tab_inner == 5:  # 统计画像
        render_profile(ctx)
