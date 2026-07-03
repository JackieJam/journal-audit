"""资产负债 inner sub-tab（可疑样本库筛选 / 资产负债）。

口径：序时账是流量数据，本页只做资产/负债类科目的**发生额与净变动**分析，
非期末余额表（无期初余额做不出真实余额）。通用引擎按类别参数化复用，
点选月度柱/净变动线或科目集中度条形，均可下钻全量分录并加入疑点库。
"""

from __future__ import annotations

import hashlib

import streamlit as st

from components.charts import (
    category_account_breakdown_chart,
    category_movement_monthly_chart,
)
from modules import column_check
from modules.account_classifier import BALANCE_SHEET_CATEGORIES, BALANCE_SHEET_SIDE
from modules.visual_analysis import (
    build_category_account_breakdown_from_work,
    build_category_account_entry_top10_from_work,
    build_category_entry_top10_from_work,
    build_category_monthly_movement_from_work,
)

from ._context import AnalysisContext

_DIRECTION_LABEL = {"debit": "借方发生额", "credit": "贷方发生额", "net": "净变动"}


def render_balance_sheet(ctx: AnalysisContext) -> None:
    audit_work = ctx.audit_work
    df_audit = ctx.df_audit
    year = ctx.audit_year_sel
    helpers = ctx.helpers
    _render_detail_with_actions = helpers["_render_detail_with_actions"]
    _render_chart_title_with_download = helpers["_render_chart_title_with_download"]
    _selected_monthly_metric_point = helpers["_selected_monthly_metric_point"]
    _selected_bar_label = helpers["_selected_bar_label"]

    if not column_check.guard(["总账科目"], "资产负债分析"):
        return

    present = set(audit_work["_acct_category"].dropna().astype(str).unique())
    options = [c for c in BALANCE_SHEET_CATEGORIES if c in present]
    if not options:
        st.info(
            "当前年度未识别到资产/负债类科目。"
            "如有，可在「上传数据 → 科目分类调整」中把相关科目手工归类后重新生成画像。"
        )
        return

    st.caption(
        "⚠️ 本页基于序时账**发生额**：展示资产/负债类科目的月度借贷发生额与净变动，"
        "**非期末余额表**（序时账无期初余额，做不出真实余额）。"
        "净变动按「资产借增、负债/权益贷增」取符号，正值=该类科目净增加。"
    )

    cat = st.selectbox(
        "科目类别",
        options,
        key=f"bs_category_{year}",
        format_func=lambda c: f"{c}（{BALANCE_SHEET_SIDE.get(c, '')}）",
    )
    side = BALANCE_SHEET_SIDE.get(cat, "")
    cat_key = hashlib.sha1(f"{cat}".encode()).hexdigest()[:8]

    _render_monthly_movement(
        audit_work, df_audit, year, cat, side, cat_key,
        _render_chart_title_with_download, _selected_monthly_metric_point, _render_detail_with_actions,
    )

    st.divider()
    _render_account_concentration(
        audit_work, df_audit, year, cat, cat_key,
        _render_chart_title_with_download, _selected_bar_label, _render_detail_with_actions,
    )


def _render_monthly_movement(
    audit_work, df_audit, year, cat, side, cat_key,
    _render_chart_title_with_download, _selected_monthly_metric_point, _render_detail_with_actions,
) -> None:
    monthly = build_category_monthly_movement_from_work(audit_work, cat)
    _render_chart_title_with_download(
        f"{cat} 月度借贷发生额与净变动",
        df=monthly,
        file_name=f"{year}_{cat}_monthly_movement.xlsx",
        key=f"download_bs_monthly_{year}_{cat_key}",
        sheet_name="月度变动",
    )
    st.caption("点击柱状图或净变动折线点后，下面会按所选月份/方向回查全量分录，并可加入疑点库。")
    event = st.plotly_chart(
        category_movement_monthly_chart(monthly, year, cat, side),
        width="stretch",
        key=f"bs_monthly_chart_{year}_{cat_key}",
        on_select="rerun",
        selection_mode="points",
    )
    point = _selected_monthly_metric_point(event, {0: "debit", 1: "credit", 2: "net"})
    sticky_key = f"chart_sel_bs_monthly_{cat_key}"
    if point is None:
        point = st.session_state.get(sticky_key)
    else:
        st.session_state[sticky_key] = point

    if point:
        month, direction = point
        label = _DIRECTION_LABEL.get(direction, "净变动")
        entries = build_category_entry_top10_from_work(
            audit_work, cat, month=month, direction=direction,
        )
        _render_detail_with_actions(
            f"{year}年{month}月 {cat} {label}全量分录",
            entries,
            df_source=df_audit,
            key=f"chart_panel_bs_monthly_{year}_{month}_{direction}_{cat_key}",
            source_module="资产负债",
            source_view=f"{cat}月度",
            selector={
                "kind": "bs_category_month",
                "year": year,
                "category": cat,
                "month": month,
                "direction": direction,
            },
            default_tags=["资产负债", "月度"],
            default_reason=f"{cat} {month}月 {label} 被选中，纳入疑点库复核。",
        )


def _render_account_concentration(
    audit_work, df_audit, year, cat, cat_key,
    _render_chart_title_with_download, _selected_bar_label, _render_detail_with_actions,
) -> None:
    breakdown = build_category_account_breakdown_from_work(audit_work, cat, top_n=15)
    _render_chart_title_with_download(
        f"{cat} 科目集中度",
        df=breakdown,
        file_name=f"{year}_{cat}_account_breakdown.xlsx",
        key=f"download_bs_breakdown_{year}_{cat_key}",
        sheet_name="科目集中度",
    )
    if breakdown.empty:
        st.info(f"当前年度 {cat} 暂无可按科目归集的发生额。")
        return

    st.caption("各科目净变动排名（Top15）。点击条形后展示该科目全部分录，可加入疑点库。")
    # 标签 -> 科目编号映射，供点选回查
    label_to_code = {
        f"{code} {name}".strip(): str(code)
        for code, name in zip(breakdown["科目编号"], breakdown["科目名称"], strict=True)
    }
    event = st.plotly_chart(
        category_account_breakdown_chart(breakdown, f"{year}年 {cat} 科目净变动 Top15"),
        width="stretch",
        key=f"bs_breakdown_chart_{year}_{cat_key}",
        on_select="rerun",
        selection_mode="points",
    )
    sel_label = _selected_bar_label(event)
    sticky_key = f"chart_sel_bs_account_{cat_key}"
    if sel_label is None:
        sel_label = st.session_state.get(sticky_key)
    else:
        st.session_state[sticky_key] = sel_label

    if sel_label:
        code = label_to_code.get(sel_label)
        if not code:
            # 兜底：标签首段即科目编号
            code = str(sel_label).split(" ", 1)[0]
        entries = build_category_account_entry_top10_from_work(audit_work, cat, code)
        _render_detail_with_actions(
            f"{year}年 {cat} 科目 {sel_label} 全量分录",
            entries,
            df_source=df_audit,
            key=f"chart_panel_bs_account_{year}_{code}_{cat_key}",
            source_module="资产负债",
            source_view=f"{cat}科目",
            selector={
                "kind": "bs_category_account",
                "year": year,
                "category": cat,
                "account": code,
            },
            default_tags=["资产负债", "科目"],
            default_reason=f"{cat} 科目 {sel_label} 被选中，纳入疑点库复核。",
        )
