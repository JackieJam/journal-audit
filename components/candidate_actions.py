"""疑点库候选动作与明细表格交互组件。

把"明细清单渲染 + 选中流转 + 加入疑点库 / 直入最终样本"这一簇 UI 逻辑从 app.py 抽离。
统计辅助（detail_metrics / detail_amount_series）为纯函数；其余依赖 st.session_state
与候选池数据层（modules.candidate_pool）。写入候选池后需要触发项目自动保存——该逻辑
深度绑定 app.py 的项目状态机制，因此通过 ``autosave`` 回调注入，模块本身不直接持久化。

app.py 通过 alias 保留原调用名（_detail_metrics 等）；其中需要 autosave 的三个入口
（save_candidate_group / render_candidate_add_popover / render_detail_with_actions）
在 app.py 用 functools.partial 预绑定 _autosave_current_project_state，调用签名与
注入给各子页签的 helper key 均不变，行为零变化。
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from modules import candidate_pool as cp
from modules.formatting import format_money
from components.chart_selection import (
    selected_dataframe_focus_row_index,
    selected_dataframe_row_indices,
)

CANDIDATE_TAG_OPTIONS = [
    "收入波动", "客户", "供应商", "物料组", "成本波动", "费用波动", "成本科目", "大额", "月度", "月末", "年末",
    "P13", "异常方向", "冲销调账", "暂估异常", "往来异常", "跨年异常", "模型建议",
    "月度异常", "客户集中", "供应商集中", "收入S异常", "成本H异常", "应付异常",
]


def detail_metrics(detail: pd.DataFrame) -> dict[str, float | int]:
    if detail.empty:
        return {"rows": 0, "vouchers": 0, "amount": 0.0}
    amount_cols = [
        "收入影响", "成本发生额", "费用发生额", "收入S影响", "成本H影响",
        "暂估贷方增加", "暂估借方减少", "暂估净额影响",
        "其他应收S发生额", "其他应收H发生额", "其他应收净额影响",
        "其他应付预提H", "其他应付核销S", "其他应付净值影响",
        "公司代码货币价值", "凭证货币价值",
    ]
    amount = 0.0
    for col in amount_cols:
        if col in detail.columns:
            amount = float(pd.to_numeric(detail[col], errors="coerce").fillna(0).abs().sum())
            break
    vouchers = int(detail["凭证编号"].astype(str).nunique()) if "凭证编号" in detail.columns else 0
    return {"rows": int(len(detail)), "vouchers": vouchers, "amount": amount}


def detail_amount_series(detail: pd.DataFrame) -> pd.Series:
    amount_cols = [
        "收入影响", "成本发生额", "毛利影响", "费用发生额", "应付发生额",
        "收入S影响", "成本H影响",
        "暂估贷方增加", "暂估借方减少", "暂估净额影响",
        "其他应收S发生额", "其他应收H发生额", "其他应收净额影响",
        "其他应付预提H", "其他应付核销S", "其他应付净值影响",
        "公司代码货币价值", "凭证货币价值",
    ]
    for col in amount_cols:
        if col in detail.columns:
            return pd.to_numeric(detail[col], errors="coerce").fillna(0).abs()
    return pd.Series([0.0] * len(detail), index=detail.index, dtype="float64")


def amount_column_config(amount_cols: list[str] | None = None) -> dict:
    config = {
        "过账日期": st.column_config.DateColumn("过账日期", format="YYYY-MM-DD"),
        "公司代码货币价值": st.column_config.NumberColumn("公司代码货币价值", format="¥ %,.2f"),
        "凭证货币价值": st.column_config.NumberColumn("凭证货币价值", format="¥ %,.2f"),
    }
    for col in amount_cols or []:
        config[col] = st.column_config.NumberColumn(col, format="¥ %,.2f")
    return config


def reset_editor_state(key: str) -> None:
    """清空明细选择控件状态，强制下次渲染时重新初始化。"""
    for widget_key in (f"{key}_hidden_sel", f"{key}_detail_editor", f"{key}_detail_table"):
        if widget_key in st.session_state:
            del st.session_state[widget_key]


def style_selected_detail_rows(selected_vids: set[str]):
    def _style_row(row: pd.Series) -> list[str]:
        if str(row.get("__voucher_id_raw", "")) not in selected_vids:
            return [""] * len(row)
        return [
            "background-color: rgba(74, 222, 128, 0.18); color: #e2e8f0;"
            for _ in row
        ]

    return _style_row


def resolve_focused_voucher(key: str, detail: pd.DataFrame) -> tuple[str | None, str]:
    focus_state_key = f"{key}_focused_voucher"
    focus_state = st.session_state.get(focus_state_key) or {}
    voucher_id = str(focus_state.get("voucher_id") or "").strip()
    voucher_date = str(focus_state.get("voucher_date") or "").strip()
    if not voucher_id:
        return None, ""

    valid_mask = detail["凭证编号"].astype(str) == voucher_id
    if voucher_date and "过账日期" in detail.columns:
        valid_mask &= (
            pd.to_datetime(detail["过账日期"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .fillna("")
            == voucher_date
        )
    if not valid_mask.any():
        return None, ""
    return voucher_id, voucher_date


def render_focused_voucher_detail(
    *,
    key: str,
    df_source: pd.DataFrame,
    amount_cols: list[str] | None = None,
) -> None:
    focused_vid, focused_date = resolve_focused_voucher(key, df_source)
    if not focused_vid:
        st.caption("点击上方明细清单中的任意一行，即可查看当前凭证的完整分录。")
        return

    voucher_mask = df_source["凭证编号"].astype(str) == focused_vid
    if focused_date and "过账日期" in df_source.columns:
        voucher_mask &= (
            pd.to_datetime(df_source["过账日期"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .fillna("")
            == focused_date
        )
    voucher_detail = df_source.loc[voucher_mask].copy()
    if voucher_detail.empty:
        st.caption("当前凭证未回查到完整分录。")
        return

    st.markdown(f"**当前凭证完整分录：{focused_vid}**")
    extra_note = f" | 过账日期 {focused_date}" if focused_date else ""
    st.caption(f"已定位到 {len(voucher_detail)} 行完整分录{extra_note}。")
    st.dataframe(
        voucher_detail,
        width="stretch",
        hide_index=True,
        column_config=amount_column_config(amount_cols),
    )


def save_candidate_group(
    *,
    title: str,
    source_module: str,
    source_view: str,
    detail: pd.DataFrame,
    tags: list[str],
    reason: str,
    selector: dict[str, Any],
    autosave: Callable[[], None],
    manual_final: bool = False,
    created_by: str = "manual",
    recommendation: dict[str, Any] | None = None,
) -> None:
    status = cp.MANUAL_FINAL_STATUS if manual_final else cp.DEFAULT_STATUS
    group = cp.build_candidate_group(
        title=title,
        source_module=source_module,
        source_view=source_view,
        detail=detail,
        tags=tags,
        reason=reason,
        selector=selector,
        status=status,
        created_by=created_by,
        recommendation=recommendation,
    )
    st.session_state.candidate_pool = cp.add_candidate_group(st.session_state.candidate_pool, group)
    st.session_state.rule_results = []
    st.session_state.llm_judgments = {}
    st.session_state.report_stats = {}
    st.session_state.report_path = None
    autosave()


def render_candidate_add_popover(
    *,
    key: str,
    title: str,
    source_module: str,
    source_view: str,
    detail: pd.DataFrame,
    selector: dict[str, Any],
    default_tags: list[str],
    default_reason: str,
    autosave: Callable[[], None],
    created_by: str = "manual",
    recommendation: dict[str, Any] | None = None,
) -> None:
    if detail.empty:
        return
    stats = detail_metrics(detail)
    with st.popover("加入疑点库", width="stretch"):
        st.caption(
            f"将按当前条件加入全量匹配分录：{stats['rows']:,} 行，"
            f"{stats['vouchers']:,} 个凭证，金额绝对值合计 {format_money(stats['amount'])}。"
        )
        all_tags = sorted(set(CANDIDATE_TAG_OPTIONS + default_tags))
        tags = st.multiselect(
            "风险标签（仅用于疑点库归类，不参与文本搜索）",
            options=all_tags,
            default=[tag for tag in default_tags if tag in all_tags],
            key=f"{key}_tags",
        )
        reason = st.text_area("入库理由", value=default_reason, key=f"{key}_reason", height=90)
        manual_final = st.checkbox("同时标记为人工直入最终样本", key=f"{key}_manual_final")
        if st.button("确认加入", type="primary", width="stretch", key=f"{key}_add"):
            save_candidate_group(
                title=title,
                source_module=source_module,
                source_view=source_view,
                detail=detail,
                tags=tags,
                reason=reason,
                selector=selector,
                manual_final=manual_final,
                created_by=created_by,
                recommendation=recommendation,
                autosave=autosave,
            )
            st.success("已加入疑点库。")
            # 写入全局候选池后跳出 fragment 触发整页刷新，保证侧边栏/疑点库页签同步（风险可见）。
            st.rerun(scope="app")


def render_detail_with_actions(
    title: str,
    detail: pd.DataFrame,
    *,
    df_source: pd.DataFrame,
    key: str,
    source_module: str,
    source_view: str,
    selector: dict[str, Any],
    autosave: Callable[[], None],
    amount_cols: list[str] | None = None,
    default_tags: list[str] | None = None,
    default_reason: str = "",
) -> None:
    """明细表格：左侧选择框批量流转，点击任意行查看当前凭证完整分录。"""
    if detail.empty:
        st.info("暂无匹配分录。")
        return

    stats = detail_metrics(detail)
    st.markdown(f"**{title}**")
    sel_state_key = f"{key}_selected_vids"

    # ── 金额筛选 ──
    amount_options = ["全部金额", "≥10万", "≥50万", "≥100万", "≥500万"]
    threshold_map = {"全部金额": 0, "≥10万": 1e5, "≥50万": 5e5, "≥100万": 1e6, "≥500万": 5e6}
    filter_col1, filter_col2, filter_col3 = st.columns([2.5, 1, 1])
    with filter_col1:
        amount_sel = st.radio(
            "金额筛选", amount_options, index=0, horizontal=True,
            key=f"{key}_amt_filter", label_visibility="collapsed"
        )
    threshold = threshold_map.get(amount_sel, 0)
    amount_series = detail_amount_series(detail)
    eligible_vids = set(detail["凭证编号"].astype(str).tolist()) if threshold == 0 else \
        set(detail.loc[amount_series >= threshold, "凭证编号"].astype(str).tolist())

    with filter_col2:
        if threshold > 0:
            if st.button(f"✓ 选择 {amount_sel}", type="primary", width="stretch", key=f"{key}_apply_filter"):
                st.session_state[sel_state_key] = list(eligible_vids)
                reset_editor_state(key)
                st.rerun()
        else:
            if st.button("✓ 全选", width="stretch", key=f"{key}_select_all"):
                st.session_state[sel_state_key] = detail["凭证编号"].astype(str).unique().tolist()
                reset_editor_state(key)
                st.rerun()
    with filter_col3:
        if st.button("✗ 清空", width="stretch", key=f"{key}_clear_sel"):
            st.session_state[sel_state_key] = []
            reset_editor_state(key)
            st.rerun()

    # ── 当前选中集合（基础值，来自上次持久化）──
    prev_selected = set(st.session_state.get(sel_state_key) or [])
    base_selected = prev_selected & set(detail["凭证编号"].astype(str).tolist())

    # ── 原生明细表：左侧选择框用于批量动作，点击行回看完整分录 ──
    display_detail = detail.copy()
    display_detail["__voucher_id_raw"] = detail["凭证编号"].astype(str)
    if "过账日期" in detail.columns:
        display_detail["__voucher_date"] = (
            pd.to_datetime(detail["过账日期"], errors="coerce")
            .dt.strftime("%Y-%m-%d")
            .fillna("")
        )
    else:
        display_detail["__voucher_date"] = ""
    if "过账日期" in display_detail.columns:
        display_detail["过账日期"] = display_detail["过账日期"].astype(str).str[:10]
    if "借/贷标识" in display_detail.columns:
        display_detail["借/贷标识"] = display_detail["借/贷标识"].replace({"S": "借", "H": "贷"}).fillna("")
    visible_columns = [
        col for col in display_detail.columns if col not in {"__voucher_id_raw", "__voucher_date"}
    ]

    table_config: dict[str, Any] = amount_column_config(amount_cols)
    for amount_col in ("凭证货币价值", "公司代码货币价值"):
        if amount_col in display_detail.columns:
            table_config[amount_col] = st.column_config.NumberColumn(amount_col, format="%,.0f")

    styled_detail = display_detail.style.apply(
        style_selected_detail_rows(base_selected),
        axis=1,
    )
    default_focus_vid, default_focus_date = resolve_focused_voucher(key, detail)
    default_selected_rows = [
        idx for idx, voucher_id in enumerate(display_detail["__voucher_id_raw"].astype(str).tolist())
        if voucher_id in base_selected
    ]
    default_focus_row = None
    if default_focus_vid:
        focus_mask = display_detail["__voucher_id_raw"].astype(str) == default_focus_vid
        if default_focus_date:
            focus_mask &= display_detail["__voucher_date"].astype(str) == default_focus_date
        focus_matches = display_detail.index[focus_mask].tolist()
        if focus_matches:
            default_focus_row = int(focus_matches[0])
    default_selection: dict[str, Any] = {
        "selection": {
            "rows": default_selected_rows,
            "columns": [],
            "cells": [f"{default_focus_row}:0"] if default_focus_row is not None else [],
        }
    }

    detail_event = st.dataframe(
        styled_detail,
        key=f"{key}_detail_table",
        width="stretch",
        hide_index=True,
        height=min(520, 90 + max(len(display_detail), 1) * 35),
        column_order=visible_columns,
        column_config=table_config,
        on_select="rerun",
        selection_mode=["multi-row", "single-cell"],
        selection_default=default_selection,
    )
    selected_rows = selected_dataframe_row_indices(detail_event)
    current_selected = set(
        display_detail.iloc[selected_rows]["__voucher_id_raw"].astype(str).tolist()
    ) & set(detail["凭证编号"].astype(str).tolist())

    focus_row_index = selected_dataframe_focus_row_index(detail_event)
    if focus_row_index is not None and 0 <= focus_row_index < len(display_detail):
        st.session_state[f"{key}_focused_voucher"] = {
            "voucher_id": str(display_detail.iloc[focus_row_index]["__voucher_id_raw"]),
            "voucher_date": str(display_detail.iloc[focus_row_index]["__voucher_date"]),
        }

    if current_selected != base_selected:
        st.session_state[sel_state_key] = sorted(current_selected)

    # ── 批量操作按钮（弹窗内含风险标签+理由）──
    st.caption(
        f"匹配 {stats['rows']:,} 行 / {stats['vouchers']:,} 个凭证 / "
        f"金额合计 {format_money(stats['amount'])}。"
        f"**已选 {len(current_selected)} 个** | 使用最左侧选择框可批量选中；点击任意行可查看当前凭证完整分录。"
    )
    col_add, col_final = st.columns(2)
    with col_add:
        with st.popover("📥 批量加入疑点库", width="stretch", disabled=not current_selected):
            tags_add = st.multiselect("风险标签", key=f"{key}_pop_add_tags",
                options=sorted(set(CANDIDATE_TAG_OPTIONS + (default_tags or []))),
                default=default_tags or [])
            reason_add = st.text_area("入库理由", key=f"{key}_pop_add_reason",
                value=default_reason, height=60)
            if st.button("确认加入", type="primary", width="stretch", key=f"{key}_pop_add_btn",
                          disabled=not current_selected):
                batch_detail = df_source[df_source["凭证编号"].astype(str).isin(current_selected)]
                save_candidate_group(
                    title=f"{source_module}/{source_view}/批量{len(current_selected)}个",
                    source_module=source_module, source_view=source_view,
                    detail=batch_detail, tags=tags_add, reason=reason_add,
                    selector=selector, manual_final=False, autosave=autosave)
                st.session_state[sel_state_key] = []
                st.success(f"已批量加入 {len(current_selected)} 个凭证到疑点库。")
                st.rerun(scope="app")
    with col_final:
        with st.popover("🚀 批量直入最终样本", width="stretch", disabled=not current_selected):
            tags_final = st.multiselect("风险标签", key=f"{key}_pop_final_tags",
                options=sorted(set(CANDIDATE_TAG_OPTIONS + (default_tags or []))),
                default=default_tags or [])
            reason_final = st.text_area("入库理由", key=f"{key}_pop_final_reason",
                value=default_reason, height=60)
            if st.button("确认直入", width="stretch", key=f"{key}_pop_final_btn",
                          disabled=not current_selected):
                batch_detail = df_source[df_source["凭证编号"].astype(str).isin(current_selected)]
                save_candidate_group(
                    title=f"{source_module}/{source_view}/批量{len(current_selected)}个",
                    source_module=source_module, source_view=source_view,
                    detail=batch_detail, tags=tags_final, reason=reason_final,
                    selector=selector, manual_final=True, autosave=autosave)
                st.session_state[sel_state_key] = []
                st.success(f"已批量直入 {len(current_selected)} 个凭证到最终样本。")
                st.rerun(scope="app")

    # ── 已选凭证清单 ──
    if current_selected:
        selected_list = sorted(current_selected)
        display_ids = selected_list[:20]
        more = f" …等共 {len(selected_list)} 个" if len(selected_list) > 20 else ""
        st.caption(f"✅ 已选凭证号：{', '.join(display_ids)}{more}")

    render_focused_voucher_detail(
        key=key,
        df_source=df_source,
        amount_cols=amount_cols,
    )
