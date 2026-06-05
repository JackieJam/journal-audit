"""费用 inner sub-tab（可疑样本库筛选 / 费用）。"""

from __future__ import annotations

import streamlit as st

from components.charts import cross_year_expense_compare_chart
from modules.visual_analysis import build_expense_entry_top10_from_work

from ._context import AnalysisContext


def render_expense(ctx: AnalysisContext) -> None:
    audit_year_sel = ctx.audit_year_sel
    income_cost_category = ctx.income_cost_category
    financials = ctx.financials
    helpers = ctx.helpers
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _cross_year_expense_table = helpers["_cross_year_expense_table"]
    _render_chart_title_with_download = helpers["_render_chart_title_with_download"]
    _toggle_chart_selection = helpers["_toggle_chart_selection"]
    _selected_expense_cross_year_point = helpers["_selected_expense_cross_year_point"]
    _build_audit_cache = helpers["_build_audit_cache"]
    _render_detail_with_actions = helpers["_render_detail_with_actions"]

    f_audit = financials.get(audit_year_sel)
    if not f_audit:
        st.info("当前年份暂无费用数据。")
    else:
        expense_main_col, expense_suggestion_col = st.columns([6.5, 3.5], gap="large")
        with expense_suggestion_col:
            st.markdown("##### 抽样建议")
            _render_candidate_recommendations_for_module(income_cost_category, module_filter="费用")

        with expense_main_col:
            cross_year_expense_df = _cross_year_expense_table(financials)
            if not cross_year_expense_df.empty:
                cross_year_expense_nonce = st.session_state.get("chart_sel_cross_year_expense_nonce", 0)
                _render_chart_title_with_download(
                    "同一费用跨年对比",
                    df=cross_year_expense_df,
                    file_name="cross_year_expense_compare.xlsx",
                    key=f"download_cross_year_expense_compare_{audit_year_sel}",
                    sheet_name="跨年费用对比",
                )
                st.caption("金额单位：元 | 括号内为各费用类别同年占比 | 点击费用类别可回查明细")
                cross_year_expense_event = st.plotly_chart(
                    cross_year_expense_compare_chart(cross_year_expense_df),
                    width="stretch",
                    key=f"cross_year_expense_compare_chart_{audit_year_sel}_{cross_year_expense_nonce}",
                    on_select="rerun",
                    selection_mode="points",
                )
                cross_year_expense_point = _toggle_chart_selection(
                    "chart_sel_cross_year_expense",
                    _selected_expense_cross_year_point(cross_year_expense_event),
                )
                if cross_year_expense_point:
                    clear_col, _ = st.columns([1, 5])
                    with clear_col:
                        if st.button(
                            "✗ 清空当前明细",
                            key=f"clear_cross_year_expense_{audit_year_sel}",
                            width="stretch",
                        ):
                            st.session_state.pop("chart_sel_cross_year_expense", None)
                            st.session_state["chart_sel_cross_year_expense_nonce"] = cross_year_expense_nonce + 1
                            st.rerun()
                if cross_year_expense_point:
                    compare_year, compare_category = cross_year_expense_point
                    compare_work = _build_audit_cache(st.session_state.year_map[compare_year])["work"]
                    compare_entries = build_expense_entry_top10_from_work(compare_work, compare_category)
                    _render_detail_with_actions(

                        f"{compare_year}年 {compare_category}金额全量分录",

                        compare_entries,

                        df_source=st.session_state.year_map[compare_year],

                        key=f"chart_panel_cross_year_expense_{compare_year}_{compare_category}",

                        source_module="费用",

                        source_view="费用类别",

                        selector={
                            "kind": "expense_category",
                            "year": compare_year,
                            "expense_category": compare_category,
                        },

                        default_reason=f"跨年费用图中 {compare_category} 在 {compare_year} 年被选中，纳入疑点库复核。",

                    )
                # 费用明细已整合到上面「同一费用跨年对比」图表中，可通过点击跨年图回查各年度明细。
