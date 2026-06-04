"""调账冲销 inner sub-tab + 调账/反记账主体渲染。"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from config.accounts import DEFAULT_ADJUSTMENT_KEYWORDS
from modules import column_check

from ._context import AnalysisContext


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


def render_adjustment(ctx: AnalysisContext) -> None:
    helpers = ctx.helpers
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _render_adjustment_main = helpers["_render_adjustment_main"]
    income_cost_category = ctx.income_cost_category

    adjustment_main_col, adjustment_suggestion_col = st.columns([6, 4], gap="large")
    with adjustment_suggestion_col:
        st.markdown("##### 抽样建议")
        _render_candidate_recommendations_for_module(income_cost_category, module_filter="调账冲销")

    with adjustment_main_col:
        if column_check.guard(["文本"], "调账/冲销凭证识别"):
            _render_adjustment_main(df_audit=ctx.df_audit, audit_year_sel=ctx.audit_year_sel)
