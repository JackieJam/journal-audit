"""
Tab 1 – 上传数据

文件上传 → 列名映射确认 → 数据解析 → 年度识别。

新版增加列名映射阶段：
1. 用户选好文件后，先调用 detect_columns() 探测源文件列名并给出建议映射；
2. UI 按"核心/重要/辅助"三档展示标准列，每个标准列对应一个下拉框；
3. 用户确认映射后，再调用 load_files(uploaded, mapping) 完成解析；
4. 缺失字段以空占位放行，并写入 session_state.missing_columns 供下游分析降级。
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from modules import account_classifier, knowledge_base
from modules.account_classifier import ALL_CATEGORIES, CAT_UNCATEGORIZED
from modules.ingestion import (
    NO_COLUMN_SENTINEL,
    STANDARD_COLUMNS,
    detect_columns,
    load_files,
    summarize_years,
)

logger = logging.getLogger(__name__)


_TIER_LABELS = {
    "core": ("核心字段", "缺失会直接影响基础校验，必须确认"),
    "important": ("重要字段", "缺失会让相关分析模块自动跳过"),
    "auxiliary": ("辅助字段", "仅影响展示丰富度，可全部留空"),
}


def render_upload_tab(main_tab, **helpers) -> None:
    """Render the Tab-1 '上传数据' content."""
    _has_loaded_years = helpers["_has_loaded_years"]
    _clear_analysis_results = helpers["_clear_analysis_results"]
    _clear_loaded_data = helpers["_clear_loaded_data"]
    _uploaded_files_signature = helpers["_uploaded_files_signature"]
    _autosave_current_project_state = helpers["_autosave_current_project_state"]

    st.title("📂 文件上传")

    with st.expander("📁 文件上传", expanded=True):
        st.caption(
            '支持单/多个 .xlsx 文件。上传后会先确认列名映射，再自动按"过账日期"识别年份。'
        )
        with st.container(border=True):
            uploaded = st.file_uploader(
                "选择序时账文件（.xlsx）",
                type=["xlsx", "XLSX"],
                accept_multiple_files=True,
                key=f"journal_upload_{st.session_state.get('upload_widget_nonce', 0)}",
                label_visibility="collapsed",
            )
            st.caption("旧版 .xls 请先另存为 .xlsx 后上传。")

        if uploaded:
            _process_files(
                uploaded,
                _uploaded_files_signature,
                _clear_loaded_data,
                _clear_analysis_results,
                _autosave_current_project_state,
            )

    if _has_loaded_years() and not uploaded:
        st.info("当前会话里已经有已解析数据。可在下方查看识别概览、调整科目体系配置，或重新选择文件覆盖当前数据。")
        _render_loaded_summary()


def _process_files(
    uploaded,
    _uploaded_files_signature,
    _clear_loaded_data,
    _clear_analysis_results,
    _autosave_current_project_state,
):
    """处理上传的文件：先探测列名 → UI 映射 → 解析。"""
    file_signature = _uploaded_files_signature(uploaded)
    loaded_signature = st.session_state.get("loaded_file_signature")

    # ── 切换文件 → 清空旧数据 + 重新探测 ──
    if loaded_signature and loaded_signature != file_signature:
        _clear_loaded_data()
        loaded_signature = None

    # ── 探测列名（结果缓存到 session）──
    detection_key = f"detection_{file_signature}"
    if detection_key not in st.session_state:
        with st.spinner("正在读取文件列名…"):
            try:
                st.session_state[detection_key] = detect_columns(
                    uploaded, learned_aliases=_safe_learned_aliases()
                )
            except Exception as exc:
                st.error(f"文件列名读取失败：{exc}")
                return

    detection = st.session_state[detection_key]

    # ── 映射阶段或解析阶段 ──
    if loaded_signature == file_signature:
        _render_loaded_summary()
    else:
        _render_mapping_stage(
            uploaded,
            detection,
            file_signature,
            _clear_analysis_results,
            _autosave_current_project_state,
        )


def _render_mapping_stage(
    uploaded,
    detection,
    file_signature,
    _clear_analysis_results,
    _autosave_current_project_state,
):
    """渲染列名映射 UI 并触发解析。"""
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.subheader("待读取文件清单")
        file_rows = [
            {
                "文件名": file.name,
                "大小": f"{round((getattr(file, 'size', 0) or 0) / 1024 / 1024, 2)} MB",
            }
            for file in uploaded
        ]
        st.dataframe(pd.DataFrame(file_rows), width="stretch", hide_index=True)

        st.caption(f"探测到源文件共 **{len(detection.source_columns)}** 列")
        with st.expander("查看源文件全部列名", expanded=False):
            st.write("、".join(detection.source_columns) or "（空）")
        if not detection.sample.empty:
            with st.expander("源文件前 5 行预览", expanded=False):
                st.dataframe(detection.sample.head(), width="stretch", hide_index=True)

    with col_right:
        st.subheader("列名映射确认")
        st.caption("系统已按列名相似度自动匹配，请确认或修改后开始解析。")

        # 当前 mapping 的可编辑副本
        mapping_state_key = f"mapping_{file_signature}"
        if mapping_state_key not in st.session_state:
            st.session_state[mapping_state_key] = dict(detection.suggested_mapping)
        mapping = st.session_state[mapping_state_key]

        action_col1, action_col2 = st.columns(2)
        with action_col1:
            if st.button("重置为自动建议", width="stretch", key=f"reset_map_{file_signature}"):
                st.session_state[mapping_state_key] = dict(detection.suggested_mapping)
                # 同步清空各 selectbox 的状态
                for std in STANDARD_COLUMNS:
                    st.session_state.pop(f"map_{file_signature}_{std.name}", None)
                st.rerun()
        with action_col2:
            if st.button("全部清空（除核心）", width="stretch", key=f"clear_map_{file_signature}"):
                for std in STANDARD_COLUMNS:
                    if std.tier != "core":
                        st.session_state[mapping_state_key].pop(std.name, None)
                        st.session_state.pop(f"map_{file_signature}_{std.name}", None)
                st.rerun()

        _render_mapping_form(detection, mapping, file_signature)
        _render_mapping_summary(mapping)

        if st.button(
            "开始解析数据",
            type="primary",
            width="stretch",
            key=f"parse_{file_signature}",
        ):
            _run_parse(
                uploaded,
                mapping,
                file_signature,
                _clear_analysis_results,
                _autosave_current_project_state,
            )


def _render_mapping_form(detection, mapping: dict[str, str], file_signature: str) -> None:
    """按 tier 分组展示 selectbox。"""
    by_tier: dict[str, list] = {"core": [], "important": [], "auxiliary": []}
    for std in STANDARD_COLUMNS:
        by_tier[std.tier].append(std)

    options = [NO_COLUMN_SENTINEL, *detection.source_columns]
    matches = getattr(detection, "mapping_matches", {}) or {}

    fuzzy_flagged = sum(
        1 for std in STANDARD_COLUMNS
        if _is_low_confidence(matches.get(std.name), mapping.get(std.name))
    )
    learned_count = sum(
        1 for std in STANDARD_COLUMNS
        if _is_learned(matches.get(std.name), mapping.get(std.name))
    )
    if learned_count:
        st.caption(
            f"📚 其中 **{learned_count}** 个字段命中**经验库**（你以往确认过的列名映射，已自动套用）。"
        )
    if fuzzy_flagged:
        st.caption(
            f"⚠️ 其中 **{fuzzy_flagged}** 个字段是按列名相似度**模糊匹配**的（非精确命中），"
            f"下方以 `≈ 模糊匹配` 标出，请重点核对后再解析。"
        )

    for tier in ("core", "important", "auxiliary"):
        title, hint = _TIER_LABELS[tier]
        cols_in_tier = by_tier[tier]
        # 计算未映射数量
        unmapped = sum(
            1 for std in cols_in_tier
            if not mapping.get(std.name) or mapping.get(std.name) == NO_COLUMN_SENTINEL
        )
        # 核心字段或有缺失的重要字段：默认展开
        expanded = tier == "core" or (tier == "important" and unmapped > 0)
        badge = f"（{len(cols_in_tier) - unmapped}/{len(cols_in_tier)} 已映射）"
        with st.expander(f"{title}　{badge}", expanded=expanded):
            st.caption(hint)
            for std in cols_in_tier:
                _render_single_mapping_row(std, options, mapping, file_signature, matches.get(std.name))


def _is_low_confidence(match, current: str | None) -> bool:
    """该字段是否为「低置信模糊匹配」：仍采用自动建议、且命中方式为子串/模糊。"""
    if match is None:
        return False
    if not current or current == NO_COLUMN_SENTINEL:
        return False
    # 用户已手动改成别的源列，则不再算"模糊建议"
    if current != match.source:
        return False
    return match.method in ("contains", "fuzzy")


def _is_learned(match, current: str | None) -> bool:
    """该字段是否命中经验库：仍采用自动建议、且命中方式为 learned。"""
    if match is None or not current or current == NO_COLUMN_SENTINEL:
        return False
    if current != match.source:
        return False
    return match.method == "learned"


def _render_single_mapping_row(std, options: list[str], mapping: dict[str, str], file_signature: str, match=None) -> None:
    """单个标准列的下拉行。"""
    current = mapping.get(std.name, NO_COLUMN_SENTINEL)
    if current not in options:
        current = NO_COLUMN_SENTINEL

    widget_key = f"map_{file_signature}_{std.name}"
    label = f"**{std.name}**"
    if std.tier == "core":
        label += "  :red[*核心*]"
    if _is_learned(match, current):
        label += "  :green[📚 经验库]"
    elif _is_low_confidence(match, current):
        label += f"  :orange[≈ 模糊匹配 {match.score:.0%}]"

    selected = st.selectbox(
        label,
        options=options,
        index=options.index(current),
        key=widget_key,
        help=std.description or None,
    )
    mapping[std.name] = selected if selected != NO_COLUMN_SENTINEL else NO_COLUMN_SENTINEL


def _render_mapping_summary(mapping: dict[str, str]) -> None:
    """汇总缺失字段，提示哪些分析将不可用。"""
    missing_core: list[str] = []
    missing_important: list[str] = []
    for std in STANDARD_COLUMNS:
        val = mapping.get(std.name)
        if val and val != NO_COLUMN_SENTINEL:
            continue
        if std.tier == "core":
            missing_core.append(std.name)
        elif std.tier == "important":
            missing_important.append(std.name)

    # 借/贷标识允许通过借方金额/贷方金额或正负号合成
    if "借/贷标识" in missing_core:
        has_dc_amount = (
            mapping.get("借方金额") and mapping.get("借方金额") != NO_COLUMN_SENTINEL
        ) or (
            mapping.get("贷方金额") and mapping.get("贷方金额") != NO_COLUMN_SENTINEL
        )
        has_amount = (
            mapping.get("凭证货币价值") and mapping.get("凭证货币价值") != NO_COLUMN_SENTINEL
        )
        if has_dc_amount:
            missing_core.remove("借/贷标识")
            st.caption("ℹ️ `借/贷标识` 缺失，将由 `借方金额` / `贷方金额` 自动推断。")
        elif has_amount:
            missing_core.remove("借/贷标识")
            st.caption("ℹ️ `借/贷标识` 缺失，将由 `凭证货币价值` 正负号自动推断。")

    if missing_core:
        cols = "、".join(f"`{c}`" for c in missing_core)
        st.error(f"核心字段缺失：{cols}。这些字段会阻断基础校验，强烈建议补齐。")

    if missing_important:
        cols = "、".join(f"`{c}`" for c in missing_important)
        st.warning(
            f"以下重要字段未映射：{cols}。"
            f"相关分析模块将在解析后自动跳过并给出说明。"
        )


def _run_parse(
    uploaded,
    mapping: dict[str, str],
    file_signature,
    _clear_analysis_results,
    _autosave_current_project_state,
) -> None:
    """执行数据解析并写入 session。"""
    progress = st.progress(0, text="正在按映射读取数据…")
    try:
        df_unified, year_map, missing = load_files(uploaded, column_mapping=mapping)
        progress.progress(60, text=f"数据识别完成（{len(df_unified):,} 行），正在汇总年度…")
        summary = summarize_years(df_unified)

        st.session_state.df_unified = df_unified
        st.session_state.year_map = year_map
        st.session_state.year_summary = summary
        st.session_state.missing_columns = missing
        st.session_state.column_mapping = {
            k: v for k, v in mapping.items() if v and v != NO_COLUMN_SENTINEL
        }
        st.session_state.loaded_file_signature = file_signature
        _clear_analysis_results()
        # 数据集被替换：强制重写重数据，避免「同结构不同内容」的重新上传被签名漏判。
        _autosave_current_project_state(data_changed=True)
        # 列名沉淀：把用户最终确认的映射写入经验库，让下次匹配越用越聪明。
        # 失败不可阻断解析（学习是增强项，非主流程）。
        _record_column_mappings_safe(mapping)
        progress.progress(100, text="解析完成，下方可查看识别概览和科目体系配置。")
    except Exception as e:
        st.error(f"文件读取失败：{e}")
        st.stop()
    st.rerun()


def _safe_learned_aliases() -> dict[str, str]:
    """从经验库取学习别名；任何异常都降级为空，不阻断上传。"""
    try:
        return knowledge_base.learned_column_aliases()
    except Exception:
        return {}


def _record_column_mappings_safe(mapping: dict[str, str]) -> None:
    """沉淀本次确认的列映射到经验库（忽略未映射项）。失败静默，不阻断主流程。"""
    confirmed = {
        std: src for std, src in mapping.items()
        if src and src != NO_COLUMN_SENTINEL
    }
    if not confirmed:
        return
    try:
        knowledge_base.record_column_mappings(confirmed)
    except Exception:
        logger.warning("record_column_mappings failed; 学习数据未沉淀", exc_info=True)


def _render_loaded_summary() -> None:
    """已解析后的概览展示。"""
    st.subheader("数据识别概览")
    year_map = st.session_state.year_map
    summary = st.session_state.year_summary
    st.success(f"成功识别到 **{len(year_map)}** 个年度的数据")

    df_summary = pd.DataFrame(summary)
    st.dataframe(df_summary, width="stretch", hide_index=True)

    missing = st.session_state.get("missing_columns", []) or []
    important_missing = [
        c for c in missing
        if c in {std.name for std in STANDARD_COLUMNS if std.tier == "important"}
    ]
    if important_missing:
        cols = "、".join(f"`{c}`" for c in important_missing)
        st.warning(
            f"以下重要字段在源文件中不存在：{cols}。"
            f"相关分析模块将在「序时账分析」中自动跳过并提示。"
        )

    _render_account_config_section()

    if st.button("确认识别结果，进入分析页", type="primary", width="stretch"):
        # 走 _pending_tab 中转：下次 rerun 在 segmented_control 实例化前写入其 key。
        st.session_state["_pending_tab"] = 1
        st.rerun()


def _render_account_config_section() -> None:
    """科目分类调整 UI。

    系统按"科目名称"自动分类（11 大类，单向优先级匹配）。
    用户只在自动分类与本项目实际不符时，对该行手工调整生效分类。
    """
    df_unified = st.session_state.get("df_unified")
    if df_unified is None or df_unified.empty:
        return

    overrides = _get_overrides()
    overview = account_classifier.build_account_overview(df_unified, overrides=overrides)
    if overview.empty:
        return

    auto_count = (overview["自动分类"] != CAT_UNCATEGORIZED).sum()
    total = len(overview)
    manual_count = (overview["人工分类"] != "").sum()
    badge = f"自动命中 {auto_count}/{total} 个科目"
    if manual_count:
        badge += f"，人工调整 {manual_count} 项"

    with st.expander(f"⚙️ 科目分类调整 — {badge}", expanded=True):
        st.caption(
            "系统按「科目名称」关键词自动判断每个科目的业务类别。"
            "若某行的「自动分类」与本项目账务实质不符，请在「人工分类」列下拉调整；"
            "未分类的科目不会进入任何分析模块。"
        )

        editor_df = overview.copy()
        editor_df["金额(亿)"] = editor_df["金额"] / 1e8
        editor_df = editor_df[
            ["科目编号", "科目名称", "行数", "金额(亿)", "自动分类", "人工分类"]
        ]

        manual_options = [""] + list(ALL_CATEGORIES)

        edited = st.data_editor(
            editor_df,
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=["科目编号", "科目名称", "行数", "金额(亿)", "自动分类"],
            column_config={
                "科目编号": st.column_config.TextColumn("科目编号", width="small"),
                "科目名称": st.column_config.TextColumn("科目名称", width="medium"),
                "行数": st.column_config.NumberColumn("行数", format="%,d", width="small"),
                "金额(亿)": st.column_config.NumberColumn("金额(亿)", format="%.2f", width="small"),
                "自动分类": st.column_config.TextColumn(
                    "自动分类", help="基于科目名称自动识别（不可改，仅展示）", width="small"
                ),
                "人工分类": st.column_config.SelectboxColumn(
                    "人工分类",
                    help="留空则采用自动分类。下拉调整后该科目按所选类别参与分析。",
                    options=manual_options,
                    width="small",
                ),
            },
            key="account_classifier_editor",
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("应用分类", type="primary", width="stretch", key="apply_account_classifier"):
                new_overrides: dict[str, str] = {}
                for _, row in edited.iterrows():
                    code = str(row["科目编号"]).strip()
                    manual = str(row.get("人工分类", "")).strip()
                    auto = str(row.get("自动分类", "")).strip()
                    if not code or not manual:
                        continue
                    if manual not in ALL_CATEGORIES:
                        continue
                    if manual == auto:
                        continue
                    new_overrides[code] = manual
                st.session_state.account_category_overrides = new_overrides
                _clear_analysis_cache()
                st.success(f"已保存 {len(new_overrides)} 项人工分类。请进入「序时账分析」重新生成画像。")
                st.rerun()
        with col2:
            if st.button("清空人工分类", width="stretch", key="reset_account_classifier"):
                st.session_state.account_category_overrides = {}
                st.session_state.pop("account_classifier_editor", None)
                _clear_analysis_cache()
                st.success("已清空所有人工分类。")
                st.rerun()


def _get_overrides() -> dict[str, str]:
    raw = st.session_state.get("account_category_overrides")
    if isinstance(raw, dict):
        return {str(k).strip(): str(v).strip() for k, v in raw.items() if str(k).strip()}
    return {}


def _clear_analysis_cache() -> None:
    """配置变更后清空依赖科目前缀的分析缓存。"""
    for key in (
        "profiles", "profiles_version", "financials", "financials_version",
        "audit_llm_analysis", "cross_year_findings", "candidate_pool",
        "rule_results", "llm_judgments",
    ):
        if key in st.session_state:
            if isinstance(st.session_state[key], dict):
                st.session_state[key] = {}
            elif isinstance(st.session_state[key], list):
                st.session_state[key] = []
            else:
                st.session_state[key] = None
