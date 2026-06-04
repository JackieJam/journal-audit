"""Tab 2 analysis section helpers."""

from __future__ import annotations

import hashlib
from typing import Any, Callable

import pandas as pd
import streamlit as st

from components.charts import (
    amount_distribution_chart,
    ap_accrual_monthly_chart,
    ap_accrual_supplier_share_chart,
    audit_income_cost_abnormal_chart,
    audit_monthly_revenue_cost_chart,
    benford_first_digit_chart,
    cross_year_expense_compare_chart,
    cross_year_findings_chart,
    cross_year_revenue_chart,
    customer_revenue_top_chart,
    month_end_heatmap,
    monthly_trend_chart,
    multi_year_financial_overview,
    other_receivable_monthly_chart,
    other_payable_monthly_chart,
    profile_amount_percentile_table,
    profile_benford_table,
    profile_temporal_table,
    supplier_payables_top_chart,
    user_bar_chart,
    voucher_type_pie,
)
from config.accounts import DEFAULT_ADJUSTMENT_KEYWORDS
from config.constants import FINANCIALS_VERSION, PROFILES_VERSION
from modules import candidate_pool as cp
from modules import column_check
from modules.cross_year import run_cross_year_analysis
from modules.profiler import build_financial_summary, build_profile
from modules.visual_analysis import (
    build_ap_accrual_entry_top10_from_work,
    build_ap_accrual_supplier_comparison_from_work,
    build_customer_revenue_entry_top10_from_work,
    build_customer_top10_from_work,
    build_expense_entry_top10_from_work,
    build_income_cost_abnormal_entry_top10_from_work,
    build_income_cost_category_options_from_work,
    build_monthly_revenue_cost_entry_top10_from_work,
    build_monthly_revenue_cost_view_from_work,
    build_other_receivable_entry_top10_from_work,
    build_other_payable_entry_top10_from_work,
    build_supplier_payable_entry_top10_from_work,
    build_supplier_top10_from_work,
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


def render_analysis_tab(main_tab=None, **helpers):
    """Render the 序时账分析 (Analysis) tab.

    从 app.py 内联抽离。依赖的 app.py 私有 helper 通过 **helpers 注入，
    与 upload/rules/sampling 页签保持一致的调用约定。
    """
    _has_project_payload = helpers["_has_project_payload"]
    _has_loaded_years = helpers["_has_loaded_years"]
    _render_missing_columns_banner = helpers["_render_missing_columns_banner"]
    _build_audit_cache = helpers["_build_audit_cache"]
    _income_page_candidate_counts = helpers["_income_page_candidate_counts"]
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _render_chart_title_with_download = helpers["_render_chart_title_with_download"]
    _selected_monthly_metric_point = helpers["_selected_monthly_metric_point"]
    _render_detail_with_actions = helpers["_render_detail_with_actions"]
    _selected_income_cost_abnormal_point = helpers["_selected_income_cost_abnormal_point"]
    _selected_bar_label = helpers["_selected_bar_label"]
    _cross_year_expense_table = helpers["_cross_year_expense_table"]
    _toggle_chart_selection = helpers["_toggle_chart_selection"]
    _selected_expense_cross_year_point = helpers["_selected_expense_cross_year_point"]
    _render_working_capital_main = helpers["_render_working_capital_main"]
    _render_adjustment_main = helpers["_render_adjustment_main"]
    _format_years = helpers["_format_years"]
    _render_cross_year_finding = helpers["_render_cross_year_finding"]
    _render_candidate_add_popover = helpers["_render_candidate_add_popover"]
    _unified_llm_key = helpers["_unified_llm_key"]
    _render_unified_generation_controls = helpers["_render_unified_generation_controls"]
    _format_money = helpers["_format_money"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]

    if main_tab is not None:
        main_tab.__enter__()

    if not (_has_project_payload() and _has_loaded_years()):
        st.info("请先在「上传数据」页签中上传序时账文件。")
        return

        st.title("📊 数据分析")
        _render_missing_columns_banner()

        needs_profiles = (
            not st.session_state.profiles
            or st.session_state.get("profiles_version") != PROFILES_VERSION
            or any("benford_first_digit" not in p for p in st.session_state.profiles.values())
        )
        needs_financials = (
            not st.session_state.financials
            or st.session_state.get("financials_version") != FINANCIALS_VERSION
        )
        if needs_profiles or needs_financials:
            progress = st.progress(0)
            status = st.empty()
            status.text("准备生成数据分析结果...")
            with st.spinner("生成统计画像…"):
                profiles = st.session_state.profiles or {}
                financials = st.session_state.financials or {}
                year_items = list(st.session_state.year_map.items())
                total_years = max(len(year_items), 1)
                for idx, (year, df_year) in enumerate(year_items, start=1):
                    status.text(f"正在处理 {year} 年数据画像与财务摘要...")
                    if needs_profiles or year not in profiles:
                        profiles[year] = build_profile(df_year, year)
                    if needs_financials or year not in financials:
                        financials[year] = build_financial_summary(df_year, year)
                    progress.progress(min(int(idx / total_years * 75), 75))
                st.session_state.profiles = profiles
                st.session_state.profiles_version = PROFILES_VERSION
                st.session_state.financials = financials
                st.session_state.financials_version = FINANCIALS_VERSION

                if needs_profiles or not st.session_state.cross_year_findings:
                    status.text("正在执行跨年交叉稽核...")
                    progress.progress(85)
                    findings = run_cross_year_analysis(st.session_state.year_map)
                    st.session_state.cross_year_findings = findings
                _autosave_current_project_state()
                status.text("数据分析完成")
                progress.progress(100)

        profiles = st.session_state.profiles
        financials = st.session_state.financials
        findings = st.session_state.cross_year_findings

        # 顶层：财务概况 / 可疑样本库筛选 / 疑点库管理（用 session_state 保持选择，图表点击后不跳回第一个）
        SUB_TABS_TOP = ["财务概况", "可疑样本库筛选", "疑点库管理"]
        if "_sub_tab_top" not in st.session_state:
            st.session_state._sub_tab_top = 0
        top_sel = st.segmented_control("", SUB_TABS_TOP, default=SUB_TABS_TOP[st.session_state._sub_tab_top],
                                        selection_mode="single", label_visibility="collapsed")
        if top_sel is not None:
            st.session_state._sub_tab_top = SUB_TABS_TOP.index(top_sel)

        if st.session_state._sub_tab_top == 1:  # 可疑样本库筛选
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

            if st.session_state._sub_tab_inner == 0:  # 收入成本
                category_key = hashlib.sha1(str(income_cost_category).encode("utf-8")).hexdigest()[:8]
                candidate_counts = _income_page_candidate_counts(audit_year_sel, income_cost_category)
                main_col, suggestion_col = st.columns([6, 4], gap="large")

                with suggestion_col:
                    st.markdown("##### 抽样建议")
                    st.caption("统一生成各模块模型建议，可批量应用到疑点库。")
                    _render_candidate_recommendations_for_module(income_cost_category, module_filter="收入成本")

                with main_col:
                    _render_chart_title_with_download(
                        "月度收入成本",
                        df=monthly_view,
                        file_name=f"{audit_year_sel}_{income_cost_category}_monthly_income_cost.xlsx",
                        key=f"download_monthly_income_cost_{audit_year_sel}_{category_key}",
                        sheet_name="月度收入成本",
                    )
                    st.caption("点击柱状图或折线点后，下面会按所选月份回查全量分录，并可加入疑点库。")
                    monthly_income_cost_event = st.plotly_chart(
                        audit_monthly_revenue_cost_chart(
                            monthly_view,
                            audit_year_sel,
                            income_cost_category,
                            sample_counts=candidate_counts["month"],
                        ),
                        use_container_width=True,
                        key=f"monthly_income_cost_chart_{audit_year_sel}_{category_key}",
                        on_select="rerun",
                        selection_mode="points",
                    )
                    monthly_income_cost_point = _selected_monthly_metric_point(
                        monthly_income_cost_event,
                        {0: "revenue", 1: "cost", 2: "gross"},
                    )

                    if monthly_income_cost_point is None:

                        monthly_income_cost_point = st.session_state.get("chart_sel_monthly_income_cost")

                    else:

                        st.session_state["chart_sel_monthly_income_cost"] = monthly_income_cost_point
                    if monthly_income_cost_point:
                        monthly_detail_month, monthly_metric = monthly_income_cost_point
                        monthly_metric_label = {
                            "revenue": "净收入",
                            "cost": "净成本",
                            "gross": "毛利",
                        }.get(monthly_metric, "月度")
                        monthly_entries = build_monthly_revenue_cost_entry_top10_from_work(
                            audit_work,
                            month=monthly_detail_month,
                            metric=monthly_metric,
                            category=income_cost_category,
                        )
                        _render_detail_with_actions(

                            f"{audit_year_sel}年{monthly_detail_month}月 {income_cost_category} {monthly_metric_label}金额全量分录",

                            monthly_entries,

                            df_source=df_audit,

                            key=f"chart_panel_monthly_{audit_year_sel}_{monthly_detail_month}_{monthly_metric}_{category_key}",

                            source_module="收入成本",

                            source_view="月度收入成本",

                            selector={
                                "kind": "monthly_income_cost",
                                "year": audit_year_sel,
                                "month": monthly_detail_month,
                                "metric": monthly_metric,
                                "category": income_cost_category,
                            },

                            default_reason=f"从月度收入成本图选择 {audit_year_sel}年{monthly_detail_month}月 {monthly_metric_label}，纳入疑点库复核。",

                        )

                    abnormal_export = monthly_view.loc[
                        :,
                        [col for col in ["月份", "收入S影响", "成本H影响"] if col in monthly_view.columns],
                    ].copy()
                    _render_chart_title_with_download(
                        "异常方向",
                        df=abnormal_export,
                        file_name=f"{audit_year_sel}_{income_cost_category}_abnormal_direction.xlsx",
                        key=f"download_abnormal_direction_{audit_year_sel}_{category_key}",
                        sheet_name="异常方向",
                    )
                    abnormal_event = st.plotly_chart(
                        audit_income_cost_abnormal_chart(
                            monthly_view,
                            audit_year_sel,
                            income_cost_category,
                            sample_counts=candidate_counts["month"],
                        ),
                        use_container_width=True,
                        key=f"income_cost_abnormal_chart_{audit_year_sel}_{category_key}",
                        on_select="rerun",
                        selection_mode="points",
                    )
                    abnormal_point = _selected_income_cost_abnormal_point(abnormal_event)

                    if abnormal_point is None:

                        abnormal_point = st.session_state.get("chart_sel_abnormal")

                    else:

                        st.session_state["chart_sel_abnormal"] = abnormal_point
                    if abnormal_point:
                        abnormal_month, abnormal_direction = abnormal_point
                        abnormal_label = "收入S" if abnormal_direction == "income_s" else "成本H"
                        abnormal_entries = build_income_cost_abnormal_entry_top10_from_work(
                            audit_work,
                            month=abnormal_month,
                            direction=abnormal_direction,
                            category=income_cost_category,
                        )
                        _render_detail_with_actions(

                            f"{audit_year_sel}年{abnormal_month}月 {income_cost_category} {abnormal_label}金额全量分录",

                            abnormal_entries,

                            df_source=df_audit,

                            key=f"chart_panel_abnormal_{audit_year_sel}_{abnormal_month}_{abnormal_direction}_{category_key}",

                            source_module="收入成本",

                            source_view="异常方向",

                            selector={
                                "kind": "income_cost_abnormal",
                                "year": audit_year_sel,
                                "month": abnormal_month,
                                "direction": abnormal_direction,
                                "category": income_cost_category,
                            },

                            default_reason=f"{abnormal_label} 属于收入成本异常方向金额，纳入疑点库复核。",

                        )

                    st.divider()
                    if column_check.guard(["客户"], "客户收入分析"):
                        customer_top15 = build_customer_top10_from_work(audit_work, top_n=15)
                        _render_chart_title_with_download(
                            "客户收入",
                            df=customer_top15,
                            file_name=f"{audit_year_sel}_{income_cost_category}_customer_revenue_top15.xlsx",
                            key=f"download_customer_top15_{audit_year_sel}_{category_key}",
                            sheet_name="客户收入",
                        )
                        st.caption("客户对应收入。保留前 15 大客户，点击柱状图后展示该客户全部收入分录。")
                        if customer_top15.empty:
                            st.info("当前口径下暂无可按客户归集的收入。")
                        else:
                            customer_top15.attrs["sample_counts"] = candidate_counts["customer"]
                            customer_event = st.plotly_chart(
                                customer_revenue_top_chart(customer_top15, audit_year_sel),
                                use_container_width=True,
                                key=f"income_page_customer_chart_{audit_year_sel}_{category_key}",
                                on_select="rerun",
                                selection_mode="points",
                            )
                            selected_customer = _selected_bar_label(customer_event)

                            if selected_customer is None:

                                selected_customer = st.session_state.get("chart_sel_customer")

                            else:

                                st.session_state["chart_sel_customer"] = selected_customer
                            if selected_customer:
                                customer_entries = build_customer_revenue_entry_top10_from_work(audit_work, selected_customer)
                                _render_detail_with_actions(

                                    f"{audit_year_sel}年 {selected_customer} 收入全量分录",

                                    customer_entries,

                                    df_source=df_audit,

                                    key=f"chart_panel_customer_{audit_year_sel}_{selected_customer}_{category_key}",

                                    source_module="收入成本",

                                    source_view="客户收入",

                                    selector={
                                        "kind": "customer_revenue",
                                        "year": audit_year_sel,
                                        "customer": selected_customer,
                                        "category": income_cost_category,
                                    },

                                    default_reason=f"客户 {selected_customer} 收入被选中，纳入疑点库复核。",

                                )

                    st.divider()
                    if column_check.guard(["供应商编号"], "供应商应付分析"):
                        supplier_top15 = build_supplier_top10_from_work(audit_work, top_n=15)
                        _render_chart_title_with_download(
                            "供应商应付账款",
                            df=supplier_top15,
                            file_name=f"{audit_year_sel}_{income_cost_category}_supplier_payable_top15.xlsx",
                            key=f"download_supplier_top15_{audit_year_sel}_{category_key}",
                            sheet_name="供应商应付",
                        )
                        st.caption("成本供应商统一使用应付账款供应商口径。保留前 15 大供应商，点击柱状图后展示该供应商全部应付分录。")
                        if supplier_top15.empty:
                            st.info("当前口径下暂无可按供应商归集的应付账款数据。")
                        else:
                            supplier_top15.attrs["sample_counts"] = candidate_counts["supplier"]
                            supplier_event = st.plotly_chart(
                                supplier_payables_top_chart(supplier_top15, audit_year_sel),
                                use_container_width=True,
                                key=f"income_page_supplier_chart_{audit_year_sel}_{category_key}",
                                on_select="rerun",
                                selection_mode="points",
                            )
                            selected_supplier = _selected_bar_label(supplier_event)

                            if selected_supplier is None:

                                selected_supplier = st.session_state.get("chart_sel_supplier")

                            else:

                                st.session_state["chart_sel_supplier"] = selected_supplier
                            if selected_supplier:
                                supplier_entries = build_supplier_payable_entry_top10_from_work(audit_work, selected_supplier)
                                _render_detail_with_actions(

                                    f"{audit_year_sel}年 {selected_supplier} 供应商应付全量分录",

                                    supplier_entries,

                                    df_source=df_audit,

                                    key=f"chart_panel_supplier_{audit_year_sel}_{selected_supplier}_{category_key}",

                                    source_module="收入成本",

                                    source_view="供应商应付",

                                    selector={
                                        "kind": "supplier_payable",
                                        "year": audit_year_sel,
                                        "supplier": selected_supplier,
                                        "category": income_cost_category,
                                    },

                                    default_reason=f"供应商 {selected_supplier} 应付交易被选中，作为成本相关口径纳入疑点库复核。",

                                )

            if st.session_state._sub_tab_inner == 1:  # 费用
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
                                use_container_width=True,
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
                                        use_container_width=True,
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

            if st.session_state._sub_tab_inner == 2:  # 暂估往来
                working_main_col, working_suggestion_col = st.columns([6, 4], gap="large")
                with working_suggestion_col:
                    st.markdown("##### 抽样建议")
                    _render_candidate_recommendations_for_module(income_cost_category, module_filter="暂估往来")

                with working_main_col:
                    _render_working_capital_main(
                        audit_cache=audit_cache,
                        audit_work=audit_work,
                        audit_year_sel=audit_year_sel,
                    )

            if st.session_state._sub_tab_inner == 3:  # 调账冲销
                adjustment_main_col, adjustment_suggestion_col = st.columns([6, 4], gap="large")
                with adjustment_suggestion_col:
                    st.markdown("##### 抽样建议")
                    _render_candidate_recommendations_for_module(income_cost_category, module_filter="调账冲销")

                with adjustment_main_col:
                    if column_check.guard(["文本"], "调账/冲销凭证识别"):
                        _render_adjustment_main(df_audit=df_audit, audit_year_sel=audit_year_sel)

            if st.session_state._sub_tab_inner == 4:  # 跨年交叉稽核
                cross_main_col, cross_suggestion_col = st.columns([6, 4], gap="large")
                with cross_suggestion_col:
                    st.markdown("##### 抽样建议")
                    _render_candidate_recommendations_for_module(income_cost_category, module_filter="跨年交叉稽核")
                with cross_main_col:
                    if len(profiles) < 2:
                        st.info("💡 跨年交叉稽核需要至少上传两个年度的序时账数据。")
                    else:
                        st.markdown("#### 跨年收入对比趋势")
                        st.plotly_chart(cross_year_revenue_chart(financials), use_container_width=True)

                        if findings:
                            st.divider()
                            st.markdown(f"#### 跨年异常稽核发现 ({len(findings)})")
                            st.plotly_chart(cross_year_findings_chart(findings), use_container_width=True)

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

            if st.session_state._sub_tab_inner == 5:  # 统计画像
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
        if st.session_state._sub_tab_top == 0:  # 财务概况
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
                        use_container_width=True,
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
                        use_container_width=True,
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
        # ── 疑点库管理 ──
        if st.session_state._sub_tab_top == 2:  # 疑点库管理
            pool = st.session_state.get("candidate_pool", [])
            stats = cp.pool_stats(pool)

            st.markdown("#### 候选池概览")
            stat_cols = st.columns(5)
            stat_cols[0].metric("候选群体", stats["groups"])
            stat_cols[1].metric("有效群体", stats["active_groups"])
            stat_cols[2].metric("有效凭证", stats["active_vouchers"])
            stat_cols[3].metric("人工直入凭证", stats["manual_final_vouchers"])
            stat_cols[4].metric("总金额", _format_money(stats["amount_total"]))

            if not pool:
                st.info("候选池为空。请先在「可疑样本库筛选」中通过图表交互或模型建议将疑点凭证加入候选池。")
            else:
                st.divider()
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    status_options = ["全部"] + list({g.get("status", "active") for g in pool})
                    status_filter = st.selectbox("按状态筛选", status_options, key="pool_status_filter")
                with filter_col2:
                    module_options = ["全部"] + list({g.get("source_module", "未知") for g in pool})
                    module_filter = st.selectbox("按来源模块筛选", module_options, key="pool_module_filter")

                filtered = pool
                if status_filter != "全部":
                    filtered = [g for g in filtered if g.get("status", "active") == status_filter]
                if module_filter != "全部":
                    filtered = [g for g in filtered if g.get("source_module", "未知") == module_filter]

                groups_df = cp.groups_to_table(filtered)
                if groups_df.empty:
                    st.info("当前筛选条件下没有匹配的疑点群体。")
                else:
                    display_cols = [c for c in groups_df.columns if c != "group_id"]
                    st.dataframe(groups_df[display_cols], use_container_width=True, hide_index=True)

                    st.divider()
                    st.markdown("#### 批量操作")

                    def _fmt_gid(gid):
                        for g in filtered:
                            if g["group_id"] == gid:
                                s = g.get("status", "?")
                                t = g.get("title", "")
                                vc = g.get("voucher_count", 0)
                                return f"[{s}] {t} ({vc}凭证)"
                        return gid

                    selected_ids = st.multiselect(
                        "选择群体进行批量操作",
                        options=[g["group_id"] for g in filtered],
                        format_func=_fmt_gid,
                        key="pool_batch_select",
                    )

                    if selected_ids:
                        batch_col1, batch_col2, batch_col3 = st.columns(3)
                        with batch_col1:
                            if st.button("标记为已审核", use_container_width=True, key="pool_mark_reviewed"):
                                for gid in selected_ids:
                                    st.session_state.candidate_pool = cp.update_candidate_status(
                                        st.session_state.candidate_pool, gid, "reviewed"
                                    )
                                _autosave_current_project_state()
                                st.rerun()
                        with batch_col2:
                            if st.button("排除选中群体", use_container_width=True, key="pool_mark_excluded"):
                                for gid in selected_ids:
                                    st.session_state.candidate_pool = cp.update_candidate_status(
                                        st.session_state.candidate_pool, gid, "excluded"
                                    )
                                _autosave_current_project_state()
                                st.rerun()
                        with batch_col3:
                            if st.button("移除选中群体", type="secondary", use_container_width=True, key="pool_remove_selected"):
                                for gid in selected_ids:
                                    st.session_state.candidate_pool = cp.remove_candidate_group(
                                        st.session_state.candidate_pool, gid
                                    )
                                _autosave_current_project_state()
                                st.rerun()

