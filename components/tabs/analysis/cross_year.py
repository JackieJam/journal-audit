"""跨年交叉稽核 inner sub-tab（可疑样本库筛选 / 跨年交叉稽核）。"""

from __future__ import annotations

import hashlib

import streamlit as st

from components.charts import cross_year_findings_chart, cross_year_revenue_chart

from ._context import AnalysisContext


def render_cross_year(ctx: AnalysisContext) -> None:
    profiles = ctx.profiles
    financials = ctx.financials
    findings = ctx.findings
    income_cost_category = ctx.income_cost_category
    helpers = ctx.helpers
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _format_years = helpers["_format_years"]
    _render_cross_year_finding = helpers["_render_cross_year_finding"]
    _render_candidate_add_popover = helpers["_render_candidate_add_popover"]

    cross_main_col, cross_suggestion_col = st.columns([6, 4], gap="large")
    with cross_suggestion_col:
        st.markdown("##### 抽样建议")
        _render_candidate_recommendations_for_module(income_cost_category, module_filter="跨年交叉稽核")
    with cross_main_col:
        if len(profiles) < 2:
            st.info("💡 跨年交叉稽核需要至少上传两个年度的序时账数据。")
        else:
            st.markdown("#### 跨年收入对比趋势")
            st.plotly_chart(cross_year_revenue_chart(financials), width="stretch")

            if findings:
                st.divider()
                st.markdown(f"#### 跨年异常稽核发现 ({len(findings)})")
                st.plotly_chart(cross_year_findings_chart(findings), width="stretch")

                for f in findings:
                    severity_icon = "🔴" if f.severity == "高" else ("🟡" if f.severity == "中" else "🔵")
                    with st.expander(f"{severity_icon} [{f.category}] 涉及年份：{_format_years(f.years_involved)}", expanded=f.severity == "高"):
                        _render_cross_year_finding(f)
                        if getattr(f, "voucher_ids", None):
                            cross_detail = st.session_state.df_unified[
                                st.session_state.df_unified["凭证编号"].astype(str).isin(
                                    {str(vid) for vid in f.voucher_ids}
                                )
                            ]
                            _render_candidate_add_popover(
                                key=f"cand_cross_{f.category}_{hashlib.sha1(str(f.voucher_ids).encode('utf-8')).hexdigest()[:8]}",
                                title=f"跨年异常：{f.category}",
                                source_module="跨年交叉稽核",
                                source_view=f.category,
                                detail=cross_detail,
                                selector={
                                    "kind": "cross_year_finding",
                                    "category": f.category,
                                    "years": f.years_involved,
                                },
                                default_tags=["跨年异常"],
                                default_reason=f.description,
                            )
            else:
                st.success("✅ 跨年数据一致性校验通过，未发现显著异常。")
