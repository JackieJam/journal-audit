"""收入成本 inner sub-tab（可疑样本库筛选 / 收入成本）。"""

from __future__ import annotations

import hashlib

import streamlit as st

from components.charts import (
    audit_income_cost_abnormal_chart,
    audit_monthly_revenue_cost_chart,
    customer_revenue_top_chart,
    supplier_payables_top_chart,
)
from modules import column_check
from modules.visual_analysis import (
    build_customer_revenue_entry_top10_from_work,
    build_customer_top10_from_work,
    build_income_cost_abnormal_entry_top10_from_work,
    build_monthly_revenue_cost_entry_top10_from_work,
    build_supplier_payable_entry_top10_from_work,
    build_supplier_top10_from_work,
)

from ._context import AnalysisContext


def render_income_cost(ctx: AnalysisContext) -> None:
    audit_year_sel = ctx.audit_year_sel
    df_audit = ctx.df_audit
    audit_work = ctx.audit_work
    income_cost_category = ctx.income_cost_category
    monthly_view = ctx.monthly_view
    helpers = ctx.helpers
    _income_page_candidate_counts = helpers["_income_page_candidate_counts"]
    _render_candidate_recommendations_for_module = helpers["_render_candidate_recommendations_for_module"]
    _render_chart_title_with_download = helpers["_render_chart_title_with_download"]
    _selected_monthly_metric_point = helpers["_selected_monthly_metric_point"]
    _render_detail_with_actions = helpers["_render_detail_with_actions"]
    _selected_income_cost_abnormal_point = helpers["_selected_income_cost_abnormal_point"]
    _selected_bar_label = helpers["_selected_bar_label"]

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
            width="stretch",
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
            width="stretch",
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
                    width="stretch",
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
                    width="stretch",
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
