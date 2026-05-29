"""
列字段守卫：分析模块入口检查必要字段是否存在，缺失则降级跳过并给出可审计提示。

使用：
    from modules.column_check import guard
    if not guard(["供应商编号"], "供应商集中度分析"):
        return  # 自动渲染跳过提示
    # 否则继续执行分析

session_state.missing_columns 由 ingestion.load_files() 返回时写入，
表示用户在上传阶段确认"无此列"的标准字段。
"""

from __future__ import annotations

import streamlit as st


def get_missing_columns() -> set[str]:
    """读取 session_state 中的缺失列集合。"""
    return set(st.session_state.get("missing_columns", []) or [])


def check_required(required: list[str]) -> list[str]:
    """返回 required 中实际缺失的列名（与 session_state 求交）。"""
    missing_now = get_missing_columns()
    return [c for c in required if c in missing_now]


def render_skip_notice(missing: list[str], analysis_name: str) -> None:
    """缺字段时渲染审计可读的降级提示。"""
    if not missing:
        return
    cols = "、".join(f"`{c}`" for c in missing)
    st.info(
        f"**{analysis_name}** 已跳过：源文件未包含 {cols}。"
        f"如需此分析，请在「上传数据」页签重新映射列后再次运行。",
        icon="ℹ️",
    )


def guard(required: list[str], analysis_name: str) -> bool:
    """缺字段则渲染提示并返回 False；齐全则返回 True。"""
    missing = check_required(required)
    if missing:
        render_skip_notice(missing, analysis_name)
        return False
    return True
