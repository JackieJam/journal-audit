"""
Tab 1 – 上传数据

Renders the file upload / year-recognition UI.
"""

from __future__ import annotations

import os

import streamlit as st
import pandas as pd

from modules.ingestion import load_files, summarize_years


def render_upload_tab(main_tab, **helpers) -> None:
    """Render the Tab-1 '上传数据' content."""
    _require_loaded_data = helpers["_require_loaded_data"]
    _has_project_payload = helpers["_has_project_payload"]
    _has_loaded_years = helpers["_has_loaded_years"]
    _clear_analysis_results = helpers["_clear_analysis_results"]
    _clear_loaded_data = helpers["_clear_loaded_data"]
    _uploaded_files_signature = helpers["_uploaded_files_signature"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]

    st.title("📂 文件上传")

    with st.expander("📁 文件上传", expanded=True):
        st.caption(
            '支持单/多个 Excel 文件，自动识别年份。'
            '系统将根据\u201c过账日期\u201d字段自动聚合数据。'
        )
        with st.container(border=True):
            uploaded = st.file_uploader(
                "选择序时账文件（.xlsx / .xls）",
                type=["xlsx", "xls", "XLSX", "XLS"],
                accept_multiple_files=True,
                key=f"journal_upload_{st.session_state.get('upload_widget_nonce', 0)}",
                label_visibility="collapsed",
            )

        if uploaded:
            _process_files(uploaded, _uploaded_files_signature,
                           _clear_loaded_data, _clear_analysis_results,
                           _autosave_current_project_state)

    if _has_loaded_years() and not uploaded:
        st.info("当前会话里已经有已解析数据。你可以直接继续数据画像，或重新选择文件覆盖当前数据。")


def _process_files(uploaded, _uploaded_files_signature,
                   _clear_loaded_data, _clear_analysis_results,
                   _autosave_current_project_state):
    """处理上传的文件。"""
    file_signature = _uploaded_files_signature(uploaded)
    loaded_signature = st.session_state.get("loaded_file_signature")

    if loaded_signature and loaded_signature != file_signature:
        _clear_loaded_data()
        loaded_signature = None

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("待读取文件清单")
        file_rows = [
            {"文件名": file.name, "大小": f"{round((getattr(file, 'size', 0) or 0) / 1024 / 1024, 2)} MB"}
            for file in uploaded
        ]
        st.dataframe(pd.DataFrame(file_rows), use_container_width=True, hide_index=True)

    with col2:
        if loaded_signature != file_signature:
            st.subheader("操作")
            st.info("已选择文件。确认文件齐全后开始读取。")
            if st.button("开始解析数据", type="primary", use_container_width=True):
                progress = st.progress(0, text="正在识别数据…")
                try:
                    df_unified, year_map = load_files(uploaded)
                    progress.progress(60, text=f"数据识别完成（{len(df_unified):,} 行），正在汇总年度…")
                    summary = summarize_years(df_unified)
                    st.session_state.df_unified = df_unified
                    st.session_state.year_map = year_map
                    st.session_state.year_summary = summary
                    st.session_state.loaded_file_signature = file_signature
                    _clear_analysis_results()
                    _autosave_current_project_state()
                    progress.progress(100, text="汇总完成，即将跳转分析页…")
                    st.session_state.active_tab = 1
                except Exception as e:
                    st.error(f"文件读取失败：{e}")
                    st.stop()
                st.rerun()

        if st.session_state.get("loaded_file_signature") == file_signature:
            st.subheader("数据识别概览")
            year_map = st.session_state.year_map
            summary = st.session_state.year_summary
            st.success(f"成功识别到 **{len(year_map)}** 个年度的数据")
            df_summary = pd.DataFrame(summary)
            st.dataframe(df_summary, use_container_width=True, hide_index=True)

            if st.button("确认识别结果", type="primary", use_container_width=True):
                st.rerun()
