"""
序时账审计分析平台 — Streamlit 主入口

运行：uv run streamlit run app.py
"""

from __future__ import annotations

import io
import json
import hashlib
import re
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st
import pandas as pd

# ── 页面配置（必须是第一个 st 调用）──
st.set_page_config(
    page_title="序时账审计分析平台",
    page_icon="⏿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 全局 CSS ──
st.markdown("""
<style>
/* ── 根变量 ── */
:root {
    --accent: #4f8ef7;
    --accent-soft: rgba(79, 142, 247, 0.12);
    --gold: #d4a853;
    --gold-soft: rgba(212, 168, 83, 0.10);
    --red: #f87171;
    --green: #4ade80;
    --radius: 6px;
    --radius-lg: 10px;
}

/* ── 全局字体 ── */
html, body, .stApp {
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
}

/* ── 卡片容器 ── */
[data-testid="stExpander"] details,
div[data-testid="stVerticalBlockBorderWrapper"] {
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: var(--radius-lg) !important;
    background: rgba(255,255,255,0.015) !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2) !important;
    transition: border-color 0.2s ease;
}
[data-testid="stExpander"] details:hover,
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(255,255,255,0.12) !important;
}

/* ── Metrics 指标卡 ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(79,142,247,0.06), rgba(79,142,247,0.02));
    border: 1px solid rgba(79,142,247,0.10);
    border-radius: var(--radius-lg);
    padding: 0.6rem 0.8rem;
    transition: border-color 0.2s ease;
}
[data-testid="stMetric"]:hover {
    border-color: rgba(79,142,247,0.22);
}
[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: rgba(220,226,234,0.55) !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-weight: 600 !important;
}

/* ── 按钮（圆角胶囊形）── */
.stButton > button {
    border-radius: 24px !important;
    font-weight: 500 !important;
    letter-spacing: 0.3px;
    transition: all 0.15s ease !important;
}
.stButton > button[kind="primary"] {
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    filter: brightness(1.1);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(79,142,247,0.3);
}

/* ── 数据表格 ── */
[data-testid="stDataFrame"] {
    border-radius: var(--radius-lg) !important;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.06) !important;
}

/* ── 分割线 ── */
hr, [data-testid="stDivider"] {
    border-color: rgba(255,255,255,0.06) !important;
    margin: 1.2rem 0 !important;
}

/* ── Checkbox / Toggle ── */
[data-testid="stCheckbox"] label {
    font-weight: 500 !important;
}

/* ── Expander 头部 ── */
[data-testid="stExpander"] summary {
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    color: rgba(220,226,234,0.85) !important;
}

/* ── 进度条 ── */
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--accent), #818cf8) !important;
    border-radius: 4px !important;
}

/* ── Radio / Segmented control ── */
[data-testid="stSegmentedControl"] {
    background: rgba(255,255,255,0.03) !important;
    border-radius: var(--radius) !important;
    padding: 3px !important;
}
[data-testid="stSegmentedControl"] label {
    border-radius: calc(var(--radius) - 2px) !important;
    transition: all 0.2s ease !important;
}

/* ── Selectbox / Text input ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] input,
.stTextArea textarea,
.stNumberInput input {
    border-radius: var(--radius) !important;
    border-color: rgba(255,255,255,0.10) !important;
}
[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stTextInput"] input:focus,
.stTextArea textarea:focus,
.stNumberInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(79,142,247,0.15) !important;
}

/* ── Tab 内部 st.tabs ── */
.stTabs [data-baseweb="tab"] {
    font-size: 0.85rem;
    font-weight: 500;
}
.stTabs [data-baseweb="tab-highlight"] {
    background: var(--accent) !important;
}

/* ── 侧边栏优化 ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1320 0%, #0c1117 100%);
    border-right: 1px solid rgba(255,255,255,0.05);
}
[data-testid="stSidebar"] .stMetric {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.04) !important;
}

/* ── 图表容器 ── */
.js-plotly-plot {
    border-radius: var(--radius-lg);
    overflow: hidden;
}

/* ── 滚动条 ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.08);
    border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }
</style>
""", unsafe_allow_html=True)

# ── 模块导入 ──
from modules.ingestion import load_files, summarize_years, detect_columns
from modules import column_check
from modules.profiler import build_profile, build_financial_summary, profiles_to_summary_text, financials_to_summary_text
from modules.visual_analysis import (
    DEFAULT_ADJUSTMENT_KEYWORDS,
    add_analysis_columns,
    build_ap_accrual_monthly_view_from_work,
    build_ap_accrual_entry_top10_from_work,
    build_ap_accrual_supplier_comparison_from_work,
    build_adjustment_views_from_work,
    build_expense_entry_top10_from_work,
    build_cost_focus_entries_from_work,
    build_cost_material_account_summary_from_work,
    build_income_cost_category_options_from_work,
    build_income_cost_abnormal_entry_top10_from_work,
    build_customer_revenue_entry_top10_from_work,
    build_customer_top10_from_work,
    build_monthly_revenue_cost_entry_top10_from_work,
    build_monthly_revenue_cost_view_from_work,
    build_other_receivable_entry_top10_from_work,
    build_other_receivable_monthly_view_from_work,
    build_other_payable_entry_top10_from_work,
    build_other_payable_monthly_view_from_work,
    build_revenue_customer_material_summary_from_work,
    build_revenue_customer_monthly_focus_from_work_map,
    build_revenue_focus_entries_from_work,
    build_supplier_payable_entry_top10_from_work,
    build_supplier_top10_from_work,
)
from modules.cross_year import run_cross_year_analysis, findings_to_summary_text
from modules.audit_llm_analysis import (
    build_audit_analysis_payload,
    build_multi_year_audit_analysis_payload,
    generate_module_recommendations,
    generate_overview_analysis,
)
from modules.rule_generator import generate_rules_config, default_rules_config
from modules.rule_engine import run_all_rules, hits_summary
from modules.llm_verifier import verify_with_llm
from modules.reporter import generate_report
from modules import knowledge_base as kb
from modules import candidate_pool as cp
from modules import llm_config
from modules.formatting import (
    escape_html as _escape_html,
    format_list as _format_list,
    format_money as _format_money,
    format_multiplier as _format_multiplier,
    format_percent as _format_percent,
    format_years as _format_years,
    plain_value as _plain_value,
)
from components.chart_selection import (
    parse_event_points as _parse_event_points,
    selected_ap_accrual_point as _selected_ap_accrual_point,
    selected_bar_label as _selected_bar_label,
    selected_bar_label_and_direction as _selected_bar_label_and_direction,
    selected_dataframe_focus_row_index as _selected_dataframe_focus_row_index,
    selected_dataframe_row_index as _selected_dataframe_row_index,
    selected_dataframe_row_indices as _selected_dataframe_row_indices,
    selected_expense_cross_year_point as _selected_expense_cross_year_point,
    selected_income_cost_abnormal_point as _selected_income_cost_abnormal_point,
    selected_monthly_metric_point as _selected_monthly_metric_point,
    toggle_chart_selection as _toggle_chart_selection,
)
from modules.rule_text import (
    collect_rule_changes as _collect_rule_changes,
    format_param_value as _format_param_value,
    generic_param_lines as _generic_param_lines,
    rule_change_lines as _rule_change_lines,
    rule_condition_lines as _rule_condition_lines,
    rule_counts as _rule_counts,
)
from components.llm_orchestration import (
    backfill_recommendation_condition as _backfill_recommendation_condition,
    detail_for_recommendation as _lo_detail_for_recommendation,
    normalise_recommendation_condition as _normalise_recommendation_condition,
    recommendation_condition_text as _recommendation_condition_text,
    recommendation_matches_module as _recommendation_matches_module,
    recommendation_target_text as _recommendation_target_text,
    records_for_payload as _records_for_payload,
    unified_llm_key as _unified_llm_key,
)
from components.candidate_actions import (
    CANDIDATE_TAG_OPTIONS,
    amount_column_config as _amount_column_config,
    detail_amount_series as _detail_amount_series,
    detail_metrics as _detail_metrics,
    render_candidate_add_popover as _ca_render_candidate_add_popover,
    render_detail_with_actions as _ca_render_detail_with_actions,
    render_focused_voucher_detail as _render_focused_voucher_detail,
    reset_editor_state as _reset_editor_state,
    resolve_focused_voucher as _resolve_focused_voucher,
    style_selected_detail_rows as _style_selected_detail_rows,
)
from components.sidebar import render_sidebar as _sidebar_render
from components.tabs.upload import render_upload_tab
from components.tabs.rules import render_rules_tab
from components.tabs.sampling import render_sampling_tab
from components.tabs.analysis import (
    render_adjustment_main as _render_adjustment_main_impl,
    render_analysis_tab,
    render_working_capital_main as _render_working_capital_main_impl,
)
from components.charts import (
    monthly_trend_chart, amount_distribution_chart, voucher_type_pie,
    profile_amount_percentile_table, profile_temporal_table, profile_benford_table,
    month_end_heatmap, user_bar_chart, benford_first_digit_chart, cross_year_revenue_chart,
    multi_year_financial_overview,
    cross_year_findings_chart, rule_hit_bar, risk_level_pie,
    cost_structure_chart, expense_breakdown_chart, cross_year_expense_compare_chart,
    audit_monthly_revenue_cost_chart, customer_revenue_top_chart,
    supplier_payables_top_chart, audit_income_cost_abnormal_chart,
    ap_accrual_monthly_chart,
    ap_accrual_supplier_share_chart,
    other_receivable_monthly_chart,
    other_payable_monthly_chart,
)

# ── 全局常量（来自 config/）──
from config.constants import (
    RULE_ORDER, RULE_META, PARAM_LABELS,
    DEFAULT_LLM_CONFIG, PROFILES_VERSION, FINANCIALS_VERSION, AUDIT_CACHE_VERSION,
    PROJECT_MEMORY_KEYS,
)



def _initial_llm_config() -> dict[str, str]:
    saved_default = kb.get_default_llm_profile()
    if saved_default:
        return llm_config.normalize(saved_default)
    return DEFAULT_LLM_CONFIG.copy()

def _init_state():
    defaults = {
        "df_unified": None,
        "year_map": {},
        "year_summary": [],
        "missing_columns": [],
        "column_mapping": {},
        "account_category_overrides": {},
        "profiles": {},
        "profiles_version": None,
        "cross_year_findings": [],
        "financials": {},
        "financials_version": None,
        "audit_llm_analysis": {},
        "candidate_pool": [],
        "llm_config": _initial_llm_config(),
        "rules_config": None,
        "rule_results": [],
        "llm_judgments": {},
        "report_path": None,
        "report_stats": {},
        "engagement_name": "",
        "loaded_file_signature": None,
        "loaded_project_id": None,
        "upload_widget_nonce": 0,
        "active_tab": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def _has_project_payload() -> bool:
    return st.session_state.get("df_unified") is not None


def _has_loaded_years() -> bool:
    return bool(st.session_state.get("year_map"))


def _project_payload() -> dict:
    return {key: st.session_state.get(key) for key in PROJECT_MEMORY_KEYS}


# 以下均为对 modules/llm_config 的薄封装：app.py 只负责把 session_state 接进来，
# 真正的规范化 / 解析逻辑收在单一事实来源模块里。
def _llm_config() -> dict[str, str]:
    return llm_config.normalize(st.session_state.get("llm_config"))


def _save_llm_config(cfg: dict[str, str]) -> None:
    st.session_state.llm_config = llm_config.normalize({**_llm_config(), **(cfg or {})})


def _llm_model() -> str:
    return _llm_config()["model"]


def _llm_base_url() -> str:
    return _llm_config()["base_url"]


def _keychain_account() -> str:
    return llm_config.key_account(_llm_config())


def _resolve_api_key() -> tuple[str, str]:
    return llm_config.resolve_key(
        _keychain_account(),
        manual=st.session_state.get("_manual_api_key", ""),
    )


def _project_name_exists(project_name: str, exclude_project_id: str | None = None) -> bool:
    clean_name = project_name.strip()
    if not clean_name:
        return False
    candidate_id = kb.project_id_for_name(clean_name)
    for project in kb.list_projects():
        if project.get("project_id") == exclude_project_id:
            continue
        if project.get("project_id") == candidate_id or project.get("project_name", "").strip() == clean_name:
            return True
    return False


def _set_project_name_input(project_name: str) -> None:
    st.session_state["_pending_project_name_input"] = project_name.strip()


def _set_llm_config_inputs() -> None:
    """把当前方案推入侧边栏表单的 widget state（载入方案/项目后调用，使表单同步显示）。"""
    cfg = _llm_config()
    st.session_state["llm_profile_name_input"] = cfg["profile_name"]
    st.session_state["llm_base_url_input"] = cfg["base_url"]
    st.session_state["llm_model_input"] = cfg["model"]


def _save_current_project_state() -> tuple[bool, str]:
    project_name = st.session_state.get("engagement_name", "").strip()
    if not project_name:
        return False, "请先填写项目名称。"
    project_id = st.session_state.get("loaded_project_id")
    if _project_name_exists(project_name, exclude_project_id=project_id):
        return False, f"项目名称“{project_name}”已存在。请先载入该项目，或换一个名称。"

    # 手动保存是低频操作，强制重写重数据以保证落盘正确（不依赖结构签名）。
    metadata = kb.save_project_state(project_name, _project_payload(), project_id=project_id, data_changed=True)
    st.session_state.loaded_project_id = metadata["project_id"]
    _set_project_name_input(project_name)
    years = "、".join(str(y) for y in metadata.get("years", [])) or "未识别"
    row_count = metadata.get("row_count", 0)
    if row_count:
        return True, f"已保存：{project_name}（{years}，{row_count:,} 行）"
    return True, f"已保存空白项目：{project_name}"


def _autosave_current_project_state(data_changed: bool = False) -> None:
    """自动保存。``data_changed=True`` 用于数据集本身被替换的路径（如重新上传），
    强制重写重数据；其余轻状态变更走默认快路径（按结构签名决定是否重写 df）。"""
    project_name = st.session_state.get("engagement_name", "").strip()
    project_id = st.session_state.get("loaded_project_id")
    if not project_name:
        return
    if not project_id and not _has_project_payload():
        return
    if not project_id and _project_name_exists(project_name):
        return
    try:
        metadata = kb.save_project_state(
            project_name, _project_payload(), project_id=project_id, data_changed=data_changed
        )
        st.session_state.loaded_project_id = metadata["project_id"]
    except Exception:
        # 自动保存失败不应打断当前分析流程；手动保存时会显示具体错误。
        pass


# 候选库写入入口预绑定项目自动保存回调，使调用签名与注入 helper key 维持不变。
_render_candidate_add_popover = functools.partial(
    _ca_render_candidate_add_popover, autosave=_autosave_current_project_state
)
_render_detail_with_actions = functools.partial(
    _ca_render_detail_with_actions, autosave=_autosave_current_project_state
)


def _restore_project_state(project_id: str) -> dict:
    loaded = kb.load_project_state(project_id)
    state = loaded["state"]
    metadata = loaded.get("metadata", {})
    for key in PROJECT_MEMORY_KEYS:
        if key in state:
            st.session_state[key] = state[key]
    if not st.session_state.get("engagement_name") and metadata.get("project_name"):
        st.session_state.engagement_name = metadata["project_name"]
    st.session_state.loaded_project_id = project_id
    _set_project_name_input(st.session_state.get("engagement_name", ""))
    _set_llm_config_inputs()
    st.session_state.upload_widget_nonce = st.session_state.get("upload_widget_nonce", 0) + 1
    return metadata


def _reset_current_project(project_name: str = "") -> None:
    st.session_state.df_unified = None
    st.session_state.year_map = {}
    st.session_state.year_summary = []
    st.session_state.missing_columns = []
    st.session_state.column_mapping = {}
    st.session_state.account_category_overrides = {}
    st.session_state.profiles = {}
    st.session_state.profiles_version = None
    st.session_state.cross_year_findings = []
    st.session_state.financials = {}
    st.session_state.financials_version = None
    st.session_state.audit_llm_analysis = {}
    st.session_state.candidate_pool = []
    st.session_state.rules_config = None
    st.session_state.rule_results = []
    st.session_state.llm_judgments = {}
    st.session_state.report_path = None
    st.session_state.report_stats = {}
    if "final_samples" in st.session_state:
        del st.session_state.final_samples
    st.session_state.engagement_name = project_name.strip()
    st.session_state.loaded_file_signature = None
    st.session_state.loaded_project_id = None
    _set_project_name_input(project_name)
    _set_llm_config_inputs()
    st.session_state["_pending_new_project_name"] = ""
    st.session_state.upload_widget_nonce = st.session_state.get("upload_widget_nonce", 0) + 1


def _create_blank_project(project_name: str) -> tuple[bool, str]:
    clean_name = project_name.strip()
    if not clean_name:
        return False, "请先输入新项目名称。"
    if _project_name_exists(clean_name):
        return False, f"项目名称“{clean_name}”已存在，请换一个名称或直接载入历史项目。"

    _reset_current_project(clean_name)
    metadata = kb.save_project_state(clean_name, _project_payload())
    st.session_state.loaded_project_id = metadata["project_id"]
    return True, f"已创建空白项目：{clean_name}"


def _project_option_label(project: dict) -> str:
    name = project.get("project_name") or project.get("project_id", "未命名项目")
    years = "、".join(str(y) for y in project.get("years", [])) or "空白"
    rows = int(project.get("row_count", 0) or 0)
    updated = project.get("updated_at", "")
    return f"{name} | {years} | {rows:,} 行 | {updated}"


def _llm_profile_option_label(profile: dict) -> str:
    name = profile.get("profile_name") or profile.get("profile_id", "未命名方案")
    model = profile.get("model") or DEFAULT_LLM_CONFIG["model"]
    base_url = profile.get("base_url") or DEFAULT_LLM_CONFIG["base_url"]
    prefix = "默认 | " if profile.get("is_default") else ""
    return f"{prefix}{name} | {model} | {base_url}"


# ── 侧边栏调用 ──
_sidebar_render(
    _save_current_project_state=_save_current_project_state,
    _restore_project_state=_restore_project_state,
    _reset_current_project=_reset_current_project,
    _create_blank_project=_create_blank_project,
    _project_option_label=_project_option_label,
    _llm_profile_option_label=_llm_profile_option_label,
    _save_llm_config=_save_llm_config,
    _set_llm_config_inputs=_set_llm_config_inputs,
    _initial_llm_config=_initial_llm_config,
    _resolve_api_key=_resolve_api_key,
    _llm_config=_llm_config,
    _llm_model=_llm_model,
    _llm_base_url=_llm_base_url,
    _keychain_account=_keychain_account,
    _has_project_payload=_has_project_payload,
    _project_name_exists=_project_name_exists,
    _set_project_name_input=_set_project_name_input,
    DEFAULT_LLM_CONFIG=DEFAULT_LLM_CONFIG,
)

# ─────────────────────────────────────────────
# 主内容区
# ─────────────────────────────────────────────


def _can_use_llm() -> bool:
    return bool(st.session_state.get("_api_key", ""))

def _uploaded_files_signature(uploaded_files) -> tuple[tuple[str, int | None], ...]:
    return tuple(
        (file.name, getattr(file, "size", None))
        for file in uploaded_files
    )

def _clear_loaded_data():
    st.session_state.df_unified = None
    st.session_state.year_map = {}
    st.session_state.year_summary = []
    st.session_state.missing_columns = []
    st.session_state.column_mapping = {}
    st.session_state.account_category_overrides = {}
    st.session_state.loaded_file_signature = None
    _clear_analysis_results()

def _clear_analysis_results():
    st.session_state.profiles = {}
    st.session_state.profiles_version = None
    st.session_state.cross_year_findings = []
    st.session_state.financials = {}
    st.session_state.financials_version = None
    st.session_state.audit_llm_analysis = {}
    st.session_state.candidate_pool = []
    st.session_state.rules_config = None
    st.session_state.rule_results = []
    st.session_state.llm_judgments = {}
    st.session_state.report_path = None
    st.session_state.report_stats = {}


def _require_loaded_data() -> None:
    """Check if data is loaded. Returns True if OK, False if not."""
    if _has_project_payload() and _has_loaded_years():
        return True
    st.info("请先在「上传数据」页签中上传序时账文件。")
    return False


def _expense_summary_table(financial: dict) -> pd.DataFrame:
    expenses = dict(financial.get("expenses", {}))
    if financial.get("rd_expense", 0) != 0:
        expenses["研发费用"] = financial["rd_expense"]
    if financial.get("financial_expense", 0) != 0:
        expenses["财务费用(汇兑)"] = financial["financial_expense"]
    if financial.get("tax_surcharge", 0) != 0:
        expenses["税金及附加"] = financial["tax_surcharge"]

    items = sorted(expenses.items(), key=lambda x: x[1], reverse=True)
    total = sum(value for _, value in items)
    rows = [
        {
            "费用类别": category,
            "金额": value,
            "占比": value / total if total else 0,
        }
        for category, value in items
    ]
    return pd.DataFrame(rows)


def _cross_year_expense_table(financials: dict[int, dict]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for year, financial in sorted(financials.items()):
        summary = _expense_summary_table(financial)
        if summary.empty:
            continue
        for row in summary.to_dict("records"):
            rows.append(
                {
                    "年份": int(year),
                    "费用类别": str(row.get("费用类别", "")),
                    "金额": float(row.get("金额", 0) or 0),
                    "占比": float(row.get("占比", 0) or 0),
                }
            )
    return pd.DataFrame(rows)


CHART_TAG_PRESETS: dict[str, dict[str, list[str]]] = {
    "月度收入成本": {
        "options": ["月度", "月度异常", "收入波动", "成本波动", "大额", "月末", "年末"],
        "default": ["月度", "月度异常"],
    },
    "异常方向": {
        "options": ["异常方向", "收入S异常", "成本H异常", "收入波动", "成本波动", "冲销调账"],
        "default": ["异常方向"],
    },
    "客户收入": {
        "options": ["客户", "客户集中", "收入波动", "大额", "月度"],
        "default": ["客户", "客户集中"],
    },
    "供应商应付": {
        "options": ["供应商", "供应商集中", "应付异常", "成本波动", "大额"],
        "default": ["供应商", "应付异常"],
    },
    "费用类别": {
        "options": ["费用波动", "成本科目", "大额", "月度异常"],
        "default": ["费用波动"],
    },
}

def _candidate_pool_voucher_ids() -> set[str]:
    return cp.active_candidate_voucher_ids(st.session_state.get("candidate_pool", []))


def _income_page_candidate_counts(year: int, category: str) -> dict[str, dict[Any, int]]:
    counts: dict[str, dict[Any, int]] = {"month": {}, "customer": {}, "supplier": {}}
    for group in st.session_state.get("candidate_pool", []) or []:
        if group.get("status", cp.DEFAULT_STATUS) == cp.EXCLUDED_STATUS:
            continue
        selector = group.get("selector") or {}
        try:
            selector_year = int(selector.get("year"))
        except (TypeError, ValueError):
            continue
        if selector_year != int(year):
            continue
        selector_category = selector.get("category")
        if selector_category and selector_category != category:
            continue
        voucher_count = int(group.get("voucher_count", 0) or len(group.get("voucher_ids", [])))
        kind = str(selector.get("kind", ""))
        month = selector.get("month")
        if month not in (None, "") and kind in {"monthly_income_cost", "income_cost_abnormal", "revenue_customer_month"}:
            try:
                month = int(month)
                counts["month"][month] = counts["month"].get(month, 0) + voucher_count
            except (TypeError, ValueError):
                pass
        customer = selector.get("customer")
        if customer and kind in {"customer_revenue", "revenue_customer_month", "revenue_customer_material"}:
            customer = str(customer)
            counts["customer"][customer] = counts["customer"].get(customer, 0) + voucher_count
        supplier = selector.get("supplier")
        if supplier and kind == "supplier_payable":
            supplier = str(supplier)
            counts["supplier"][supplier] = counts["supplier"].get(supplier, 0) + voucher_count
    return counts


def _dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    export_df = df.copy()
    for col in export_df.columns:
        if pd.api.types.is_datetime64_any_dtype(export_df[col]):
            export_df[col] = export_df[col].dt.strftime("%Y-%m-%d")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name=sheet_name[:31] or "Sheet1")
    return output.getvalue()


def _render_chart_title_with_download(
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
                data=_dataframe_to_excel_bytes(df, sheet_name=sheet_name),
                file_name=file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=key,
                help="下载当前图表对应的 Excel",
                width="stretch",
            )


def _cross_year_focus_text(category: str) -> str:
    focus_map = {
        "预提冲回配对": "关注年末计提在次年一季度是否足额冲回，判断是否存在跨期悬挂。",
        "预提冲回金额不符": "关注年末计提和期后冲回金额是否接近，判断是否存在跨年损益调节。",
        "收入跨年确认": "关注年末收入冲高后次年一月红字冲回，判断是否存在收入提前确认。",
        "期末余额持续累积": "关注应收、预付或其他应收余额是否连续堆积，判断资产是否虚增或长期未清理。",
        "对手方跨年资金循环": "关注同一对手方年末资金流出和次年年初资金流入是否高度匹配。",
        "费用科目年度突变": "关注费用科目是否跨年异常放量，判断是否存在集中确认或重分类。",
        "手工凭证占比持续上升": "关注手工过账比例是否连续抬升，判断内控自动化和职责分离是否弱化。",
        "新科目组合涌现": "关注历史未出现过的借贷科目组合，判断是否存在新业务通道或绕过既有流程。",
    }
    return focus_map.get(category, "关注跨年金额、比例、对手方和凭证线索是否共同指向同一异常模式。")


def _format_evidence_cell(key: str, value: Any) -> str:
    value = _plain_value(value)
    if value is None:
        return "无"
    if key in {
        "accrual_amount",
        "reversal_amount",
        "jan_reversal",
        "out_amount",
        "in_amount",
        "prev_amount",
        "curr_amount",
    }:
        return _format_money(value)
    if key == "coverage_ratio":
        return _format_percent(value)
    if key == "dec_ratio":
        return _format_multiplier(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, list):
        if all(isinstance(item, list) and len(item) == 2 for item in value):
            return "、".join(f"{item[0]}-{item[1]}" for item in value) if value else "无"
        return "、".join(str(v) for v in value) if value else "无"
    return str(value)


def _cross_year_evidence_rows(finding: Any) -> list[dict[str, str]]:
    labels = {
        "accrual_amount": ("年末预提金额", "年末已经计提、需要在期后核销或冲回的金额。"),
        "reversal_amount": ("次年Q1冲回金额", "次年一季度已找到的冲销或冲回金额。"),
        "coverage_ratio": ("冲回覆盖率", "覆盖率越低，跨期悬挂风险越高。"),
        "dec_ratio": ("12月收入放大倍数", "12月收入相对前11月均值的放大程度。"),
        "jan_reversal": ("次年1月红字冲回", "期后红字金额越大，越需要检查收入截止。"),
        "vendor": ("对手方编号", "用于定位需要进一步穿透的供应商或客户。"),
        "out_amount": ("年末流出金额", "年末向该对手方付出的资金规模。"),
        "in_amount": ("次年Q1流入金额", "次年一季度从同一对手方收回的资金规模。"),
        "account_prefix": ("科目前缀", "用于定位异常放量的会计科目。"),
        "category": ("科目类别", "按自动分类识别出的费用大类（费用 / 研发 / 财务 / 税金）。"),
        "prev_amount": ("上年发生额", "对比基准年份的发生额。"),
        "curr_amount": ("本年发生额", "异常年份的发生额。"),
        "new_pair_count": ("新增科目组合数", "历史未出现过的借贷组合数量。"),
        "sample_pairs": ("样例科目组合", "抽样展示的新增借贷组合，用于后续穿透。"),
    }
    evidence = _plain_value(getattr(finding, "evidence", {}) or {})
    rows: list[dict[str, str]] = [
        {
            "维度": "涉及年份",
            "观察值": _format_years(getattr(finding, "years_involved", [])),
            "怎么解读": "先按这些年度之间的交易连续性和期后变化做穿透。",
        },
        {
            "维度": "异常方向金额",
            "观察值": _format_money(getattr(finding, "amount", 0)),
            "怎么解读": "用于判断该异常是否值得进入审计抽样优先级。",
        },
    ]

    if evidence and all(str(k).isdigit() for k in evidence.keys()):
        for year, amount in sorted(evidence.items()):
            rows.append(
                {
                    "维度": f"{year}年余额/发生额",
                    "观察值": _format_money(amount),
                    "怎么解读": "用于观察跨年趋势是否连续累积或异常跳升。",
                }
            )
        return rows

    for key, value in evidence.items():
        label, explanation = labels.get(str(key), (str(key), "规则识别时保留的关键证据。"))
        rows.append(
            {
                "维度": label,
                "观察值": _format_evidence_cell(str(key), value),
                "怎么解读": explanation,
            }
        )
    return rows


def _render_cross_year_finding(finding: Any) -> None:
    st.markdown(f"**异常说明**：{finding.description}")
    st.caption(f"关注点：{_cross_year_focus_text(finding.category)}")
    st.dataframe(
        pd.DataFrame(_cross_year_evidence_rows(finding)),
        width="stretch",
        hide_index=True,
    )
    voucher_ids = _plain_value(getattr(finding, "voucher_ids", []) or [])
    if voucher_ids:
        st.caption(f"关联凭证：已识别 {len(voucher_ids)} 个凭证号，优先抽查金额最大或期后冲回相关凭证。")
    raw_evidence = _plain_value(getattr(finding, "evidence", {}) or {})
    if raw_evidence:
        with st.expander("技术明细（用于核对规则证据）", expanded=False):
            st.json(raw_evidence)


def _render_library_rules(lib_rules: list[dict[str, Any]]) -> None:
    if not lib_rules:
        st.info("💡 经验库里还没有可推荐的历史规则。")
        return

    for rule in lib_rules:
        name = rule.get("name") or "未命名规则"
        rate = rule.get("performance", {}).get("confirmation_rate", 0)
        category = rule.get("category") or "未分类"
        
        rate_color = "green" if rate >= 0.7 else ("orange" if rate >= 0.4 else "gray")
        
        with st.expander(f"📚 {name} | 历史确认率 :{rate_color}[{rate:.0%}]", expanded=False):
            st.markdown(f"**类别**：{category}")
            perf = rule.get("performance", {})
            st.caption(
                f"📊 历史表现：已在 {perf.get('engagements_used', 0)} 个项目中使用，"
                f"累计命中 {perf.get('total_hits', 0)}，累计确认 {perf.get('total_confirmed', 0)}。"
            )
            
            params = rule.get("parameters", {})
            if params:
                st.markdown("**⚙️ 经验参数**")
                for line in _generic_param_lines(params):
                    st.markdown(f"- {line}")
            
            rationale = rule.get("rationale", "")
            if rationale:
                st.success(f"**💡 经验说明**：{rationale}")
            
            notes = rule.get("applicable_context", {}).get("notes", "")
            if notes:
                st.info(f"📍 适用背景：{notes}")
            source_engagement = rule.get("source_engagement", "")
            if source_engagement:
                st.caption(f"来源项目：{source_engagement}")


@st.cache_data(show_spinner=False)
def _build_audit_cache(df: pd.DataFrame, cache_version: int = AUDIT_CACHE_VERSION) -> dict[str, pd.DataFrame]:
    _ = cache_version
    work = add_analysis_columns(df)
    return {
        "work": work,
        "monthly": build_monthly_revenue_cost_view_from_work(work),
        "customers": build_customer_top10_from_work(work),
        "suppliers": build_supplier_top10_from_work(work),
        "ap_accrual": build_ap_accrual_monthly_view_from_work(work),
        "other_receivable": build_other_receivable_monthly_view_from_work(work),
        "other_payable": build_other_payable_monthly_view_from_work(work),
    }


# 推荐取数预绑定共享视图缓存（仍在 app.py，因分析页签复用），调用点签名不变。
_detail_for_recommendation = functools.partial(
    _lo_detail_for_recommendation, build_audit_cache=_build_audit_cache
)


@st.cache_data(show_spinner=False)
def _build_adjustment_cache(
    df: pd.DataFrame,
    keywords: tuple[str, ...],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = add_analysis_columns(df)
    return build_adjustment_views_from_work(work, keywords=keywords)


def _audit_source_summary(df_year: pd.DataFrame) -> dict:
    posting_dates = pd.to_datetime(df_year["过账日期"], errors="coerce").dropna()
    months = sorted(posting_dates.dt.month.unique().tolist()) if not posting_dates.empty else []
    start_date = posting_dates.min().date().isoformat() if not posting_dates.empty else None
    end_date = posting_dates.max().date().isoformat() if not posting_dates.empty else None
    voucher_count = int(df_year["凭证编号"].nunique()) if "凭证编号" in df_year.columns else 0
    return {
        "row_count": int(len(df_year)),
        "voucher_count": voucher_count,
        "date_range": f"{start_date} ~ {end_date}" if start_date and end_date else "",
        "months_covered": [int(month) for month in months],
        "is_partial_year": len(months) < 12,
    }


def _build_year_audit_analysis_payload(year: int, df_year: pd.DataFrame, category: str) -> dict:
    year_cache = _build_audit_cache(df_year)
    year_work = year_cache["work"]
    year_category_options = build_income_cost_category_options_from_work(year_work)
    category_available = category == "总计" or category in year_category_options
    year_monthly_view = (
        year_cache["monthly"]
        if category == "总计"
        else build_monthly_revenue_cost_view_from_work(year_work, category=category)
    )
    adjustment_summary, _ = _build_adjustment_cache(df_year, tuple(DEFAULT_ADJUSTMENT_KEYWORDS))
    payload = build_audit_analysis_payload(
        year=year,
        category=category,
        monthly_view=year_monthly_view,
        customer_top=year_cache["customers"],
        supplier_top=year_cache["suppliers"],
        ap_accrual_monthly=year_cache["ap_accrual"],
        other_receivable_monthly=year_cache["other_receivable"],
        other_payable_monthly=year_cache["other_payable"],
        adjustment_summary=adjustment_summary,
        source_summary=_audit_source_summary(df_year),
    )
    payload["category_available"] = category_available
    payload["available_income_cost_categories"] = year_category_options
    return payload


def _income_cost_focus_payload(category: str) -> dict[str, Any]:
    return _build_income_cost_focus_payload(st.session_state.year_map, category)


@st.cache_data(show_spinner=False)
def _build_income_cost_focus_payload(
    year_map: dict[int, pd.DataFrame],
    category: str,
    cache_version: int = 1,
) -> dict[str, Any]:
    _ = cache_version
    yearly_rows = []
    work_map = {}
    for year, df_year in sorted(year_map.items()):
        cache = _build_audit_cache(df_year)
        work = cache["work"]
        work_map[int(year)] = work
        monthly = (
            cache["monthly"]
            if category == "总计"
            else build_monthly_revenue_cost_view_from_work(work, category=category)
        )
        customer_summary = build_customer_top10_from_work(work, top_n=15)
        supplier_payable_summary = build_supplier_top10_from_work(work, top_n=15)
        revenue_summary = build_revenue_customer_material_summary_from_work(work, category=category, top_n=12)
        cost_summary = build_cost_material_account_summary_from_work(work, category=category, top_n=12)
        expense_summary = _expense_summary_table(build_financial_summary(df_year, year))
        adjustment_summary, adjustment_detail = _build_adjustment_cache(df_year, tuple(DEFAULT_ADJUSTMENT_KEYWORDS))
        yearly_rows.append({
            "year": year,
            "source_summary": _audit_source_summary(df_year),
            "monthly_income_cost": _records_for_payload(monthly, limit=12),
            "customer_revenue_top": _records_for_payload(customer_summary, limit=15),
            "supplier_payable_top": _records_for_payload(supplier_payable_summary, limit=15),
            "revenue_customer_material_top": _records_for_payload(revenue_summary, limit=12),
            "cost_material_account_top": _records_for_payload(cost_summary, limit=12),
            "expense_category_top": _records_for_payload(expense_summary, limit=12),
            "ap_accrual_monthly_top": _records_for_payload(cache["ap_accrual"], limit=12),
            "other_receivable_monthly_top": _records_for_payload(cache["other_receivable"], limit=12),
            "other_payable_monthly_top": _records_for_payload(cache["other_payable"], limit=12),
            "adjustment_summary_top": _records_for_payload(adjustment_summary, limit=12),
            "adjustment_voucher_top": _records_for_payload(adjustment_detail, limit=20),
        })

    customer_monthly = build_revenue_customer_monthly_focus_from_work_map(
        work_map,
        category=category,
        top_customers=12,
    )
    cross_year_expense = _cross_year_expense_table(
        {int(year): build_financial_summary(df_year, int(year)) for year, df_year in sorted(year_map.items())}
    )
    payload = {
        "analysis_scope": "income_cost_candidate_recommendation",
        "income_cost_category": category,
        "unit": "原币金额；前端通常折算为万元展示",
        "years": sorted(year_map.keys()),
        "yearly_rows": yearly_rows,
        "revenue_customer_monthly_volatility_top": _records_for_payload(customer_monthly, limit=24),
        "cross_year_expense_compare_top": _records_for_payload(cross_year_expense, limit=60),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["signature"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return payload


def _render_candidate_recommendations(category: str) -> None:
    _render_candidate_recommendations_for_module(category, module_filter="收入成本", show_controls=True)


def _render_unified_generation_controls(category: str) -> None:
    _render_candidate_recommendations_for_module(category, module_filter="收入成本", show_controls=True, cards_only=False)


def _render_candidate_recommendations_for_module(
    category: str,
    module_filter: str,
    *,
    show_controls: bool = False,
    cards_only: bool = True,
) -> None:
    years = sorted(st.session_state.get("year_map", {}).keys())
    unified_key = _unified_llm_key(years, category)
    unified_cached = st.session_state.audit_llm_analysis.get(unified_key)

    if not _can_use_llm():
        st.info("未配置 API Key。手动加入疑点库仍可正常使用。")
        return

    def _add_recommendations(selected: list[tuple[int, dict[str, Any], bool]]) -> tuple[int, int]:
        added = 0
        skipped = 0
        pool = st.session_state.get("candidate_pool", [])
        for idx, rec, direct_final in selected:
            condition = _backfill_recommendation_condition(rec, category, module_filter)
            detail = _detail_for_recommendation(condition, category)
            if detail.empty:
                skipped += 1
                continue
            title = rec.get("title") or f"模型建议 {idx + 1}"
            group = cp.build_candidate_group(
                title=title,
                source_module=rec.get("source_module", "收入成本"),
                source_view=rec.get("source_view", "模型建议"),
                detail=detail,
                tags=["模型建议"] + [str(tag) for tag in rec.get("tags", [])],
                reason=rec.get("reason", ""),
                selector=condition,
                status=cp.MANUAL_FINAL_STATUS if direct_final else cp.DEFAULT_STATUS,
                created_by="llm",
                recommendation=rec,
            )
            pool = cp.add_candidate_group(pool, group)
            added += 1
        st.session_state.candidate_pool = pool
        if added:
            st.session_state.rule_results = []
            st.session_state.llm_judgments = {}
            st.session_state.report_stats = {}
            st.session_state.report_path = None
            _autosave_current_project_state()
        return added, skipped

    def _generate_recommendations(auto_add_all: bool = False) -> None:
        progress = st.progress(0)
        status = st.empty()
        status.text("正在整理财务概况与筛样输入数据...")
        with st.spinner("大模型正在执行智能分析…"):
            recommendation_payload = _income_cost_focus_payload(category)
            progress.progress(25)
            status.text("正在汇总财务概况输入...")
            analysis_year_payloads = [
                _build_year_audit_analysis_payload(year, df_year, category)
                for year, df_year in sorted(st.session_state.year_map.items())
            ]
            overview_payload = build_multi_year_audit_analysis_payload(
                year_payloads=analysis_year_payloads,
                category=category,
            )
            unified_payload = {
                "overview_payload": overview_payload,
                "recommendation_payload": recommendation_payload,
            }
            progress.progress(55)
            status.text("正在生成智能分析...")
            overview_result = generate_overview_analysis(
                payload=overview_payload,
                api_key=st.session_state.get("_api_key", ""),
                model=_llm_model(),
                base_url=_llm_base_url(),
            )
            module_payloads: dict[str, dict[str, Any]] = {
                "收入成本": recommendation_payload,
                "费用": {
                    "analysis_scope": "expense_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "expense_category_top": row.get("expense_category_top", []),
                            "cross_year_expense_compare_top": recommendation_payload.get("cross_year_expense_compare_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "暂估往来": {
                    "analysis_scope": "working_capital_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "ap_accrual_monthly_top": row.get("ap_accrual_monthly_top", []),
                            "other_receivable_monthly_top": row.get("other_receivable_monthly_top", []),
                            "other_payable_monthly_top": row.get("other_payable_monthly_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "调账冲销": {
                    "analysis_scope": "adjustment_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "adjustment_summary_top": row.get("adjustment_summary_top", []),
                            "adjustment_voucher_top": row.get("adjustment_voucher_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "跨年交叉稽核": {
                    "analysis_scope": "cross_year_candidate_recommendation",
                    "findings": [
                        {
                            "category": f.category,
                            "description": f.description,
                            "years_involved": f.years_involved,
                            "voucher_ids": f.voucher_ids,
                            "amount": f.amount,
                            "severity": f.severity,
                            "evidence": f.evidence,
                        }
                        for f in st.session_state.get("cross_year_findings", [])
                    ],
                },
                "统计画像": {
                    "analysis_scope": "profile_candidate_recommendation",
                    "profiles_text": profiles_to_summary_text(st.session_state.profiles),
                    "financials_text": financials_to_summary_text(st.session_state.financials),
                },
            }
            module_recommendations: dict[str, list[dict[str, Any]]] = {}
            module_names = ["收入成本", "费用", "暂估往来", "调账冲销", "跨年交叉稽核", "统计画像"]
            status.text("正在并行生成各模块建议...")
            future_to_module = {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                for module_name in module_names:
                    future = executor.submit(
                        generate_module_recommendations,
                        module_name=module_name,
                        payload=module_payloads[module_name],
                        api_key=st.session_state.get("_api_key", ""),
                        model=_llm_model(),
                        base_url=_llm_base_url(),
                    )
                    future_to_module[future] = module_name

                completed = 0
                for future in as_completed(future_to_module):
                    module_name = future_to_module[future]
                    completed += 1
                    status.text(f"正在汇总模块建议：{module_name} 已完成（{completed}/{len(module_names)}）")
                    progress.progress(55 + int(completed / len(module_names) * 30))
                    try:
                        module_result = future.result()
                        module_recommendations[module_name] = list(module_result.get("recommendations", []))
                    except Exception as module_error:
                        module_recommendations[module_name] = []
                        st.warning(f"{module_name} 模块建议生成失败，已跳过：{module_error}")

            result = {
                "overview_analysis": overview_result,
                "module_recommendations": module_recommendations,
                "input_signature": hashlib.sha1(json.dumps(unified_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16],
                "analysis_scope": "unified_overview_and_recommendation",
            }
            progress.progress(90)
            status.text("正在回填结果并分发到各模块...")
            st.session_state.audit_llm_analysis[unified_key] = result
            if auto_add_all:
                recommendations = list(module_recommendations.get(module_filter, []))
                added, skipped = _add_recommendations([(idx, rec, False) for idx, rec in enumerate(recommendations)])
                if added:
                    st.success(f"已生成并加入 {added} 条模型建议。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                else:
                    st.warning("模型已返回建议，但没有匹配到可加入疑点库的明细分录。")
            _autosave_current_project_state()
            status.text("大模型结果已生成")
            progress.progress(100)
            st.rerun(scope="app")

    if show_controls:
        generate_col, auto_add_col = st.columns(2)
        btn_label = "智能分析" if not unified_cached else "刷新智能分析"
        with generate_col:
            if st.button(btn_label, disabled=not _can_use_llm(), type="primary", width="stretch"):
                try:
                    _generate_recommendations(auto_add_all=False)
                except Exception as e:
                    st.error(f"生成模型建议失败：{e}")
        with auto_add_col:
            add_disabled = not unified_cached or not _can_use_llm()
            if st.button("一键加入疑点库", disabled=add_disabled, width="stretch", key=f"gen_add_all_llm_{unified_key}"):
                try:
                    recommendations = list(
                        (unified_cached or {}).get("module_recommendations", {}).get(module_filter, [])
                    )
                    if not recommendations:
                        st.warning("当前没有可加入的模型建议，请先执行智能分析。")
                    else:
                        added, skipped = _add_recommendations(
                            [(idx, rec, False) for idx, rec in enumerate(recommendations)]
                        )
                        _autosave_current_project_state()
                        if added:
                            st.success(f"已加入 {added} 条模型建议到疑点库。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                            st.rerun(scope="app")
                        else:
                            st.warning("模型建议没有匹配到可加入疑点库的明细分录。")
                except Exception as e:
                    st.error(f"加入疑点库失败：{e}")

    if not unified_cached:
        if not show_controls:
            st.info("请先在收入成本页签生成智能分析，再回到这里查看本模块结果。")
        return

    if not cards_only:
        return
    recommendations = list(((unified_cached.get("module_recommendations") or {}).get(module_filter, [])))
    filtered_recommendations = [
        rec for rec in recommendations
        if isinstance(rec, dict) and _recommendation_matches_module(rec, module_filter)
    ]
    if not filtered_recommendations:
        st.caption("模型未返回可操作建议。")
        return

    all_col = st.columns(1)[0]
    with all_col:
        if st.button("一键全部加入疑点库", width="stretch", key=f"add_all_llm_rec_{unified_key}_{module_filter}"):
            added, skipped = _add_recommendations([(idx, rec, False) for idx, rec in enumerate(filtered_recommendations)])
            if added:
                st.success(f"已加入 {added} 条模型建议。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                st.rerun(scope="app")
            else:
                st.warning("没有可加入的模型建议；建议条件没有匹配到明细分录。")

    # 当前疑点库中已有的凭证号集合
    pool_vids: set[str] = set()
    for g in st.session_state.get("candidate_pool", []) or []:
        for vid in g.get("voucher_ids", []):
            pool_vids.add(str(vid))

    for idx, rec in enumerate(filtered_recommendations, start=1):
        condition = _backfill_recommendation_condition(rec, category, module_filter)
        detail = _detail_for_recommendation(condition, category)
        stats = _detail_metrics(detail)
        detail_vids = set(detail["凭证编号"].astype(str).tolist()) if not detail.empty and "凭证编号" in detail.columns else set()
        in_pool = detail_vids & pool_vids
        pool_badge = f"✅ 已入库 {len(in_pool)}/{len(detail_vids)} 个" if in_pool else "⬜ 未入库"

        risk = rec.get("risk_level", "中")
        title = rec.get("title") or f"模型建议 {idx}"
        with st.container(border=True):
            st.markdown(f"**建议 {idx:02d} | [{risk}] {title}**  `{pool_badge}`")
            st.markdown(f"**建议抽样什么**：{_recommendation_target_text(rec)}")
            st.markdown(f"**为什么建议这个**：{rec.get('reason', '') or '模型未提供说明'}")
            st.caption(f"当前回查逻辑：{_recommendation_condition_text(condition, module_filter)}")
            st.caption(f"匹配结果：{stats['vouchers']:,} 个凭证 / {stats['rows']:,} 行 / 金额绝对值合计 {_format_money(stats['amount'])}")
            if detail.empty:
                st.caption("当前建议未匹配到明细。")
            else:
                tags = "、".join(str(tag) for tag in rec.get("tags", []))
                if tags:
                    st.caption(f"标签：{tags}")
                audit_procedure = str(rec.get("audit_procedure", "")).strip()
                if audit_procedure:
                    st.caption(f"建议核查动作：{audit_procedure}")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button(
                        "加入疑点库",
                        width="stretch",
                        key=f"llm_rec_add_{unified_key}_{module_filter}_{idx}",
                        type="primary",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, False)])
                        if added:
                            st.success("已加入疑点库。")
                            st.rerun(scope="app")
                        else:
                            st.warning("当前建议没有匹配到可加入疑点库的明细分录。")
                with action_col2:
                    if st.button(
                        "直入最终样本",
                        width="stretch",
                        key=f"llm_rec_final_add_{unified_key}_{module_filter}_{idx}",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, True)])
                        if added:
                            st.success("已直入最终样本。")
                            st.rerun(scope="app")
                        else:
                            st.warning("当前建议没有匹配到可直入最终样本的明细分录。")


def _render_working_capital_main(
    *,
    audit_cache: dict[str, pd.DataFrame],
    audit_work: pd.DataFrame,
    audit_year_sel: int,
) -> None:
    return _render_working_capital_main_impl(
        audit_cache=audit_cache,
        audit_work=audit_work,
        audit_year_sel=audit_year_sel,
        year_map=st.session_state.year_map,
        render_detail_with_actions=_render_detail_with_actions,
        selected_ap_accrual_point_fn=_selected_ap_accrual_point,
        selected_bar_label_and_direction_fn=_selected_bar_label_and_direction,
        selected_monthly_metric_point_fn=_selected_monthly_metric_point,
    )


def _render_adjustment_main(*, df_audit: pd.DataFrame, audit_year_sel: int) -> None:
    return _render_adjustment_main_impl(
        df_audit=df_audit,
        audit_year_sel=audit_year_sel,
        build_adjustment_cache_fn=_build_adjustment_cache,
        selected_dataframe_row_index_fn=_selected_dataframe_row_index,
        render_detail_with_actions=_render_detail_with_actions,
    )



# ── 顶部页签 ──
TAB_NAMES = ["上传数据", "序时账分析", "规则管理", "样本抽取"]


# ── 字段缺失影响矩阵：标准列 -> 受影响的分析模块 ──
_COLUMN_IMPACT_MAP: dict[str, list[str]] = {
    "凭证类型": ["手工凭证识别", "白名单过滤"],
    "供应商编号": ["供应商集中度", "应付暂估", "化整为零"],
    "客户": ["客户集中度", "收入分析"],
    "用户名": ["用户集中度", "职责分离分析"],
    "公司代码货币价值": ["所有金额相关分析（已退化为凭证货币价值）"],
    "过账期间": ["Period 13 年末调整识别"],
    "会计年度": ["跨年调账归集（缺失时按过账日期年份归集，可能错把期后调整记入次年）"],
    "文本": ["关键词搜索", "调账/冲销凭证识别", "敏感费用筛查"],
    "总账科目": ["所有科目维度分析（收入/成本/费用/暂估）"],
}


def _render_missing_columns_banner() -> None:
    """在分析页顶端展示缺失字段及其影响范围。"""
    missing = st.session_state.get("missing_columns", []) or []
    if not missing:
        return
    relevant = [c for c in missing if c in _COLUMN_IMPACT_MAP]
    if not relevant:
        return
    with st.expander(
        f"⚠️ 检测到 {len(relevant)} 个字段在源文件中缺失，部分分析将自动跳过",
        expanded=False,
    ):
        st.caption("以下字段在「上传数据」阶段未映射到源列，相关分析模块会被跳过并给出可审计提示。")
        rows = [
            {"缺失字段": col, "受影响的分析": "、".join(_COLUMN_IMPACT_MAP[col])}
            for col in relevant
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("如需补齐，请回到「上传数据」页签重新映射列。")

# 暴露经验库/配置加载告警（损坏文件不再被静默吞掉，符合「风险可见」）
for _load_warning in kb.consume_load_warnings():
    st.warning(f"⚠️ {_load_warning}")

# 页签状态用稳定 key 驱动，避免「动态 default + 无 key」导致的点击丢失/不切换。
# 程序化跳转（如上传后跳到分析页）走 _pending_tab 中转，在 widget 实例化前写入。
if "_pending_tab" in st.session_state:
    st.session_state.active_tab_name = TAB_NAMES[st.session_state.pop("_pending_tab")]
elif "active_tab_name" not in st.session_state:
    st.session_state.active_tab_name = TAB_NAMES[st.session_state.get("active_tab", 0)]

active_tab_name = st.segmented_control(
    "页签导航", TAB_NAMES,
    key="active_tab_name",
    selection_mode="single", label_visibility="collapsed"
)
# single 模式下点击已选项会返回 None（取消选择）；此时保持当前页签，不让界面悬空。
if active_tab_name not in TAB_NAMES:
    active_tab_name = TAB_NAMES[st.session_state.get("active_tab", 0)]
st.session_state.active_tab = TAB_NAMES.index(active_tab_name)

# ── Tab 1：上传数据 ──
if st.session_state.active_tab == 0:

    render_upload_tab(None,
        _require_loaded_data=_require_loaded_data,
        _has_project_payload=_has_project_payload,
        _has_loaded_years=_has_loaded_years,
        _clear_analysis_results=_clear_analysis_results,
        _clear_loaded_data=_clear_loaded_data,
        _uploaded_files_signature=_uploaded_files_signature,
        _autosave_current_project_state=_autosave_current_project_state,
    )

# ── 序时账分析 ──
if st.session_state.active_tab == 1:

    render_analysis_tab(None,
        _has_project_payload=_has_project_payload,
        _has_loaded_years=_has_loaded_years,
        _render_missing_columns_banner=_render_missing_columns_banner,
        _build_audit_cache=_build_audit_cache,
        _income_page_candidate_counts=_income_page_candidate_counts,
        _render_candidate_recommendations_for_module=_render_candidate_recommendations_for_module,
        _render_chart_title_with_download=_render_chart_title_with_download,
        _selected_monthly_metric_point=_selected_monthly_metric_point,
        _render_detail_with_actions=_render_detail_with_actions,
        _selected_income_cost_abnormal_point=_selected_income_cost_abnormal_point,
        _selected_bar_label=_selected_bar_label,
        _cross_year_expense_table=_cross_year_expense_table,
        _toggle_chart_selection=_toggle_chart_selection,
        _selected_expense_cross_year_point=_selected_expense_cross_year_point,
        _render_working_capital_main=_render_working_capital_main,
        _render_adjustment_main=_render_adjustment_main,
        _format_years=_format_years,
        _render_cross_year_finding=_render_cross_year_finding,
        _render_candidate_add_popover=_render_candidate_add_popover,
        _unified_llm_key=_unified_llm_key,
        _render_unified_generation_controls=_render_unified_generation_controls,
        _format_money=_format_money,
        _autosave_current_project_state=_autosave_current_project_state,
    )

# ── Tab 3：规则管理 ──
if st.session_state.active_tab == 2:

    render_rules_tab(None,
        _require_loaded_data=_require_loaded_data,
        _can_use_llm=_can_use_llm,
        _resolve_api_key=_resolve_api_key,
        _llm_model=_llm_model,
        _llm_base_url=_llm_base_url,
        _autosave_current_project_state=_autosave_current_project_state,
        _rule_counts=_rule_counts,
        _collect_rule_changes=_collect_rule_changes,
        _render_library_rules=_render_library_rules,
    )

# ── 样本抽取 ──
if st.session_state.active_tab == 3:

    render_sampling_tab(None,
        _has_project_payload=_has_project_payload,
        _has_loaded_years=_has_loaded_years,
        _candidate_pool_voucher_ids=_candidate_pool_voucher_ids,
        _rule_counts=_rule_counts,
        _format_money=_format_money,
        _can_use_llm=_can_use_llm,
        _llm_model=_llm_model,
        _llm_base_url=_llm_base_url,
        _autosave_current_project_state=_autosave_current_project_state,
        _reset_current_project=_reset_current_project,
    )
