"""Tab 2 analysis section helpers."""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from components.charts import (
    ap_accrual_monthly_chart,
    ap_accrual_supplier_share_chart,
    other_receivable_monthly_chart,
    other_payable_monthly_chart,
)
from config.accounts import DEFAULT_ADJUSTMENT_KEYWORDS
from modules.visual_analysis import (
    build_ap_accrual_entry_top10_from_work,
    build_ap_accrual_supplier_comparison_from_work,
    build_other_receivable_entry_top10_from_work,
    build_other_payable_entry_top10_from_work,
)


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
        use_container_width=True,
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
            use_container_width=True,
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
            use_container_width=True,
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
        use_container_width=True,
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
            use_container_width=True,
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
        use_container_width=True,
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
            use_container_width=True,
            hide_index=True,
            column_config={
                "其他应付预提H": st.column_config.NumberColumn("其他应付预提H", format="%,.1f 万"),
                "其他应付核销S": st.column_config.NumberColumn("其他应付核销S", format="%,.1f 万"),
                "其他应付净值": st.column_config.NumberColumn("其他应付净值", format="%,.1f 万"),
            },
        )


def render_adjustment_main(
    *,
    df_audit: pd.DataFrame,
    audit_year_sel: int,
    build_adjustment_cache_fn: Callable[[pd.DataFrame, tuple[str, ...]], tuple[pd.DataFrame, pd.DataFrame]],
    selected_dataframe_row_index_fn: Callable[[Any], int | None],
    render_detail_with_actions: Callable[..., None],
) -> None:
    st.subheader("调账与反记账凭证")
    keywords = st.multiselect(
        "关键词",
        options=DEFAULT_ADJUSTMENT_KEYWORDS,
        default=DEFAULT_ADJUSTMENT_KEYWORDS,
        key=f"adjustment_keywords_{audit_year_sel}",
    )
    adj_summary, adj_detail = build_adjustment_cache_fn(df_audit, tuple(keywords))
    if adj_summary.empty:
        st.info("当前年份未发现匹配关键词或反记账标识的凭证。")
        return

    st.caption("点击表格中的行即可查看该凭证的完整分录。")
    adj_event = st.dataframe(
        adj_summary,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"adj_summary_{audit_year_sel}",
        column_config={
            "过账日期": st.column_config.DateColumn("过账日期", format="YYYY-MM-DD"),
            "借方金额": st.column_config.NumberColumn("借方金额", format="¥ %,.0f"),
            "贷方金额": st.column_config.NumberColumn("贷方金额", format="¥ %,.0f"),
            "最大行金额": st.column_config.NumberColumn("最大行金额", format="¥ %,.0f"),
        },
    )

    selected_row_index = selected_dataframe_row_index_fn(adj_event)
    if selected_row_index is None:
        selected_row_index = st.session_state.get("chart_sel_adj_row", 0)
    else:
        st.session_state["chart_sel_adj_row"] = selected_row_index

    if selected_row_index is not None and 0 <= selected_row_index < len(adj_summary):
        selected_row = adj_summary.iloc[selected_row_index]
        selected_vid = str(selected_row["凭证编号"])
        selected_date = pd.to_datetime(selected_row["过账日期"])
        detail_view = adj_detail[
            (adj_detail["凭证编号"].astype(str) == selected_vid)
            & (pd.to_datetime(adj_detail["过账日期"]) == selected_date)
        ]
        render_detail_with_actions(
            f"调账/冲销凭证 {selected_vid}",
            detail_view,
            df_source=df_audit,
            key=f"detail_adjustment_{audit_year_sel}_{selected_vid}_{selected_date:%Y%m%d}",
            source_module="调账冲销",
            source_view="调账/冲销凭证",
            selector={
                "kind": "adjustment_voucher",
                "year": audit_year_sel,
                "voucher_id": selected_vid,
                "date": selected_date.date().isoformat(),
            },
            default_tags=["冲销调账"],
            default_reason=f"凭证 {selected_vid} 命中调账/冲销关键词或反记账标识，纳入疑点库复核。",
        )
