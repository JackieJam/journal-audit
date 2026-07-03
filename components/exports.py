"""图表 / 表格的 Excel 导出层。

从 app.py 抽离的通用导出工具：把 DataFrame 转成 Excel 字节流，
并渲染「标题 + 下载按钮」的图表头部。无 session 依赖。
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    export_df = df.copy()
    for col in export_df.columns:
        if pd.api.types.is_datetime64_any_dtype(export_df[col]):
            export_df[col] = export_df[col].dt.strftime("%Y-%m-%d")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "Sheet1")
    return output.getvalue()


def render_chart_title_with_download(
    title: str,
    *,
    df: pd.DataFrame,
    file_name: str,
    key: str,
    sheet_name: str,
) -> None:
    title_col, action_col = st.columns([0.92, 0.08])
    with title_col:
        st.markdown(f"#### {title}")
    with action_col:
        if df.empty:
            st.button("下载", key=f"{key}_disabled", disabled=True, help="当前图表暂无可导出数据")
        else:
            st.download_button(
                "下载",
                data=dataframe_to_excel_bytes(df, sheet_name=sheet_name),
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=key,
                help="下载当前图表对应的 Excel",
                width="stretch",
            )
