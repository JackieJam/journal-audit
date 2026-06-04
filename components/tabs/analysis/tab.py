"""序时账分析页签入口：守卫 + 画像/财务生成 + 顶层分发。"""

from __future__ import annotations

import streamlit as st

from config.constants import FINANCIALS_VERSION, PROFILES_VERSION
from modules.cross_year import run_cross_year_analysis
from modules.profiler import build_financial_summary, build_profile

from .overview import render_overview
from .pool import render_pool_management
from .suspect_filter import render_suspect_filter


def render_analysis_tab(main_tab=None, **helpers):
    """Render the 序时账分析 (Analysis) tab.

    从 app.py 内联抽离。依赖的 app.py 私有 helper 通过 **helpers 注入，
    与 upload/rules/sampling 页签保持一致的调用约定。顶层只做守卫、画像/财务
    数据生成与三个顶层子页签（财务概况/可疑样本库筛选/疑点库管理）的分发，
    每个子页签的渲染逻辑下沉到同包的独立模块。
    """
    _has_project_payload = helpers["_has_project_payload"]
    _has_loaded_years = helpers["_has_loaded_years"]
    _render_missing_columns_banner = helpers["_render_missing_columns_banner"]
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
        render_suspect_filter(financials=financials, profiles=profiles, findings=findings, helpers=helpers)
    if st.session_state._sub_tab_top == 0:  # 财务概况
        render_overview(financials=financials, helpers=helpers)
    if st.session_state._sub_tab_top == 2:  # 疑点库管理
        render_pool_management(helpers=helpers)
