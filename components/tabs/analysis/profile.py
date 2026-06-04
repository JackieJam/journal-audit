"""统计画像 inner sub-tab（可疑样本库筛选 / 统计画像）。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.charts import (
    amount_distribution_chart,
    benford_first_digit_chart,
    month_end_heatmap,
    monthly_trend_chart,
    profile_amount_percentile_table,
    profile_benford_table,
    profile_temporal_table,
    user_bar_chart,
    voucher_type_pie,
)
from modules import column_check

from ._context import AnalysisContext


def render_profile(ctx: AnalysisContext) -> None:
    profiles = ctx.profiles
    income_cost_category = ctx.income_cost_category
    helpers = ctx.helpers
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]

    profile_main_col, profile_suggestion_col = st.columns([6, 4], gap="large")
    with profile_suggestion_col:
        st.markdown("##### 抽样建议")
        _render_candidate_recommendations_for_module(income_cost_category, module_filter="统计画像")
    with profile_main_col:
        # ── 年份选择 ──
        year_sel = st.selectbox("选择年份", sorted(profiles.keys()), key="profile_year_sel")
        p = profiles[year_sel]
        ov = p["overview"]

        # ── 总体规模指标 ──
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总行数", f"{ov['total_rows']:,}")
        col2.metric("凭证数", f"{ov['total_vouchers']:,}")
        col3.metric("P13调整行", ov.get("period13_rows", 0))
        col4.metric("平均分录/凭证", f"{ov.get('avg_rows_per_voucher', 0):.1f}")

        st.divider()

        # ── 本福特定律（置顶） ──
        st.markdown("##### 本福特定律—首位数字分布")
        st.plotly_chart(benford_first_digit_chart(p, year_sel), use_container_width=True)
        with st.expander("本福特明细表"):
            bf_df = profile_benford_table(p)
            if not bf_df.empty:
                st.dataframe(
                    bf_df, use_container_width=True, hide_index=True,
                    column_config={
                        "首位数字": st.column_config.NumberColumn("首位数字", format="%d"),
                        "实际频率": st.column_config.NumberColumn("实际频率", format="%.2f%%"),
                        "理论频率": st.column_config.NumberColumn("理论频率", format="%.2f%%"),
                        "偏差": st.column_config.NumberColumn("偏差", format="%.2f%%"),
                    },
                )

        st.divider()

        # ── 月度趋势 ──
        st.markdown("##### 月度趋势")
        trend_view = st.radio("查看维度", ["凭证数", "金额", "双轴"],
                              index=2, horizontal=True,
                              key="profile_trend_view")
        view_map = {"凭证数": "vouchers", "金额": "amount", "双轴": "both"}
        st.plotly_chart(monthly_trend_chart(profiles, view=view_map[trend_view]),
                        use_container_width=True)
        with st.expander("月度统计明细"):
            temporal_df = profile_temporal_table(p)
            temporal_display = temporal_df.copy()
            if not temporal_display.empty:
                temporal_display["绝对金额"] = temporal_display["绝对金额"] / 1e4
                temporal_display["月末5天占比"] = temporal_display["月末5天占比"] * 100
            st.dataframe(
                temporal_display, use_container_width=True, hide_index=True,
                column_config={
                    "凭证行数": st.column_config.NumberColumn("凭证行数", format="%,d"),
                    "绝对金额": st.column_config.NumberColumn("绝对金额(万)", format="%,.1f"),
                    "月末5天占比": st.column_config.NumberColumn("月末5天占比", format="%.1f%%"),
                },
            )
        if len(profiles) > 1:
            st.plotly_chart(month_end_heatmap(profiles), use_container_width=True)

        st.divider()

        # ── 凭证类型 + 用户集中度 ──
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 凭证类型结构")
            if column_check.guard(["凭证类型"], "凭证类型结构"):
                st.plotly_chart(voucher_type_pie(p, year_sel), use_container_width=True)
                with st.expander("凭证类型明细"):
                    vt = p.get("voucher_type_structure", {})
                    vt_rows = [
                        {"类型": tn, "行数": cnt, "凭证数": vt.get("voucher_count_by_type", {}).get(tn, 0),
                         "属性": "系统" if tn in vt.get("auto", {}) else "手工/需关注"}
                        for tn, cnt in vt.get("all", {}).items()
                    ]
                    st.dataframe(pd.DataFrame(vt_rows), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("##### 用户集中度 Top10")
            if column_check.guard(["用户名"], "用户集中度分析"):
                st.plotly_chart(user_bar_chart(p, year_sel), use_container_width=True)

        # ── 金额分位数 ──
        st.divider()
        st.markdown("##### 金额分位数分布")
        st.plotly_chart(amount_distribution_chart(profiles), use_container_width=True)
        with st.expander("金额分位数明细"):
            amount_df = profile_amount_percentile_table(p)
            st.dataframe(
                amount_df, use_container_width=True, hide_index=True,
                column_config={c: st.column_config.NumberColumn(c, format="¥ %,.0f") for c in amount_df.columns if c != "年份"},
            )
