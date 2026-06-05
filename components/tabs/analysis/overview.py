"""财务概况 top sub-tab（_sub_tab_top == 0）。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from components.charts import multi_year_financial_overview


def render_overview(*, financials: dict[int, Any], helpers: dict[str, Any]) -> None:
    _unified_llm_key = helpers["_unified_llm_key"]
    _render_unified_generation_controls = helpers["_render_unified_generation_controls"]

    if not financials:
        st.info("暂无财务数据。")
    else:
        overview_years = sorted(st.session_state.get("year_map", {}).keys())
        unified_key = _unified_llm_key(overview_years, income_cost_category if 'income_cost_category' in locals() else "总计")
        unified_cached = st.session_state.audit_llm_analysis.get(unified_key, {})
        overview_analysis = (unified_cached.get("overview_analysis") or {}) if isinstance(unified_cached, dict) else {}
        financial_years = sorted(financials.keys())
        latest_year = financial_years[-1]
        f_sel = financials[latest_year]

        llm_col1, llm_col2 = st.columns(2)
        with llm_col1:
            st.markdown("#### 智能综合解析")
            st.caption("一键生成智能分析并加入疑点库。")
        with llm_col2:
            _render_unified_generation_controls(income_cost_category if 'income_cost_category' in locals() else "总计")

        # ── 多年度趋势总览图 ──
        if len(financials) >= 1:
            st.plotly_chart(
                multi_year_financial_overview(financials),
                width="stretch",
                key="multi_year_financial_overview",
            )

        if overview_analysis:
            st.markdown("#### 财务概况解析")
            summary = str(overview_analysis.get("executive_summary", "")).strip()
            if summary:
                st.info(summary)
            key_risks = overview_analysis.get("key_risks", [])
            if key_risks:
                st.markdown("##### 重点风险")
                for item in key_risks:
                    st.markdown(f"- {item}")
            limitations = overview_analysis.get("data_limitations", [])
            if limitations:
                st.markdown("##### 数据限制")
                for item in limitations:
                    st.markdown(f"- {item}")
        else:
            st.info("请先在收入成本页签生成智能分析，这里会展示综合财务解析。")

        st.caption(f"综合快照范围：{'、'.join(str(year) for year in financial_years)}")

        with st.container(border=True):
            st.markdown("##### 年度财务对比摘要")
            summary_rows = []
            for year in financial_years:
                f_year = financials[year]
                rev_tot = f_year["revenue"]["total"]
                cost_tot = f_year["cost"]["total"]
                gp = f_year["gross_profit"]
                exp_total = sum(f_year.get("expenses", {}).values())
                fin_exp = f_year.get("financial_expense", 0)
                tax = f_year.get("tax_surcharge", 0)
                inv_inc = f_year.get("investment_income", 0)
                non_op_inc = f_year.get("non_operating_income", 0)
                non_op_exp = f_year.get("non_operating_expense", 0)
                net = gp - exp_total - fin_exp - tax + inv_inc + non_op_inc - non_op_exp
                summary_rows.append({
                    "年份": year,
                    "总收入": rev_tot / 1e4,
                    "总成本": cost_tot / 1e4,
                    "毛利": gp / 1e4,
                    "净利润": net / 1e4,
                    "毛利率": f_year["gross_margin"] * 100,
                    "净利率": (net / rev_tot * 100) if rev_tot > 0 else 0,
                    "研发费用率": f_year["rd_ratio"] * 100,
                })
            st.dataframe(
                pd.DataFrame(summary_rows),
                width="stretch",
                hide_index=True,
                column_config={
                    "总收入": st.column_config.NumberColumn("总收入(万)", format="%,.1f"),
                    "总成本": st.column_config.NumberColumn("总成本(万)", format="%,.1f"),
                    "毛利": st.column_config.NumberColumn("毛利(万)", format="%,.1f"),
                    "净利润": st.column_config.NumberColumn("净利润(万)", format="%,.1f"),
                    "毛利率": st.column_config.NumberColumn("毛利率", format="%.1f%%"),
                    "净利率": st.column_config.NumberColumn("净利率", format="%.1f%%"),
                    "研发费用率": st.column_config.NumberColumn("研发费用率", format="%.1f%%"),
                },
            )
