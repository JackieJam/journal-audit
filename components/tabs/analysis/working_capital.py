"""暂估往来 inner sub-tab + 营运资本主体渲染。"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from components.charts import (
    ap_accrual_monthly_chart,
    ap_accrual_supplier_share_chart,
    other_payable_monthly_chart,
    other_receivable_monthly_chart,
)
from modules.visual_analysis import (
    build_ap_accrual_entry_top10_from_work,
    build_ap_accrual_supplier_comparison_from_work,
    build_other_payable_entry_top10_from_work,
    build_other_receivable_entry_top10_from_work,
)

from ._context import AnalysisContext


def render_working_capital_main(
    *,
    audit_cache: dict[str, pd.DataFrame],
    audit_work: pd.DataFrame,
    audit_year_sel: int,
    year_map: dict[int, pd.DataFrame],
    render_detail_with_actions: Callable[..., None],
    selected_ap_accrual_point_fn: Callable[[Any], tuple[int, str] | None],
    selected_bar_label_and_direction_fn: Callable[[Any, dict[int, str]], tuple[str, str] | None],
    selected_monthly_metric_point_fn: Callable[[Any, dict[int, str]], tuple[int, str] | None],
) -> None:
    ap_accrual_monthly = audit_cache["ap_accrual"]
    ap_accrual_event = st.plotly_chart(
        ap_accrual_monthly_chart(ap_accrual_monthly, audit_year_sel),
        width="stretch",
        key=f"ap_accrual_monthly_chart_{audit_year_sel}",
        on_select="rerun",
        selection_mode="points",
    )
    ap_point = selected_ap_accrual_point_fn(ap_accrual_event)
    if ap_point:
        ap_month, ap_direction = ap_point
        direction_label = {
            "credit": "暂估贷方增加",
            "debit": "暂估借方减少",
            "net": "暂估净额",
        }.get(ap_direction, "暂估净额")
        ap_entries = build_ap_accrual_entry_top10_from_work(
            audit_work,
            month=ap_month,
            direction=ap_direction,
        )
        render_detail_with_actions(
            f"{audit_year_sel}年{ap_month}月 {direction_label}金额全量分录",
            ap_entries,
            df_source=year_map[audit_year_sel],
            key=f"detail_ap_month_{audit_year_sel}_{ap_month}_{ap_direction}",
            source_module="暂估往来",
            source_view="暂估月度",
            selector={"kind": "ap_accrual_month", "year": audit_year_sel, "month": ap_month, "direction": ap_direction},
            amount_cols=["暂估贷方增加", "暂估借方减少", "暂估净额影响"],
            default_tags=["暂估异常", "月度"],
            default_reason=f"应付暂估 {direction_label} 月度金额被选中，纳入疑点库复核。",
        )

        ap_share = build_ap_accrual_supplier_comparison_from_work(
            audit_work,
            month=ap_month,
            sort_by=ap_direction,
        )
        ap_supplier_event = st.plotly_chart(
            ap_accrual_supplier_share_chart(
                ap_share,
                f"{audit_year_sel}年{ap_month}月 应付账款暂估供应商对比（按{direction_label}排序）",
            ),
            width="stretch",
            key=f"ap_accrual_supplier_chart_{audit_year_sel}_{ap_month}_{ap_direction}",
            on_select="rerun",
            selection_mode="points",
        )
        ap_supplier_point = selected_bar_label_and_direction_fn(
            ap_supplier_event,
            {0: "credit", 1: "debit", 2: "net"},
        )

        if ap_supplier_point is None:
            ap_supplier_point = st.session_state.get("chart_sel_ap_supplier")
        else:
            st.session_state["chart_sel_ap_supplier"] = ap_supplier_point
        if ap_supplier_point:
            ap_supplier, ap_supplier_direction = ap_supplier_point
            ap_supplier_direction_label = {
                "credit": "暂估贷方增加",
                "debit": "暂估借方减少",
                "net": "暂估净额",
            }.get(ap_supplier_direction, "暂估净额")
            ap_supplier_entries = build_ap_accrual_entry_top10_from_work(
                audit_work,
                month=ap_month,
                direction=ap_supplier_direction,
                supplier=ap_supplier,
            )
            render_detail_with_actions(
                f"{audit_year_sel}年{ap_month}月 {ap_supplier_direction_label}供应商 {ap_supplier} 金额全量分录",
                ap_supplier_entries,
                df_source=year_map[audit_year_sel],
                source_module="暂估往来",
                source_view="暂估供应商",
                selector={
                    "kind": "ap_accrual_supplier",
                    "year": audit_year_sel,
                    "month": ap_month,
                    "supplier": ap_supplier,
                    "direction": ap_supplier_direction,
                },
                default_tags=["暂估异常", "供应商"],
                default_reason=f"暂估供应商 {ap_supplier} 被选中，纳入疑点库复核。",
            )

        ap_share_display = ap_share.copy()
        if not ap_share_display.empty:
            ap_amount_cols = ["暂估贷方增加", "暂估借方减少", "暂估净额"]
            ap_ratio_cols = ["贷方占比", "借方占比", "净额占比"]
            ap_share_display[ap_amount_cols] = ap_share_display[ap_amount_cols] / 1e4
            ap_share_display[ap_ratio_cols] = ap_share_display[ap_ratio_cols] * 100
        st.dataframe(
            ap_share_display,
            width="stretch",
            hide_index=True,
            column_config={
                "暂估贷方增加": st.column_config.NumberColumn("暂估贷方增加", format="%,.1f 万"),
                "暂估借方减少": st.column_config.NumberColumn("暂估借方减少", format="%,.1f 万"),
                "暂估净额": st.column_config.NumberColumn("暂估净额", format="%,.1f 万"),
                "贷方占比": st.column_config.NumberColumn("贷方占比", format="%.1%%"),
                "借方占比": st.column_config.NumberColumn("借方占比", format="%.1%%"),
                "净额占比": st.column_config.NumberColumn("净额占比", format="%.1%%"),
            },
        )

    other_receivable_monthly = audit_cache["other_receivable"]
    other_receivable_event = st.plotly_chart(
        other_receivable_monthly_chart(other_receivable_monthly, audit_year_sel),
        width="stretch",
        key=f"other_receivable_monthly_chart_{audit_year_sel}",
        on_select="rerun",
        selection_mode="points",
    )
    other_receivable_point = selected_monthly_metric_point_fn(
        other_receivable_event,
        {0: "debit", 1: "credit", 2: "net"},
    )

    if other_receivable_point is None:
        other_receivable_point = st.session_state.get("chart_sel_other_receivable")
    else:
        st.session_state["chart_sel_other_receivable"] = other_receivable_point
    if other_receivable_point:
        other_receivable_month, other_receivable_direction = other_receivable_point
        other_receivable_label = {
            "debit": "其他应收S发生额",
            "credit": "其他应收H发生额",
            "net": "其他应收净额",
        }.get(other_receivable_direction, "其他应收")
        other_receivable_entries = build_other_receivable_entry_top10_from_work(
            audit_work,
            month=other_receivable_month,
            direction=other_receivable_direction,
        )
        render_detail_with_actions(
            f"{audit_year_sel}年{other_receivable_month}月 {other_receivable_label}金额全量分录",
            other_receivable_entries,
            df_source=year_map[audit_year_sel],
            source_module="暂估往来",
            source_view="其他应收",
            selector={
                "kind": "other_receivable_month",
                "year": audit_year_sel,
                "month": other_receivable_month,
                "direction": other_receivable_direction,
            },
            default_tags=["往来异常", "月度"],
            default_reason=f"其他应收 {other_receivable_label} 被选中，纳入疑点库复核。",
        )

    with st.expander("其他应收款月度明细"):
        other_receivable_display = other_receivable_monthly.copy()
        other_receivable_amount_cols = ["其他应收S发生额", "其他应收H发生额", "其他应收净额"]
        if not other_receivable_display.empty:
            other_receivable_display[other_receivable_amount_cols] = (
                other_receivable_display[other_receivable_amount_cols] / 1e4
            )
        st.dataframe(
            other_receivable_display,
            width="stretch",
            hide_index=True,
            column_config={
                "其他应收S发生额": st.column_config.NumberColumn("其他应收S发生额", format="%,.1f 万"),
                "其他应收H发生额": st.column_config.NumberColumn("其他应收H发生额", format="%,.1f 万"),
                "其他应收净额": st.column_config.NumberColumn("其他应收净额", format="%,.1f 万"),
            },
        )

    other_payable_monthly = audit_cache["other_payable"]
    other_payable_event = st.plotly_chart(
        other_payable_monthly_chart(other_payable_monthly, audit_year_sel),
        width="stretch",
        key=f"other_payable_monthly_chart_{audit_year_sel}",
        on_select="rerun",
        selection_mode="points",
    )
    other_payable_point = selected_monthly_metric_point_fn(
        other_payable_event,
        {0: "accrual", 1: "writeoff", 2: "net"},
    )

    if other_payable_point is None:
        other_payable_point = st.session_state.get("chart_sel_other_payable")
    else:
        st.session_state["chart_sel_other_payable"] = other_payable_point
    if other_payable_point:
        other_payable_month, other_payable_direction = other_payable_point
        other_payable_label = {
            "accrual": "其他应付预提H",
            "writeoff": "其他应付核销S",
            "net": "其他应付净值",
        }.get(other_payable_direction, "其他应付")
        other_payable_entries = build_other_payable_entry_top10_from_work(
            audit_work,
            month=other_payable_month,
            direction=other_payable_direction,
        )
        render_detail_with_actions(
            f"{audit_year_sel}年{other_payable_month}月 {other_payable_label}金额全量分录",
            other_payable_entries,
            df_source=year_map[audit_year_sel],
            source_module="暂估往来",
            source_view="其他应付",
            selector={
                "kind": "other_payable_month",
                "year": audit_year_sel,
                "month": other_payable_month,
                "direction": other_payable_direction,
            },
            default_tags=["往来异常", "月度"],
            default_reason=f"其他应付 {other_payable_label} 被选中，纳入疑点库复核。",
        )

    with st.expander("其他应付款月度明细"):
        other_payable_display = other_payable_monthly.copy()
        other_payable_amount_cols = ["其他应付预提H", "其他应付核销S", "其他应付净值"]
        if not other_payable_display.empty:
            other_payable_display[other_payable_amount_cols] = (
                other_payable_display[other_payable_amount_cols] / 1e4
            )
        st.dataframe(
            other_payable_display,
            width="stretch",
            hide_index=True,
            column_config={
                "其他应付预提H": st.column_config.NumberColumn("其他应付预提H", format="%,.1f 万"),
                "其他应付核销S": st.column_config.NumberColumn("其他应付核销S", format="%,.1f 万"),
                "其他应付净值": st.column_config.NumberColumn("其他应付净值", format="%,.1f 万"),
            },
        )


def render_working_capital(ctx: AnalysisContext) -> None:
    helpers = ctx.helpers
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _render_working_capital_main = helpers["_render_working_capital_main"]
    income_cost_category = ctx.income_cost_category

    working_main_col, working_suggestion_col = st.columns([6, 4], gap="large")
    with working_suggestion_col:
        st.markdown("##### 抽样建议")
        _render_candidate_recommendations_for_module(income_cost_category, module_filter="暂估往来")

    with working_main_col:
        _render_working_capital_main(
            audit_cache=ctx.audit_cache,
            audit_work=ctx.audit_work,
            audit_year_sel=ctx.audit_year_sel,
        )
