"""
序时账审计分析平台 — Streamlit 主入口

运行：uv run streamlit run app.py
"""

from __future__ import annotations

import os
import io
import json
import hashlib
import re
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
from modules.ingestion import load_files, summarize_years
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
from modules import secret_store
from components.sidebar import render_sidebar as _sidebar_render
from components.tabs.upload import render_upload_tab
from components.tabs.rules import render_rules_tab
from components.tabs.analysis import (
    render_adjustment_main as _render_adjustment_main_impl,
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



def _normalise_llm_config(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    source = cfg or {}
    return {
        "profile_id": str(source.get("profile_id", "") or "").strip(),
        "profile_name": str(source.get("profile_name", DEFAULT_LLM_CONFIG["profile_name"]) or "").strip()
        or DEFAULT_LLM_CONFIG["profile_name"],
        "model": str(source.get("model", DEFAULT_LLM_CONFIG["model"]) or "").strip()
        or DEFAULT_LLM_CONFIG["model"],
        "base_url": str(source.get("base_url", DEFAULT_LLM_CONFIG["base_url"]) or "").strip()
        or DEFAULT_LLM_CONFIG["base_url"],
        "key_source": "env_or_keychain",
        "keychain_account": str(source.get("keychain_account", "default") or "").strip() or "default",
    }


def _initial_llm_config() -> dict[str, str]:
    saved_default = kb.get_default_llm_profile()
    if saved_default:
        return _normalise_llm_config(saved_default)
    return DEFAULT_LLM_CONFIG.copy()

def _init_state():
    defaults = {
        "df_unified": None,
        "year_map": {},
        "year_summary": [],
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


def _llm_config() -> dict[str, str]:
    cfg: dict[str, Any] = dict(DEFAULT_LLM_CONFIG)
    saved = st.session_state.get("llm_config")
    if isinstance(saved, dict):
        cfg.update({k: v for k, v in saved.items() if v is not None})
    return _normalise_llm_config(cfg)


def _save_llm_config(cfg: dict[str, str]) -> None:
    st.session_state.llm_config = _normalise_llm_config({**_llm_config(), **cfg})


def _llm_model() -> str:
    return _llm_config().get("model") or DEFAULT_LLM_CONFIG["model"]


def _llm_base_url() -> str:
    return _llm_config().get("base_url") or DEFAULT_LLM_CONFIG["base_url"]


def _keychain_account() -> str:
    cfg = _llm_config()
    account = (cfg.get("keychain_account") or "default").strip()
    return account or "default"


def _resolve_api_key() -> tuple[str, str]:
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key, "环境变量 DEEPSEEK_API_KEY"
    manual_key = st.session_state.get("_manual_api_key", "").strip()
    if manual_key:
        return manual_key, "本次会话输入"
    keychain_key = secret_store.get_secret(_keychain_account())
    if keychain_key:
        return keychain_key, f"本机钥匙串：{_keychain_account()}"
    return "", "未配置"


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
    cfg = _llm_config()
    st.session_state["llm_profile_name_input"] = cfg.get("profile_name", DEFAULT_LLM_CONFIG["profile_name"])
    st.session_state["llm_base_url_input"] = cfg.get("base_url", DEFAULT_LLM_CONFIG["base_url"])
    st.session_state["llm_model_input"] = cfg.get("model", DEFAULT_LLM_CONFIG["model"])
    st.session_state["llm_keychain_account_input"] = cfg.get("keychain_account", "default")


def _save_current_project_state() -> tuple[bool, str]:
    project_name = st.session_state.get("engagement_name", "").strip()
    if not project_name:
        return False, "请先填写项目名称。"
    project_id = st.session_state.get("loaded_project_id")
    if _project_name_exists(project_name, exclude_project_id=project_id):
        return False, f"项目名称“{project_name}”已存在。请先载入该项目，或换一个名称。"

    metadata = kb.save_project_state(project_name, _project_payload(), project_id=project_id)
    st.session_state.loaded_project_id = metadata["project_id"]
    _set_project_name_input(project_name)
    years = "、".join(str(y) for y in metadata.get("years", [])) or "未识别"
    row_count = metadata.get("row_count", 0)
    if row_count:
        return True, f"已保存：{project_name}（{years}，{row_count:,} 行）"
    return True, f"已保存空白项目：{project_name}"


def _autosave_current_project_state() -> None:
    project_name = st.session_state.get("engagement_name", "").strip()
    project_id = st.session_state.get("loaded_project_id")
    if not project_name:
        return
    if not project_id and not _has_project_payload():
        return
    if not project_id and _project_name_exists(project_name):
        return
    try:
        metadata = kb.save_project_state(project_name, _project_payload(), project_id=project_id)
        st.session_state.loaded_project_id = metadata["project_id"]
    except Exception:
        # 自动保存失败不应打断当前分析流程；手动保存时会显示具体错误。
        pass


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
    keychain_account = profile.get("keychain_account") or "default"
    prefix = "默认 | " if profile.get("is_default") else ""
    return f"{prefix}{name} | {model} | {base_url} | 钥匙串:{keychain_account}"


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


def _parse_event_points(event) -> list[dict] | None:
    """从 Plotly 图表 on_select 事件中提取 points 列表。"""
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    points = selection.get("points", []) if hasattr(selection, "get") else []
    return points if points else None


def _selected_bar_label(event) -> str | None:
    points = _parse_event_points(event)
    if not points:
        return None
    label = points[0].get("y")
    return str(label) if label else None


def _selected_expense_cross_year_point(event) -> tuple[int, str] | None:
    points = _parse_event_points(event)
    if not points:
        return None
    point = points[0]
    category = str(point.get("y", "") or point.get("x", ""))
    year = point.get("legendgroup")
    if not category or not year:
        return None
    try:
        return int(str(year)), str(category)
    except (TypeError, ValueError):
        return None


def _toggle_chart_selection(state_key: str, current_value: Any | None) -> Any | None:
    """保存图表选择；再次点中同一项时收起明细。"""
    previous_value = st.session_state.get(state_key)
    if current_value is None:
        st.session_state.pop(state_key, None)
        return None
    if previous_value == current_value:
        st.session_state.pop(state_key, None)
        return None
    st.session_state[state_key] = current_value
    return current_value

def _selected_bar_label_and_direction(event, direction_map: dict[int, str]) -> tuple[str, str] | None:
    points = _parse_event_points(event)
    if not points:
        return None

    point = points[0]
    label = point.get("y")
    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction = direction_map.get(curve_number)
    return (str(label), direction) if label and direction else None

def _selected_monthly_metric_point(event, direction_map: dict[int, str]) -> tuple[int, str] | None:
    points = _parse_event_points(event)
    if not points:
        return None

    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None

    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction = direction_map.get(curve_number)
    return (month, direction) if direction else None

def _selected_ap_accrual_point(event) -> tuple[int, str] | None:
    points = _parse_event_points(event)
    if not points:
        return None

    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None

    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction_map = {0: "credit", 1: "debit", 2: "net"}
    direction = direction_map.get(curve_number, "net")
    return month, direction

def _selected_income_cost_abnormal_point(event) -> tuple[int, str] | None:
    points = _parse_event_points(event)
    if not points:
        return None

    point = points[0]
    x_value = str(point.get("x", ""))
    try:
        month = int(x_value.replace("月", ""))
    except ValueError:
        return None

    curve_number = point.get("curve_number", point.get("curveNumber"))
    direction_map = {0: "income_s", 1: "cost_h"}
    direction = direction_map.get(curve_number)
    return (month, direction) if direction else None


def _selected_dataframe_row_index(event) -> int | None:
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    rows = selection.get("rows", []) if hasattr(selection, "get") else []
    if not rows:
        return None
    try:
        return int(rows[0])
    except (TypeError, ValueError):
        return None


def _selected_dataframe_row_indices(event) -> list[int]:
    if not event:
        return []
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    rows = selection.get("rows", []) if hasattr(selection, "get") else []
    selected_rows: list[int] = []
    for row in rows:
        try:
            selected_rows.append(int(row))
        except (TypeError, ValueError):
            continue
    return selected_rows


def _selected_dataframe_focus_row_index(event) -> int | None:
    if not event:
        return None
    if hasattr(event, "get"):
        selection = event.get("selection", {})
    else:
        selection = getattr(event, "selection", {})
    if hasattr(selection, "get"):
        cells = selection.get("cells", [])
        rows = selection.get("rows", [])
    else:
        cells = []
        rows = []

    if cells:
        cell = cells[0]
        if isinstance(cell, str):
            row_text = cell.split(":", 1)[0]
        elif isinstance(cell, dict):
            row_text = cell.get("row", cell.get("rowIndex", ""))
        else:
            row_text = ""
        try:
            return int(row_text)
        except (TypeError, ValueError):
            pass

    if rows:
        try:
            return int(rows[-1])
        except (TypeError, ValueError):
            return None
    return None


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


def _amount_column_config(amount_cols: list[str] | None = None) -> dict:
    config = {
        "过账日期": st.column_config.DateColumn("过账日期", format="YYYY-MM-DD"),
        "公司代码货币价值": st.column_config.NumberColumn("公司代码货币价值", format="¥ %,.2f"),
        "凭证货币价值": st.column_config.NumberColumn("凭证货币价值", format="¥ %,.2f"),
    }
    for col in amount_cols or []:
        config[col] = st.column_config.NumberColumn(col, format="¥ %,.2f")
    return config


CANDIDATE_TAG_OPTIONS = [
    "收入波动", "客户", "供应商", "物料组", "成本波动", "费用波动", "成本科目", "大额", "月度", "月末", "年末",
    "P13", "异常方向", "冲销调账", "暂估异常", "往来异常", "跨年异常", "模型建议",
    "月度异常", "客户集中", "供应商集中", "收入S异常", "成本H异常", "应付异常",
]

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

AMOUNT_FILTER_OPTIONS = [
    ("全部金额", 0.0),
    ("5万以上", 5e4),
    ("10万以上", 1e5),
    ("50万以上", 5e5),
    ("100万以上", 1e6),
]


def _detail_metrics(detail: pd.DataFrame) -> dict[str, float | int]:
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


def _detail_amount_series(detail: pd.DataFrame) -> pd.Series:
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


def _apply_click_amount_filter(detail: pd.DataFrame, key: str) -> tuple[pd.DataFrame, float]:
    if detail.empty:
        return detail, 0.0

    threshold_map = {label: threshold for label, threshold in AMOUNT_FILTER_OPTIONS}
    default_label = AMOUNT_FILTER_OPTIONS[0][0]
    selected_label = st.radio(
        "金额筛选",
        options=[label for label, _ in AMOUNT_FILTER_OPTIONS],
        index=0,
        horizontal=True,
        key=f"{key}_amount_filter",
        label_visibility="collapsed",
    )
    threshold = threshold_map.get(selected_label, 0.0)
    if threshold <= 0:
        return detail, threshold

    amount_series = _detail_amount_series(detail)
    filtered = detail.loc[amount_series >= threshold].copy()
    return filtered, threshold


def _save_candidate_group(
    *,
    title: str,
    source_module: str,
    source_view: str,
    detail: pd.DataFrame,
    tags: list[str],
    reason: str,
    selector: dict[str, Any],
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
    _autosave_current_project_state()


def _existing_candidate_group(
    *,
    source_view: str,
    selector: dict[str, Any],
    detail: pd.DataFrame,
) -> dict[str, Any] | None:
    group_id = cp.candidate_id_for(
        source_view=source_view,
        selector=selector,
        voucher_ids=detail["凭证编号"].dropna().astype(str).tolist() if "凭证编号" in detail.columns else [],
    )
    for group in st.session_state.get("candidate_pool", []) or []:
        if group.get("group_id") == group_id:
            return group
    return None


def _render_candidate_add_popover(
    *,
    key: str,
    title: str,
    source_module: str,
    source_view: str,
    detail: pd.DataFrame,
    selector: dict[str, Any],
    default_tags: list[str],
    default_reason: str,
    created_by: str = "manual",
    recommendation: dict[str, Any] | None = None,
) -> None:
    if detail.empty:
        return
    stats = _detail_metrics(detail)
    with st.popover("加入疑点库", use_container_width=True):
        st.caption(
            f"将按当前条件加入全量匹配分录：{stats['rows']:,} 行，"
            f"{stats['vouchers']:,} 个凭证，金额绝对值合计 {_format_money(stats['amount'])}。"
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
        if st.button("确认加入", type="primary", use_container_width=True, key=f"{key}_add"):
            _save_candidate_group(
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
            )
            st.success("已加入疑点库。")


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
                use_container_width=True,
            )


def _format_money(value: Any) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 1e8:
        return f"{sign}{amount / 1e8:.2f}亿元"
    if amount >= 1e4:
        return f"{sign}{amount / 1e4:.1f}万元"
    return f"{sign}{amount:,.0f}元"


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return str(value)


def _format_multiplier(value: Any) -> str:
    try:
        return f"{float(value):.1f}倍"
    except (TypeError, ValueError):
        return str(value)


def _format_list(values: Any) -> str:
    if isinstance(values, list):
        return "、".join(str(v) for v in values)
    return str(values)


def _plain_value(value: Any) -> Any:
    """Convert numpy/pandas scalars into UI-friendly Python values."""
    if isinstance(value, dict):
        return {str(_plain_value(k)): _plain_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain_value(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _format_years(values: Any) -> str:
    years = _plain_value(values)
    if not years:
        return "未标明"
    if not isinstance(years, list):
        years = [years]
    return "、".join(str(year) for year in years)


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
        use_container_width=True,
        hide_index=True,
    )
    voucher_ids = _plain_value(getattr(finding, "voucher_ids", []) or [])
    if voucher_ids:
        st.caption(f"关联凭证：已识别 {len(voucher_ids)} 个凭证号，优先抽查金额最大或期后冲回相关凭证。")
    raw_evidence = _plain_value(getattr(finding, "evidence", {}) or {})
    if raw_evidence:
        with st.expander("技术明细（用于核对规则证据）", expanded=False):
            st.json(raw_evidence)


def _format_param_value(key: str, value: Any) -> str:
    if key in {"max_single_amount", "min_total", "round_number_threshold", "repeat_threshold",
               "holiday_min_amount", "pnl_amount_threshold", "min_amount", "large_threshold",
               "min_revenue_amount"}:
        return _format_money(value)
    if key in {"window_days", "repeat_window_days", "match_window_days", "month_end_days"}:
        return f"{value}天"
    if key in {"min_txn_count", "repeat_min_count", "frequent_count", "max_sample_size",
               "max_candidate_groups", "max_related_vouchers"}:
        return f"{value}"
    if key in {"amount_tolerance", "coverage_threshold", "concentration_threshold", "margin_threshold",
               "low_margin_threshold", "max_loss_rate", "min_match_score"}:
        return _format_percent(value)
    if key in {"burst_multiplier", "multiplier", "dec_multiplier", "baseline_multiplier"}:
        return _format_multiplier(value)
    if key == "months":
        return "、".join(f"{m}月" for m in value) if isinstance(value, list) else str(value)
    if key in {"keywords", "whitelist_keywords", "whitelist_voucher_types",
               "income_account_prefixes", "cost_account_prefixes"}:
        return _format_list(value)
    if key == "categories" and isinstance(value, dict):
        parts = []
        for name, cfg in value.items():
            threshold = cfg.get("threshold")
            parts.append(f"{name}≥{_format_money(threshold)}")
        return "；".join(parts)
    return str(value)


def _generic_param_lines(params: dict[str, Any]) -> list[str]:
    lines = []
    for key, value in params.items():
        label = PARAM_LABELS.get(key, key)
        lines.append(f"{label}：{_format_param_value(key, value)}")
    return lines


def _rule_condition_lines(rule_key: str, rule_cfg: dict[str, Any]) -> list[str]:
    c = rule_cfg or {}
    if rule_key == "splitting":
        return [
            f"同一供应商在 {c.get('window_days', '—')} 天内至少 {c.get('min_txn_count', '—')} 笔。",
            f"单笔不超过 {_format_money(c.get('max_single_amount', 0))}，合计超过 {_format_money(c.get('min_total', 0))}。",
            f"当日笔数超过该供应商日均 {_format_multiplier(c.get('burst_multiplier', 0))}，同时继续关注同日/窗口内金额高度相似的模式。",
        ]
    if rule_key == "large_amount":
        return [
            f"把最大行金额达到 {_format_money(c.get('round_number_threshold', 0))} 的整数金额交易先拉出来。",
            f"同一供应商在 {c.get('repeat_window_days', '—')} 天内出现至少 {c.get('repeat_min_count', '—')} 笔、每笔达到 {_format_money(c.get('repeat_threshold', 0))} 的重复大额也进入样本。",
            f"若节假日/周末过账金额达到 {_format_money(c.get('holiday_min_amount', 0))}，且操作者周末率显著高于公司基线，也一并标记。",
        ]
    if rule_key == "manual_entry":
        return [
            "先识别 SA 型凭证或文本中直接出现“手工”的凭证。",
            f"重点关注损益科目金额达到 {_format_money(c.get('pnl_amount_threshold', 0))} 的手工凭证。",
            f"同时关注月末前 {c.get('month_end_days', '—')} 天内的手工调整，以及手工率显著高于公司均值的用户。",
        ]
    if rule_key == "accrual_anomaly":
        return [
            f"先抓取金额不低于 {_format_money(c.get('min_amount', 0))} 的非常规预提/计提。",
            f"如果 {c.get('match_window_days', '—')} 天内没有找到对应冲回，或金额差异超过 {_format_percent(c.get('amount_tolerance', 0))}，就视为悬空计提。",
            "同时关注谁在集中做非常规计提，防止个别用户长期独占该类分录。",
        ]
    if rule_key == "yearend_surge":
        focus_months = _format_param_value("months", c.get("months", []))
        return [
            f"把 {focus_months} 的收入与其他月份均值做比较。",
            f"当目标月份收入高于基线 {_format_multiplier(c.get('multiplier', 0))} 以上时，整个月份相关收入凭证进入样本。",
        ]
    if rule_key == "financing_trade":
        return [
            f"以 {_format_list(c.get('income_account_prefixes', ['6001', '6051']))} 收入凭证为主凭证，收入达到 {_format_money(c.get('min_revenue_amount', 0))} 后进入配对池。",
            f"在 {c.get('window_days', '—')} 天内寻找 {_format_list(c.get('cost_account_prefixes', ['6401', '6402']))} 成本凭证，按日期、对手方、文本关键词、业务类别和金额关系计算匹配得分。",
            f"当匹配得分不低于 {_format_percent(c.get('min_match_score', 0))}、组合毛利率不高于 {_format_percent(c.get('low_margin_threshold', 0))}，且亏损率不超过 {_format_percent(c.get('max_loss_rate', 0))} 时，作为“疑点组合”进入复核。",
            f"每次最多保留 {c.get('max_candidate_groups', '—')} 组候选，每组最多关联 {c.get('max_related_vouchers', '—')} 张成本凭证；文本出现 {_format_list(c.get('keywords', []))} 但找不到成本时，也作为低证据候选提示。",
        ]
    if rule_key == "cross_year_accrual":
        return [
            f"跨年预提在 {c.get('match_window_days', '—')} 天内的冲回覆盖率若低于 {_format_percent(c.get('coverage_threshold', 0))}，就进入跨期风险样本。",
            "这类规则依赖跨年交叉稽核发现，重点看预提是否真正被后续期间消化。",
        ]
    if rule_key == "cross_year_revenue":
        return [
            f"12 月收入若高于前 11 个月平均水平 {_format_multiplier(c.get('dec_multiplier', 0))}，就作为跨年收入前置迹象保留。",
            "它和年末突击确认规则互相补位：一个看单年内部的异常高点，一个看跨年层面的收入漂移。",
        ]
    if rule_key == "cash_pool":
        return [
            f"文本中若出现 {_format_list(c.get('keywords', []))} 等资金归集/划转关键词，就先做同凭证穿透。",
            f"其中最大行金额达到 {_format_money(c.get('large_threshold', 0))} 的交易优先进入样本。",
        ]
    if rule_key == "user_concentration":
        return [
            f"当单一用户过账行数占比达到 {_format_percent(c.get('concentration_threshold', 0))} 及以上时，视为职责分离风险信号。",
            "这条规则不是直接判断舞弊，而是把“谁过于集中”显式拉出来供审计师复核。",
        ]
    if rule_key == "reversal_pattern":
        return [
            f"文本出现冲销/反记账关键词的凭证，会继续按大额和频繁两个方向筛查。",
            f"单笔冲销达到 {_format_money(c.get('large_threshold', 0))} 的，直接作为大额冲销关注。",
            f"同一用户若至少冲销 {c.get('frequent_count', '—')} 笔，也会被归为频繁冲销用户。",
        ]
    if rule_key == "sensitive_fees":
        category_cfg = c.get("categories", {})
        category_bits = []
        for name, cfg in category_cfg.items():
            category_bits.append(f"{name}≥{_format_money(cfg.get('threshold', 0))}")
        bits = "；".join(category_bits)
        return [
            f"对敏感费用按类别设门槛：{bits}。",
            f"若某个用户的敏感费用占比高于公司均值 {_format_multiplier(c.get('baseline_multiplier', 0))}，则该用户相关敏感费用凭证会被整组拉出。",
            "对于非异常用户，仅保留超过类别金额阈值的凭证，避免被零碎小额淹没。",
        ]
    return _generic_param_lines({k: v for k, v in c.items() if k not in {"enabled", "rationale"}})


def _rule_change_lines(rule_key: str, current_rule: dict[str, Any], base_rule: dict[str, Any]) -> list[str]:
    if not isinstance(current_rule, dict) or not isinstance(base_rule, dict):
        return []

    changes = []
    if current_rule.get("enabled", True) != base_rule.get("enabled", True):
        from_status = "启用" if base_rule.get("enabled", True) else "关闭"
        to_status = "启用" if current_rule.get("enabled", True) else "关闭"
        changes.append(f"启用状态：{from_status} -> {to_status}")

    for key, value in current_rule.items():
        if key in {"enabled", "rationale"}:
            continue
        base_value = base_rule.get(key)
        if value == base_value:
            continue
        label = PARAM_LABELS.get(key, key)
        if key == "categories":
            changes.append("敏感费用分类阈值已按本项目重新校准。")
        else:
            changes.append(
                f"{label}：{_format_param_value(key, base_value)} -> {_format_param_value(key, value)}"
            )
    return changes


def _collect_rule_changes(base_cfg: dict[str, Any], current_cfg: dict[str, Any]) -> list[tuple[str, list[str]]]:
    rows = []
    for rule_key in RULE_ORDER:
        current_rule = current_cfg.get(rule_key, {})
        base_rule = base_cfg.get(rule_key, {})
        changes = _rule_change_lines(rule_key, current_rule, base_rule)
        if changes:
            rows.append((RULE_META.get(rule_key, {}).get("title", rule_key), changes))
    return rows


def _rule_counts(cfg: dict[str, Any] | None) -> tuple[int, int]:
    if not cfg:
        return 0, 0
    enabled = 0
    disabled = 0
    for rule_key in RULE_ORDER:
        if cfg.get(rule_key, {}).get("enabled", True):
            enabled += 1
        else:
            disabled += 1
    return enabled, disabled


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







def _reset_editor_state(key: str) -> None:
    """清空明细选择控件状态，强制下次渲染时重新初始化。"""
    for widget_key in (f"{key}_hidden_sel", f"{key}_detail_editor", f"{key}_detail_table"):
        if widget_key in st.session_state:
            del st.session_state[widget_key]


def _style_selected_detail_rows(selected_vids: set[str]):
    def _style_row(row: pd.Series) -> list[str]:
        if str(row.get("__voucher_id_raw", "")) not in selected_vids:
            return [""] * len(row)
        return [
            "background-color: rgba(74, 222, 128, 0.18); color: #e2e8f0;"
            for _ in row
        ]

    return _style_row


def _resolve_focused_voucher(key: str, detail: pd.DataFrame) -> tuple[str | None, str]:
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


def _render_focused_voucher_detail(
    *,
    key: str,
    df_source: pd.DataFrame,
    amount_cols: list[str] | None = None,
) -> None:
    focused_vid, focused_date = _resolve_focused_voucher(key, df_source)
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
        use_container_width=True,
        hide_index=True,
        column_config=_amount_column_config(amount_cols),
    )



def _render_hover_table_html(
    detail: pd.DataFrame,
    df_source: pd.DataFrame,
    key: str,
    current_selected: set,
    amount_cols: list[str] | None = None,
) -> None:
    """渲染内联 HTML 明细表格——全部列 + 勾选框 + 可滚动 + 绿色行高亮 + 悬停浮出凭证完整分录。

    表格渲染在主页面 DOM 中（非 iframe），CSS 可对勾选行直接设绿色背景。
    勾选状态通过 JS 写入隐藏 st.text_input 回传 Streamlit。
    """
    if detail.empty:
        return

    # ── 为每个 unique 凭证构建悬停工具提示 (11+ 列) ──
    vids = detail["凭证编号"].astype(str).unique()
    tooltip_map: dict[str, str] = {}
    for vid in vids:
        vd = df_source[df_source["凭证编号"].astype(str) == vid]
        lines = []
        for _, r in vd.head(15).iterrows():
            dc = str(r.get("借/贷标识", ""))
            dc_label = "借" if dc == "S" else "贷" if dc == "H" else dc
            vt = str(r.get("凭证类型", ""))
            pd_date = str(r.get("过账日期", ""))[:10]
            acct = str(r.get("总账科目", ""))
            aname = str(
                r.get("_account_name", "")
                or r.get("总账科目：长文本", "")
                or r.get("总账科目：短文本", "")
            )
            htext = str(r.get("_header_text", r.get("凭证抬头摘要", "")))[:60]
            ltext = str(r.get("_line_text", r.get("文本", "")))[:60]
            amt = float(r.get("公司代码货币价值", r.get("凭证货币价值", 0)) or 0)
            currency = str(r.get("公司代码货币", ""))
            lines.append(
                f"凭证类型:{vt} | {dc_label} | 凭证:{vid} | 日期:{pd_date} | "
                f"科目:{acct} | {aname} | 抬头:{htext} | 摘要:{ltext} | "
                f"金额:{currency} {amt:,.0f}"
            )
        if len(vd) > 15:
            lines.append(f"... 共 {len(vd)} 行分录")
        tooltip_map[vid] = "\n".join(lines)

    # ── 全部列 ──
    display_cols = list(detail.columns)
    total_rows = len(detail)

    # ── 构建每列的格式化值 ──
    col_vals = []
    for col in display_cols:
        series = detail[col]
        if col == "过账日期":
            formatted = series.astype(str).str[:10]
        elif col in ("凭证货币价值", "公司代码货币价值"):
            formatted = series.fillna(0).astype(float).apply(lambda x: f"{x:,.0f}")
        elif col == "借/贷标识":
            formatted = series.replace({"S": "借", "H": "贷"}).fillna("")
        else:
            formatted = series.astype(str).str[:60]
        col_vals.append(formatted.values)

    cells_by_row = list(zip(*col_vals))
    vids_col = detail["凭证编号"].astype(str).values

    # ── 构建行 HTML ──
    rows_html_parts: list[str] = []
    for i in range(total_rows):
        vid = vids_col[i]
        is_sel = vid in current_selected
        checked_attr = " checked" if is_sel else ""
        cls = "ht-row selected" if is_sel else "ht-row"
        tip = _escape_html(tooltip_map.get(vid, ""))
        # 第一列：勾选框 + 凭证编号（合并在一列以节省空间）
        cb_cell = f'<td class="cb-cell"><input type="checkbox" class="row-cb" data-vid="{_escape_html(vid)}"{checked_attr}></td>'
        data_cells = "".join(
            f"<td>{_escape_html(str(c))}</td>" for c in cells_by_row[i]
        )
        rows_html_parts.append(
            f'<tr class="{cls}" data-tooltip="{tip}" data-vid="{_escape_html(vid)}">{cb_cell}{data_cells}</tr>'
        )

    headers = "<th>✓</th>" + "".join(f"<th>{_escape_html(c)}</th>" for c in display_cols)

    html = f"""
    <style>
    .ht-wrap-{key} {{
        max-height: 480px; overflow: auto; border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px; margin: 8px 0; background: rgba(255,255,255,0.008);
    }}
    .ht-wrap-{key} table {{
        width: max-content; min-width: 100%; border-collapse: collapse; font-size: 0.78rem;
    }}
    .ht-wrap-{key} thead {{
        position: sticky; top: 0; z-index: 10;
    }}
    .ht-wrap-{key} th {{
        background: rgba(15,23,42,0.95); color: #94a3b8; padding: 8px 10px;
        text-align: left; font-weight: 600; font-size: 0.7rem; text-transform: uppercase;
        letter-spacing: 0.3px; border-bottom: 1px solid rgba(255,255,255,0.10);
        white-space: nowrap; backdrop-filter: blur(4px);
    }}
    .ht-wrap-{key} th:first-child {{
        width: 32px; text-align: center;
    }}
    .ht-wrap-{key} .ht-row {{
        transition: background 0.1s ease; border-bottom: 1px solid rgba(255,255,255,0.03);
        position: relative;
    }}
    .ht-wrap-{key} .ht-row:nth-child(even) {{
        background: rgba(255,255,255,0.008);
    }}
    .ht-wrap-{key} .ht-row:hover {{
        background: rgba(79,142,247,0.1) !important; z-index: 5;
    }}
    .ht-wrap-{key} .ht-row.selected {{
        background: rgba(74,222,128,0.1) !important;
    }}
    .ht-wrap-{key} .ht-row.selected td {{
        color: #e2e8f0;
    }}
    .ht-wrap-{key} .ht-row td {{
        padding: 6px 10px; white-space: nowrap; color: #b0b8c1;
        max-width: 260px; overflow: hidden; text-overflow: ellipsis;
    }}
    .ht-wrap-{key} .ht-row td.cb-cell {{
        text-align: center; padding: 6px 4px;
    }}
    .ht-wrap-{key} .row-cb {{
        width: 15px; height: 15px; cursor: pointer; accent-color: #4ade80;
    }}
    .ht-wrap-{key} .ht-row:hover::after {{
        content: attr(data-tooltip);
        position: absolute; left: 10px; top: 100%; margin-top: 2px;
        background: #0f172a; color: #e2e8f0; padding: 10px 14px;
        border-radius: 8px; border: 1px solid rgba(79,142,247,0.35);
        font-size: 0.7rem; font-family: monospace; white-space: pre;
        line-height: 1.5; z-index: 9999;
        box-shadow: 0 10px 30px rgba(0,0,0,0.7);
        min-width: 460px; max-width: 760px; pointer-events: none;
        text-align: left; font-weight: 400;
    }}
    </style>
    <div class="ht-wrap-{key}">
    <table><thead><tr>{headers}</tr></thead><tbody>{"".join(rows_html_parts)}</tbody></table>
    </div>
    <div style="color:#64748b;font-size:0.7rem;margin-top:2px;">
        共 {total_rows} 行 · 鼠标悬停行查看完整分录 · 勾选后本行变绿
    </div>
    <script>
    (function() {{
        var checkboxes = document.querySelectorAll(".ht-wrap-{key} .row-cb");

        function getSelected() {{
            var vids = [];
            checkboxes.forEach(function(cb) {{
                if (cb.checked) vids.push(cb.getAttribute("data-vid"));
            }});
            return vids;
        }}

        function syncToStreamlit() {{
            var selected = getSelected();
            // 找隐藏的 st.text_input（aria-label 含 hidden_sel）
            var inputs = document.querySelectorAll('input[aria-label*="hidden_sel"]');
            for (var i = 0; i < inputs.length; i++) {{
                var inp = inputs[i];
                var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(inp, JSON.stringify(selected));
                inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }}

        checkboxes.forEach(function(cb) {{
            cb.addEventListener('change', function() {{
                var tr = cb.closest('tr');
                if (cb.checked) {{
                    tr.classList.add('selected');
                }} else {{
                    tr.classList.remove('selected');
                }}
                syncToStreamlit();
            }});
        }});
    }})();
    </script>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_hover_tooltip_html(
    detail: pd.DataFrame,
    df_source: pd.DataFrame,
    key: str,
    current_selected: set,
) -> None:
    """渲染紧凑的凭证号悬停伴侣——鼠标悬停任意凭证号即浮出完整分录。"""
    vids = detail["凭证编号"].astype(str).unique()
    if len(vids) == 0:
        return

    # ── 为每个 unique 凭证构建悬停工具提示 (11+ 列) ──
    tooltip_map: dict[str, str] = {}
    for vid in vids:
        vd = df_source[df_source["凭证编号"].astype(str) == vid]
        lines = []
        for _, r in vd.head(15).iterrows():
            dc = str(r.get("借/贷标识", ""))
            dc_label = "借" if dc == "S" else "贷" if dc == "H" else dc
            vt = str(r.get("凭证类型", ""))
            pd_date = str(r.get("过账日期", ""))[:10]
            acct = str(r.get("总账科目", ""))
            aname = str(
                r.get("_account_name", "")
                or r.get("总账科目：长文本", "")
                or r.get("总账科目：短文本", "")
            )
            htext = str(r.get("_header_text", r.get("凭证抬头摘要", "")))[:60]
            ltext = str(r.get("_line_text", r.get("文本", "")))[:60]
            amt = float(r.get("公司代码货币价值", r.get("凭证货币价值", 0)) or 0)
            currency = str(r.get("公司代码货币", ""))
            lines.append(
                f"凭证类型:{vt} | {dc_label} | 凭证:{vid} | 日期:{pd_date} | "
                f"科目:{acct} | {aname} | 抬头:{htext} | 摘要:{ltext} | "
                f"金额:{currency} {amt:,.0f}"
            )
        if len(vd) > 15:
            lines.append(f"... 共 {len(vd)} 行分录")
        tooltip_map[vid] = "\n".join(lines)

    items_html: list[str] = []
    for vid in vids:
        tip = _escape_html(tooltip_map.get(vid, ""))
        is_sel = vid in current_selected
        cls = "ht-vid selected" if is_sel else "ht-vid"
        items_html.append(
            f'<span class="{cls}" data-tooltip="{tip}">{_escape_html(vid)}</span>'
        )

    html = f"""
    <style>
    .ht-vid-wrap {{
        display: flex; flex-wrap: wrap; gap: 4px; max-height: 120px; overflow-y: auto;
        padding: 8px; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px;
        margin-top: 8px; background: rgba(255,255,255,0.01);
    }}
    .ht-vid {{
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.72rem; font-family: monospace; cursor: default;
        background: rgba(79,142,247,0.08); color: #94a3b8;
        transition: all 0.15s ease; position: relative;
    }}
    .ht-vid:hover {{
        background: rgba(79,142,247,0.25); color: #e2e8f0; z-index: 100;
    }}
    .ht-vid.selected {{
        background: rgba(74,222,128,0.15); color: #4ade80; font-weight: 600;
    }}
    .ht-vid:hover::after {{
        content: attr(data-tooltip);
        position: absolute; left: 0; bottom: 100%; margin-bottom: 4px;
        background: #0f172a; color: #e2e8f0; padding: 10px 14px;
        border-radius: 8px; border: 1px solid rgba(79,142,247,0.35);
        font-size: 0.7rem; font-family: monospace; white-space: pre;
        line-height: 1.5; z-index: 9999;
        box-shadow: 0 10px 30px rgba(0,0,0,0.7);
        min-width: 460px; max-width: 750px; pointer-events: none;
    }}
    </style>
    <div class="ht-vid-wrap">
        {"".join(items_html)}
    </div>
    <div style="color:#64748b;font-size:0.65rem;margin-top:2px;">
        {len(vids)} 个凭证号 · 鼠标悬停查看完整分录 · <span style="color:#4ade80;">绿色=已选中</span>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("\n", "&#10;")


def _render_detail_with_actions(
    title: str,
    detail: pd.DataFrame,
    *,
    df_source: pd.DataFrame,
    key: str,
    source_module: str,
    source_view: str,
    selector: dict[str, Any],
    amount_cols: list[str] | None = None,
    default_tags: list[str] | None = None,
    default_reason: str = "",
) -> None:
    """明细表格：左侧选择框批量流转，点击任意行查看当前凭证完整分录。"""
    if detail.empty:
        st.info("暂无匹配分录。")
        return

    stats = _detail_metrics(detail)
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
    amount_series = _detail_amount_series(detail)
    eligible_vids = set(detail["凭证编号"].astype(str).tolist()) if threshold == 0 else \
        set(detail.loc[amount_series >= threshold, "凭证编号"].astype(str).tolist())

    with filter_col2:
        if threshold > 0:
            if st.button(f"✓ 选择 {amount_sel}", type="primary", use_container_width=True, key=f"{key}_apply_filter"):
                st.session_state[sel_state_key] = list(eligible_vids)
                _reset_editor_state(key)
                st.rerun()
        else:
            if st.button("✓ 全选", use_container_width=True, key=f"{key}_select_all"):
                st.session_state[sel_state_key] = detail["凭证编号"].astype(str).unique().tolist()
                _reset_editor_state(key)
                st.rerun()
    with filter_col3:
        if st.button("✗ 清空", use_container_width=True, key=f"{key}_clear_sel"):
            st.session_state[sel_state_key] = []
            _reset_editor_state(key)
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

    table_config: dict[str, Any] = _amount_column_config(amount_cols)
    for amount_col in ("凭证货币价值", "公司代码货币价值"):
        if amount_col in display_detail.columns:
            table_config[amount_col] = st.column_config.NumberColumn(amount_col, format="%,.0f")

    styled_detail = display_detail.style.apply(
        _style_selected_detail_rows(base_selected),
        axis=1,
    )
    default_focus_vid, default_focus_date = _resolve_focused_voucher(key, detail)
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
        use_container_width=True,
        hide_index=True,
        height=min(520, 90 + max(len(display_detail), 1) * 35),
        column_order=visible_columns,
        column_config=table_config,
        on_select="rerun",
        selection_mode=["multi-row", "single-cell"],
        selection_default=default_selection,
    )
    selected_rows = _selected_dataframe_row_indices(detail_event)
    current_selected = set(
        display_detail.iloc[selected_rows]["__voucher_id_raw"].astype(str).tolist()
    ) & set(detail["凭证编号"].astype(str).tolist())

    focus_row_index = _selected_dataframe_focus_row_index(detail_event)
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
        f"金额合计 {_format_money(stats['amount'])}。"
        f"**已选 {len(current_selected)} 个** | 使用最左侧选择框可批量选中；点击任意行可查看当前凭证完整分录。"
    )
    col_add, col_final = st.columns(2)
    with col_add:
        with st.popover("📥 批量加入疑点库", use_container_width=True, disabled=not current_selected):
            tags_add = st.multiselect("风险标签", key=f"{key}_pop_add_tags",
                options=sorted(set(CANDIDATE_TAG_OPTIONS + (default_tags or []))),
                default=default_tags or [])
            reason_add = st.text_area("入库理由", key=f"{key}_pop_add_reason",
                value=default_reason, height=60)
            if st.button("确认加入", type="primary", use_container_width=True, key=f"{key}_pop_add_btn",
                          disabled=not current_selected):
                batch_detail = df_source[df_source["凭证编号"].astype(str).isin(current_selected)]
                _save_candidate_group(
                    title=f"{source_module}/{source_view}/批量{len(current_selected)}个",
                    source_module=source_module, source_view=source_view,
                    detail=batch_detail, tags=tags_add, reason=reason_add,
                    selector=selector, manual_final=False)
                st.session_state[sel_state_key] = []
                st.success(f"已批量加入 {len(current_selected)} 个凭证到疑点库。")
                st.rerun()
    with col_final:
        with st.popover("🚀 批量直入最终样本", use_container_width=True, disabled=not current_selected):
            tags_final = st.multiselect("风险标签", key=f"{key}_pop_final_tags",
                options=sorted(set(CANDIDATE_TAG_OPTIONS + (default_tags or []))),
                default=default_tags or [])
            reason_final = st.text_area("入库理由", key=f"{key}_pop_final_reason",
                value=default_reason, height=60)
            if st.button("确认直入", use_container_width=True, key=f"{key}_pop_final_btn",
                          disabled=not current_selected):
                batch_detail = df_source[df_source["凭证编号"].astype(str).isin(current_selected)]
                _save_candidate_group(
                    title=f"{source_module}/{source_view}/批量{len(current_selected)}个",
                    source_module=source_module, source_view=source_view,
                    detail=batch_detail, tags=tags_final, reason=reason_final,
                    selector=selector, manual_final=True)
                st.session_state[sel_state_key] = []
                st.success(f"已批量直入 {len(current_selected)} 个凭证到最终样本。")
                st.rerun()

    # ── 已选凭证清单 ──
    if current_selected:
        selected_list = sorted(current_selected)
        display_ids = selected_list[:20]
        more = f" …等共 {len(selected_list)} 个" if len(selected_list) > 20 else ""
        st.caption(f"✅ 已选凭证号：{', '.join(display_ids)}{more}")

    _render_focused_voucher_detail(
        key=key,
        df_source=df_source,
        amount_cols=amount_cols,
    )


def _unified_llm_key(years: list[int], category: str) -> str:
    years_part = ",".join(str(year) for year in sorted(years))
    return f"unified::{years_part}::{category}"


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


def _records_for_payload(df: pd.DataFrame, limit: int = 30) -> list[dict[str, Any]]:
    if df.empty:
        return []
    data = df.head(limit).copy()
    for col in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[col]):
            data[col] = data[col].dt.strftime("%Y-%m-%d")
    return data.to_dict("records")


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


def _detail_for_recommendation(condition: dict[str, Any], category: str) -> pd.DataFrame:
    condition = _normalise_recommendation_condition(condition)
    kind = str(condition.get("kind", ""))
    year = condition.get("year")
    if year is None:
        return pd.DataFrame()
    try:
        year = int(year)
    except (TypeError, ValueError):
        return pd.DataFrame()
    if year not in st.session_state.year_map:
        return pd.DataFrame()
    work = _build_audit_cache(st.session_state.year_map[year])["work"]
    month = condition.get("month")
    try:
        month = int(month) if month not in (None, "") else None
    except (TypeError, ValueError):
        month = None

    if kind == "revenue_customer_month":
        return build_revenue_focus_entries_from_work(
            work,
            customer=condition.get("customer") or None,
            material_group=condition.get("material_group") or None,
            month=month,
            category=category,
        )
    if kind == "monthly_income_cost":
        months = condition.get("months") or ([month] if month is not None else [])
        if not months:
            return pd.DataFrame()
        metric = str(condition.get("metric") or "revenue")
        frames = [
            build_monthly_revenue_cost_entry_top10_from_work(
                work,
                month=int(m),
                metric=metric,
                category=category,
            )
            for m in months
        ]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if kind == "income_cost_abnormal":
        months = condition.get("months") or ([month] if month is not None else [])
        if not months:
            return pd.DataFrame()
        direction = str(condition.get("direction") or "")
        frames = [
            build_income_cost_abnormal_entry_top10_from_work(
                work,
                month=int(m),
                direction=direction,
                category=category,
            )
            for m in months
        ]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if kind == "customer_revenue":
        customer = str(condition.get("customer") or "")
        detail = build_customer_revenue_entry_top10_from_work(work, customer=customer)
        if not detail.empty:
            return detail
        customer_norm = _normalise_label(customer)
        if not customer_norm:
            return pd.DataFrame()
        detail = work[
            work["_acct4"].isin(["6001", "6051"])
            & (work["_customer_display"].astype(str).map(_normalise_label) == customer_norm)
        ].copy()
        if detail.empty:
            return pd.DataFrame()
        detail["收入影响"] = detail["_amount_raw"]
        return detail.sort_values("_amount_abs", ascending=False).pipe(lambda d: d[[c for c in [
            "凭证编号", "过账日期", "行项目", "凭证类型", "总账科目", "_account_name", "借/贷标识",
            "公司代码货币价值", "凭证货币价值", "收入影响", "用户名", "_customer_display", "_vendor_display",
            "_material_group_display", "_material_display", "_cost_center_display", "_header_text", "_line_text",
            "_reversal_text"
        ] if c in d.columns]]).rename(columns={
            "_account_name": "科目名称", "_customer_display": "客户", "_vendor_display": "供应商",
            "_material_group_display": "物料组", "_material_display": "物料", "_cost_center_display": "成本中心",
            "_header_text": "凭证抬头摘要", "_line_text": "摘要", "_reversal_text": "反记账/冲销标识",
        })
    if kind == "revenue_customer_material":
        return build_revenue_focus_entries_from_work(
            work,
            customer=condition.get("customer") or None,
            material_group=condition.get("material_group") or None,
            month=month,
            category=category,
        )
    if kind == "cost_material_account":
        return build_cost_focus_entries_from_work(
            work,
            material_group=condition.get("material_group") or None,
            cost_account=condition.get("cost_account") or None,
            month=month,
            category=category,
        )
    if kind == "supplier_payable":
        supplier = str(condition.get("supplier") or "")
        detail = build_supplier_payable_entry_top10_from_work(work, supplier=supplier)
        if not detail.empty:
            return detail
        supplier_norm = _normalise_label(supplier)
        if not supplier_norm:
            return pd.DataFrame()
        detail = work[
            (work["_acct4"] == "2202")
            & (work["_vendor_display"].astype(str).map(_normalise_label) == supplier_norm)
        ].copy()
        if detail.empty:
            return pd.DataFrame()
        detail["应付发生额"] = detail["_amount_raw"].where(detail["_dc"] == "S", -detail["_amount_raw"])
        detail = detail.sort_values("_amount_abs", ascending=False)
        return detail[[
            c for c in [
                "凭证编号", "过账日期", "行项目", "凭证类型", "总账科目", "_account_name", "借/贷标识",
                "公司代码货币价值", "凭证货币价值", "应付发生额", "用户名", "_customer_display", "_vendor_display",
                "_material_group_display", "_material_display", "_cost_center_display", "_header_text", "_line_text",
                "_reversal_text"
            ] if c in detail.columns
        ]].rename(columns={
            "_account_name": "科目名称", "_customer_display": "客户", "_vendor_display": "供应商",
            "_material_group_display": "物料组", "_material_display": "物料", "_cost_center_display": "成本中心",
            "_header_text": "凭证抬头摘要", "_line_text": "摘要", "_reversal_text": "反记账/冲销标识",
        })
    if kind == "expense_category":
        expense_category = str(condition.get("expense_category") or "")
        if not expense_category:
            return pd.DataFrame()
        return build_expense_entry_top10_from_work(work, expense_category)
    if kind == "ap_accrual_month":
        if month is None:
            return pd.DataFrame()
        direction = str(condition.get("direction") or "net")
        return build_ap_accrual_entry_top10_from_work(work, month=month, direction=direction)
    if kind == "ap_accrual_supplier":
        if month is None:
            return pd.DataFrame()
        return build_ap_accrual_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
            supplier=str(condition.get("supplier") or ""),
        )
    if kind == "other_receivable_month":
        if month is None:
            return pd.DataFrame()
        return build_other_receivable_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
        )
    if kind == "other_payable_month":
        if month is None:
            return pd.DataFrame()
        return build_other_payable_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
        )
    if kind == "adjustment_voucher":
        voucher_id = str(condition.get("voucher_id") or "")
        if not voucher_id:
            return pd.DataFrame()
        return work.loc[work["凭证编号"].astype(str) == voucher_id].copy()

    if kind == "cross_year_finding":
        years_list = condition.get("years") or [year]
        cat = str(condition.get("category") or "")
        cat_lower = cat.lower()
        # 匹配跨年稽核发现中的关键词
        keyword_map = {
            "预提": ["预提", "计提", "accrual"],
            "收入": ["收入", "revenue"],
            "突增": ["突增", "surge", "spike"],
            "年末": ["年末", "year.end", "december"],
            "冲回": ["冲回", "冲销", "reversal"],
        }
        keywords = []
        for kw_group, kws in keyword_map.items():
            if any(k in cat_lower for k in kws):
                keywords.extend(kws)
        if not keywords:
            keywords = [cat]
        frames = []
        for y in years_list:
            try:
                y = int(y)
            except (TypeError, ValueError):
                continue
            if y in st.session_state.year_map:
                y_work = _build_audit_cache(st.session_state.year_map[y])["work"]
                mask = pd.Series(False, index=y_work.index)
                for kw in keywords:
                    if "文本" in y_work.columns:
                        mask |= y_work["文本"].astype(str).str.contains(kw, case=False, na=False)
                if mask.any():
                    frames.append(y_work[mask].copy())
        if frames:
            return pd.concat(frames, ignore_index=True)
        # fallback: 返回对应年份的数据
        for y in years_list:
            try:
                y = int(y)
            except (TypeError, ValueError):
                continue
            if y in st.session_state.year_map:
                return _build_audit_cache(st.session_state.year_map[y])["work"].head(50).copy()
        return pd.DataFrame()

    if kind == "profile_signal":
        signal = str(condition.get("signal") or condition.get("category") or "")
        signal_lower = signal.lower()
        # 匹配统计画像信号关键词
        if any(k in signal_lower for k in ["假日", "周末", "weekend", "holiday"]):
            mask = (work["_dow"] >= 5) if "_dow" in work.columns else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["月末", "month.end", "period.end", "年底", "年末"]):
            mask = (work["_is_month_end"]) if "_is_month_end" in work.columns else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["用户", "user", "concentration", "集中"]):
            top_users = work["用户名"].value_counts().head(5).index.tolist() if "用户名" in work.columns else []
            mask = work["用户名"].isin(top_users) if top_users else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["大额", "large", "整数", "round"]):
            amt_threshold = 1e6
            if "_amount_abs" in work.columns:
                mask = work["_amount_abs"] >= amt_threshold
            else:
                mask = pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["冲销", "reversal", "反记账", "调账"]):
            mask = work["_reversal_text"].astype(str).str.strip() != "" if "_reversal_text" in work.columns else pd.Series(False, index=work.index)
        else:
            # 默认返回当前年份金额最大的凭证
            if "_amount_abs" in work.columns:
                return work.nlargest(min(50, len(work)), "_amount_abs").copy()
            return work.head(50).copy()
        if mask.any():
            return work[mask].head(100).copy()
        return work.head(50).copy()

    return pd.DataFrame()


def _normalise_label(value: str) -> str:
    return str(value or "").strip().replace(" ", "").replace("\n", "").replace("\t", "")


def _normalise_recommendation_condition(condition: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(condition or {})
    metric_map = {
        "净收入": "revenue",
        "收入": "revenue",
        "revenue": "revenue",
        "净成本": "cost",
        "成本": "cost",
        "cost": "cost",
        "毛利": "gross",
        "gross": "gross",
    }
    direction_map = {
        "收入S": "income_s",
        "收入S异常": "income_s",
        "income_s": "income_s",
        "成本H": "cost_h",
        "成本H异常": "cost_h",
        "cost_h": "cost_h",
        "借方": "debit",
        "贷方": "credit",
        "净额": "net",
        "冲销": "writeoff",
        "预提": "accrual",
    }
    metric = normalized.get("metric")
    if metric is not None:
        normalized["metric"] = metric_map.get(str(metric).strip(), str(metric).strip())
    direction = normalized.get("direction")
    if direction is not None:
        normalized["direction"] = direction_map.get(str(direction).strip(), str(direction).strip())
    month = normalized.get("month")
    months = normalized.get("months")
    if isinstance(months, list):
        cleaned_months = []
        for item in months:
            try:
                cleaned_months.append(int(str(item).replace("月", "").strip()))
            except (TypeError, ValueError):
                continue
        normalized["months"] = cleaned_months
    elif month is not None:
        try:
            normalized["month"] = int(str(month).replace("月", "").strip())
            normalized["months"] = [normalized["month"]]
        except (TypeError, ValueError):
            pass
    for key in ["customer", "supplier", "expense_category", "voucher_id"]:
        if normalized.get(key) is not None:
            normalized[key] = str(normalized.get(key)).strip()
    return normalized


def _backfill_recommendation_condition(
    rec: dict[str, Any],
    category: str,
    module_filter: str,
) -> dict[str, Any]:
    condition = _normalise_recommendation_condition(rec.get("condition") or {})
    title = str(rec.get("title") or "")
    reason = str(rec.get("reason") or "")
    text = f"{title}\n{reason}"

    if module_filter == "收入成本":
        if not condition.get("kind"):
            customer_match = re.search(r"客户([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+?)收入", text)
            if customer_match:
                condition["kind"] = "customer_revenue"
                condition["customer"] = customer_match.group(1).strip()
        if not condition.get("year"):
            year_match = re.search(r"(20\\d{2})年", text)
            if year_match:
                condition["year"] = int(year_match.group(1))
        if not condition.get("kind") and "毛利" in text:
            months = [int(m) for m in re.findall(r"(\\d{1,2})月", text)]
            if months:
                condition["kind"] = "monthly_income_cost"
                condition["metric"] = "gross"
                condition["month"] = months[0]
                condition["months"] = months
        if not condition.get("kind") and "供应商" in text:
            supplier_match = re.search(r"供应商([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+?)(应付|暂估|收入|成本)", text)
            if supplier_match:
                condition["kind"] = "supplier_payable"
                condition["supplier"] = supplier_match.group(1).strip()
    elif module_filter == "费用":
        if not condition.get("kind"):
            expense_match = re.search(r"费用类别\\s*([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+)", text)
            if expense_match:
                condition["kind"] = "expense_category"
                condition["expense_category"] = expense_match.group(1).strip()

    elif module_filter == "跨年交叉稽核":
        if not condition.get("kind"):
            condition["kind"] = "cross_year_finding"
        if not condition.get("category"):
            condition["category"] = title
        if not condition.get("years"):
            years_found = sorted(set(int(y) for y in re.findall(r"(20\d{2})", text)))
            condition["years"] = years_found if years_found else list(st.session_state.year_map.keys())
    elif module_filter == "统计画像":
        if not condition.get("kind"):
            condition["kind"] = "profile_signal"
        if not condition.get("signal"):
            condition["signal"] = title
        if not condition.get("year") and st.session_state.year_map:
            condition["year"] = max(st.session_state.year_map.keys())
    return _normalise_recommendation_condition(condition)


def _render_candidate_recommendations(category: str) -> None:
    _render_candidate_recommendations_for_module(category, module_filter="收入成本", show_controls=True)


def _render_unified_generation_controls(category: str) -> None:
    _render_candidate_recommendations_for_module(category, module_filter="收入成本", show_controls=True, cards_only=False)


def _recommendation_matches_module(rec: dict[str, Any], module_filter: str) -> bool:
    source_module = str(rec.get("source_module", "") or "")
    source_view = str(rec.get("source_view", "") or "")
    condition = rec.get("condition") or {}
    kind = str(condition.get("kind", "") or "")

    if module_filter == "收入成本":
        return (
            "收入成本" in source_module
            or source_view in {"月度收入成本", "异常方向", "客户收入", "供应商应付"}
            or kind in {"monthly_income_cost", "income_cost_abnormal", "customer_revenue", "supplier_payable"}
        )
    if module_filter == "费用":
        return "费用" in source_module or source_view == "费用类别" or kind == "expense_category"
    if module_filter == "暂估往来":
        return (
            "暂估往来" in source_module
            or source_view in {"暂估月度", "暂估供应商", "其他应收", "其他应付"}
            or kind in {"ap_accrual_month", "ap_accrual_supplier", "other_receivable_month", "other_payable_month"}
        )
    if module_filter == "调账冲销":
        return "调账冲销" in source_module or source_view == "调账凭证" or kind == "adjustment_voucher"
    return True


def _recommendation_target_text(rec: dict[str, Any]) -> str:
    condition = rec.get("condition") or {}
    kind = str(condition.get("kind", "") or "")
    year = condition.get("year")
    month = condition.get("month")
    if kind == "monthly_income_cost":
        metric_map = {"revenue": "净收入", "cost": "净成本", "gross": "毛利"}
        metric = metric_map.get(str(condition.get("metric") or "revenue"), "月度指标")
        return f"{year}年{month}月 {metric}"
    if kind == "income_cost_abnormal":
        direction = "收入S异常" if str(condition.get("direction")) == "income_s" else "成本H异常"
        return f"{year}年{month}月 {direction}"
    if kind == "customer_revenue":
        return f"{year}年 客户 {condition.get('customer', '')} 收入"
    if kind == "supplier_payable":
        return f"{year}年 供应商 {condition.get('supplier', '')} 应付"
    if kind == "expense_category":
        return f"{year}年 费用类别 {condition.get('expense_category', '')}"
    if kind == "ap_accrual_month":
        return f"{year}年{month}月 暂估往来"
    if kind == "ap_accrual_supplier":
        return f"{year}年{month}月 供应商 {condition.get('supplier', '')} 暂估"
    if kind == "other_receivable_month":
        return f"{year}年{month}月 其他应收"
    if kind == "other_payable_month":
        return f"{year}年{month}月 其他应付"
    if kind == "adjustment_voucher":
        return f"{year}年 调账凭证 {condition.get('voucher_id', '')}"
    return str(rec.get("title") or "未命名建议")


def _recommendation_condition_text(condition: dict[str, Any], module_filter: str) -> str:
    condition = _normalise_recommendation_condition(condition)
    kind = str(condition.get("kind", "") or "")
    year = condition.get("year")
    month = condition.get("month")
    months = condition.get("months") or ([] if month is None else [month])

    def _months_text(values: list[Any]) -> str:
        cleaned = []
        for item in values:
            try:
                cleaned.append(f"{int(item)}月")
            except (TypeError, ValueError):
                continue
        return "、".join(cleaned) if cleaned else "未指定月份"

    if module_filter == "收入成本":
        if kind == "monthly_income_cost":
            metric_label = {
                "revenue": "净收入",
                "cost": "净成本",
                "gross": "毛利",
            }.get(str(condition.get("metric") or ""), "月度指标")
            return f"按 {year} 年 {_months_text(months)} 的 {metric_label} 相关分录回查。"
        if kind == "income_cost_abnormal":
            direction_label = {
                "income_s": "收入借方异常",
                "cost_h": "成本贷方异常",
            }.get(str(condition.get("direction") or ""), "异常方向")
            return f"按 {year} 年 {_months_text(months)} 的 {direction_label} 分录回查。"
        if kind == "customer_revenue":
            return f"按 {year} 年客户“{condition.get('customer', '')}”的收入分录回查。"
        if kind == "supplier_payable":
            return f"按 {year} 年供应商“{condition.get('supplier', '')}”的应付分录回查。"
    if module_filter == "费用":
        if kind == "expense_category":
            return f"按 {year} 年费用类别“{condition.get('expense_category', '')}”的分录回查。"
    if module_filter == "暂估往来":
        if kind == "ap_accrual_month":
            direction_label = {
                "credit": "暂估贷方增加",
                "debit": "暂估借方减少",
                "net": "暂估净额",
            }.get(str(condition.get("direction") or ""), "暂估分录")
            return f"按 {year} 年 {month} 月的{direction_label}分录回查。"
        if kind == "ap_accrual_supplier":
            direction_label = {
                "credit": "暂估贷方增加",
                "debit": "暂估借方减少",
                "net": "暂估净额",
            }.get(str(condition.get("direction") or ""), "暂估分录")
            return f"按 {year} 年 {month} 月供应商“{condition.get('supplier', '')}”的{direction_label}分录回查。"
        if kind == "other_receivable_month":
            direction_label = {
                "debit": "其他应收借方发生额",
                "credit": "其他应收贷方发生额",
                "net": "其他应收净额",
            }.get(str(condition.get("direction") or ""), "其他应收分录")
            return f"按 {year} 年 {month} 月的{direction_label}回查。"
        if kind == "other_payable_month":
            direction_label = {
                "accrual": "其他应付预提",
                "writeoff": "其他应付核销",
                "net": "其他应付净值",
            }.get(str(condition.get("direction") or ""), "其他应付分录")
            return f"按 {year} 年 {month} 月的{direction_label}回查。"
    if module_filter == "调账冲销":
        if kind == "adjustment_voucher":
            return f"按 {year} 年凭证号“{condition.get('voucher_id', '')}”的整张凭证分录回查。"
    if module_filter == "跨年交叉稽核":
        if kind == "cross_year_finding":
            years = condition.get("years") or []
            year_text = "、".join(str(y) for y in years) if years else "相关年度"
            return f"按跨年异常“{condition.get('category', '')}”涉及的 {year_text} 年凭证回查。"
    if module_filter == "统计画像":
        if kind == "profile_signal":
            return "按统计画像识别出的异常特征对应分录回查。"
    return "按模型给出的筛选条件回查对应分录。"


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
            st.rerun()

    if show_controls:
        generate_col, auto_add_col = st.columns(2)
        btn_label = "智能分析" if not unified_cached else "刷新智能分析"
        with generate_col:
            if st.button(btn_label, disabled=not _can_use_llm(), type="primary", use_container_width=True):
                try:
                    _generate_recommendations(auto_add_all=False)
                except Exception as e:
                    st.error(f"生成模型建议失败：{e}")
        with auto_add_col:
            add_disabled = not unified_cached or not _can_use_llm()
            if st.button("一键加入疑点库", disabled=add_disabled, use_container_width=True, key=f"gen_add_all_llm_{unified_key}"):
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
                            st.rerun()
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
        if st.button("一键全部加入疑点库", use_container_width=True, key=f"add_all_llm_rec_{unified_key}_{module_filter}"):
            added, skipped = _add_recommendations([(idx, rec, False) for idx, rec in enumerate(filtered_recommendations)])
            if added:
                st.success(f"已加入 {added} 条模型建议。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                st.rerun()
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
                        use_container_width=True,
                        key=f"llm_rec_add_{unified_key}_{module_filter}_{idx}",
                        type="primary",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, False)])
                        if added:
                            st.success("已加入疑点库。")
                            st.rerun()
                        else:
                            st.warning("当前建议没有匹配到可加入疑点库的明细分录。")
                with action_col2:
                    if st.button(
                        "直入最终样本",
                        use_container_width=True,
                        key=f"llm_rec_final_add_{unified_key}_{module_filter}_{idx}",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, True)])
                        if added:
                            st.success("已直入最终样本。")
                            st.rerun()
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
active_tab_name = st.segmented_control(
    "页签导航", TAB_NAMES,
    default=TAB_NAMES[st.session_state.get("active_tab", 0)],
    selection_mode="single", label_visibility="collapsed"
)
st.session_state.active_tab = TAB_NAMES.index(active_tab_name) if active_tab_name in TAB_NAMES else 0

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
    if not (_has_project_payload() and _has_loaded_years()):
        st.info("请先在「上传数据」页签中上传序时账文件。")
    else:
        st.title("📊 数据分析")

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
            net_cost = -(total_cost_s + total_cost_h)
            gross_profit = net_revenue + net_cost
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
    if not (_has_project_payload() and _has_loaded_years()):
        st.info("请先在「上传数据」页签中上传序时账文件。")
    else:
        st.title("🎯 样本抽取")
        st.caption("从可疑样本库中选择规则和抽样方式，一键生成最终审计样本。")

        pool = st.session_state.get("candidate_pool", [])
        df = st.session_state.df_unified
        candidate_voucher_ids = _candidate_pool_voucher_ids()
        pool_stat = cp.get_pool_statistics(pool)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            rule_source = st.selectbox(
                "规则来源",
                options=["default_rules", "calibrated_rules", "no_rule"],
                format_func=lambda x: {
                    "default_rules": "🏛 系统默认规则",
                    "calibrated_rules": "🤖 LLM 校准后规则",
                    "no_rule": "❌ 不使用规则（仅随机/全量）",
                }.get(x, x),
                help="选择用于筛选样本的规则集。",
            )
        with col_b:
            sample_method = st.selectbox(
                "抽样方式",
                options=["by_rule", "by_account_weight", "monetary_unit", "stratified", "random", "all"],
                format_func=lambda x: {
                    "by_rule": "🔍 按规则筛选",
                    "by_account_weight": "📊 科目权重抽样",
                    "monetary_unit": "💰 货币单元抽样 (MUS)",
                    "stratified": "📑 分层抽样",
                    "random": "🎲 随机抽样",
                    "all": "📦 全量（不抽样）",
                }.get(x, x),
                help="从候选凭证中选择最终样本的方式。",
            )
        with col_c:
            max_sample_size = st.number_input(
                "样本量上限（凭证数）",
                min_value=1,
                max_value=500,
                value=min((st.session_state.rules_config or {}).get("max_sample_size", 50), 200),
                key="sample_max_size",
                help="最终输出的最大凭证数量。",
            )

        if rule_source == "calibrated_rules":
            if st.session_state.rules_config:
                enabled_count, _ = _rule_counts(st.session_state.rules_config)
                st.caption(f"已加载校准规则 {enabled_count} 条（可在「规则管理」页签中调整）。")
            else:
                st.warning("尚未生成校准规则，将回退到系统默认规则。")
        elif rule_source == "default_rules":
            st.caption("使用系统内置默认规则集。")

        if sample_method == "random":
            st.info("随机抽样：对候选池中所有凭证按指定样本量随机抽取，不依赖规则引擎。")
        elif sample_method == "by_rule":
            st.info("按规则筛选：使用选定规则集对候选池（或全量数据）执行规则引擎，命中凭证作为样本。")
        elif sample_method == "all":
            st.info("全量抽取：将候选池中所有凭证直接作为最终样本，不做筛选。")
        elif sample_method == "by_account_weight":
            st.info("科目权重抽样：按科目大类分配样本名额，每类内取金额最大的凭证。可调整下方权重。")
            # 权重滑块
            weights = st.session_state.get("_sample_weights", dict(cp.DEFAULT_ACCOUNT_WEIGHTS))
            st.caption("调整各科目大类的抽样权重（将自动归一化）：")
            weight_cols = st.columns(len(weights))
            new_weights = {}
            for (cat, default_w), col in zip(weights.items(), weight_cols):
                with col:
                    new_weights[cat] = st.slider(
                        cat, 0.0, 1.0, default_w, 0.05,
                        key=f"weight_{cat}",
                    )
            st.session_state["_sample_weights"] = new_weights
        elif sample_method == "monetary_unit":
            st.info("货币单元抽样 (MUS)：以金额为抽样单元，金额越大的凭证被抽中概率越高。经典审计抽样方法。")
        elif sample_method == "stratified":
            st.info("分层抽样：按指定属性将候选凭证分层，每层按比例或等量抽取。")
            strat_col1, strat_col2 = st.columns(2)
            with strat_col1:
                stratify_by = st.selectbox(
                    "分层属性",
                    options=["凭证类型", "科目大类", "月份", "用户名"],
                    key="stratify_by",
                )
            with strat_col2:
                stratify_mode = st.selectbox(
                    "分配方式",
                    options=["proportional", "equal"],
                    format_func=lambda x: "按层规模比例" if x == "proportional" else "每层等量",
                    key="stratify_mode",
                )
            st.session_state["_stratify_by"] = stratify_by
            st.session_state["_stratify_mode"] = stratify_mode

        scope_desc = f"当前候选池有效凭证：{len(candidate_voucher_ids):,} 个" if candidate_voucher_ids else "候选池为空，将对全量数据执行规则引擎。"
        st.caption(f"📊 {scope_desc} | 候选群体：{pool_stat['total_groups']} 个 | 总金额：{_format_money(pool_stat['total_amount'])}")

        use_candidate_scope = False
        if sample_method == "by_rule":
            use_candidate_scope = st.checkbox(
                "仅在疑点库范围内执行规则",
                value=bool(candidate_voucher_ids),
                disabled=not bool(candidate_voucher_ids),
                key="sample_use_scope",
            )
            if candidate_voucher_ids:
                st.caption(f"启用后仅在 {len(candidate_voucher_ids):,} 个候选凭证上运行规则，否则回退全量。")

        run_llm = st.checkbox(
            "启用智能辅助核实 (LLM Verification)",
            value=_can_use_llm(),
            disabled=not _can_use_llm(),
            key="sample_run_llm",
        )

        st.divider()

        if st.button("🚀 执行样本抽取", type="primary", use_container_width=True):
            if rule_source == "calibrated_rules" and st.session_state.rules_config:
                cfg = st.session_state.rules_config
            else:
                cfg = default_rules_config()

            with st.spinner("正在执行样本抽取..."):
                if sample_method == "by_rule":
                    scope_ids = candidate_voucher_ids if use_candidate_scope else None
                    rule_results = run_all_rules(
                        df, cfg,
                        cross_year_findings=st.session_state.cross_year_findings,
                        candidate_voucher_ids=scope_ids,
                    )
                    st.session_state.rule_results = rule_results

                    if run_llm:
                        progress_bar = st.progress(0)
                        progress_text = st.empty()

                        def on_progress(batch_num, total_batches):
                            pct = int(batch_num / total_batches * 100)
                            progress_bar.progress(pct)
                            progress_text.text(f"智能核实进度：{batch_num}/{total_batches} 批次 ({pct}%)")

                        judgments = verify_with_llm(
                            df=df,
                            rule_results=rule_results,
                            api_key=st.session_state["_api_key"],
                            model=_llm_model(),
                            base_url=_llm_base_url(),
                            batch_size=10,
                            max_verify=50,
                            progress_callback=on_progress,
                        )
                        progress_bar.progress(100)
                        progress_text.text("✅ 智能核实已完成")
                        st.session_state.llm_judgments = judgments
                    else:
                        st.session_state.llm_judgments = {}

                    samples = cp.sample_from_pool(
                        pool, df,
                        method="by_rule",
                        size=max_sample_size,
                        rules_config=cfg,
                    )
                    st.session_state.final_samples = samples
                elif sample_method == "by_account_weight":
                    samples = cp.sample_from_pool(
                        pool, df,
                        method="by_account_weight",
                        size=max_sample_size,
                        account_weights=st.session_state.get("_sample_weights"),
                    )
                    st.session_state.final_samples = samples
                elif sample_method == "monetary_unit":
                    samples = cp.sample_from_pool(
                        pool, df,
                        method="monetary_unit",
                        size=max_sample_size,
                    )
                    st.session_state.final_samples = samples
                elif sample_method == "stratified":
                    samples = cp.sample_from_pool(
                        pool, df,
                        method="stratified",
                        size=max_sample_size,
                        stratify_by=st.session_state.get("_stratify_by"),
                        stratify_mode=st.session_state.get("_stratify_mode", "proportional"),
                    )
                    st.session_state.final_samples = samples
                elif sample_method == "random":
                    samples = cp.sample_from_pool(
                        pool, df,
                        method="random",
                        size=max_sample_size,
                    )
                    st.session_state.final_samples = samples
                elif sample_method == "all":
                    samples = cp.sample_from_pool(
                        pool, df,
                        method="all",
                    )
                    st.session_state.final_samples = samples

                st.session_state.report_stats = {}
                st.session_state.report_path = None
                _autosave_current_project_state()
                st.rerun()

        # 展示抽样结果
        if st.session_state.get("final_samples"):
            samples = st.session_state.final_samples
            st.divider()
            st.subheader(f"📊 抽样结果（{len(samples)} 条凭证）")

            source_counts = {}
            for s in samples:
                src = s.get("来源模块", "未知")
                source_counts[src] = source_counts.get(src, 0) + 1

            stats_cols = st.columns(3)
            stats_cols[0].metric("样本凭证总数", len(samples))
            stats_cols[1].metric("人工直入数量", sum(1 for s in samples if s.get("是否为人工直入")))
            if source_counts:
                stats_cols[2].metric("来源模块数", len(source_counts))

            result_df = cp.sample_to_table(samples)
            if not result_df.empty:
                display_df = result_df.copy()
                display_df["借方金额"] = display_df["借方金额"] / 1e4
                display_df["贷方金额"] = display_df["贷方金额"] / 1e4
                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "凭证编号": st.column_config.TextColumn("凭证编号"),
                        "过账日期": st.column_config.TextColumn("过账日期"),
                        "总账科目": st.column_config.TextColumn("总账科目"),
                        "科目名称": st.column_config.TextColumn("科目名称"),
                        "借方金额(万)": st.column_config.NumberColumn("借方金额(万)", format="%,.1f"),
                        "贷方金额(万)": st.column_config.NumberColumn("贷方金额(万)", format="%,.1f"),
                        "来源模块": st.column_config.TextColumn("来源模块"),
                        "是否为人工直入": st.column_config.CheckboxColumn("是否为人工直入"),
                    },
                )

            if st.session_state.rule_results:
                results = st.session_state.rule_results
                summary_data = hits_summary(results)
                c1, c2 = st.columns([1, 1.5])
                with c1:
                    st.markdown("##### 规则命中摘要")
                    st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)
                    total_hits = sum(r.count for r in results)
                    total_vouchers = len({h.voucher_id for r in results for h in r.hits})
                    st.info(f"💡 规则共命中 **{total_hits}** 行分录，涉及 **{total_vouchers}** 个凭证。")
                with c2:
                    st.plotly_chart(rule_hit_bar(summary_data), use_container_width=True)

                if st.session_state.llm_judgments:
                    st.plotly_chart(risk_level_pie(st.session_state.llm_judgments), use_container_width=True)

        st.divider()
        st.subheader("📄 报告下载")

        cfg = st.session_state.rules_config or {}
        max_sample = cfg.get("max_sample_size", 50)

        if not st.session_state.report_stats:
            with st.spinner("正在汇总数据并生成 Excel 报告..."):
                engagement = st.session_state.engagement_name or "unnamed"
                ts = datetime.now().strftime("%Y%m%d_%H%M")
                out_path = Path(__file__).parent / f"样本清单_{engagement}_{ts}.xlsx"

                rule_results = st.session_state.rule_results
                # 如果规则结果为空但有最终样本，用样本凭证号构建最小 RuleHit 集合
                if (not rule_results) and st.session_state.get("final_samples"):
                    from modules.rule_engine import RuleHit, RuleResult
                    sample_vids = {str(s["凭证编号"]) for s in st.session_state.final_samples if s.get("凭证编号")}
                    if sample_vids:
                        hits = [
                            RuleHit(voucher_id=vid, rule_type="人工/随机抽样", evidence="来自最终样本",
                                    line_indices=(), priority=1)
                            for vid in sorted(sample_vids)
                        ]
                        rule_results = [RuleResult(rule_name="抽样结果", hits=hits)]

                stats = generate_report(
                    df=st.session_state.df_unified,
                    rule_results=rule_results,
                    llm_judgments=st.session_state.llm_judgments,
                    output_path=str(out_path),
                    max_sample_size=max_sample,
                    manual_final_samples=cp.manual_final_groups(st.session_state.get("candidate_pool", [])),
                )
                st.session_state.report_path = str(out_path)
                st.session_state.report_stats = stats
                _autosave_current_project_state()

        stats = st.session_state.report_stats

        with st.container(border=True):
            st.markdown("##### 报告统计摘要")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("最终样本凭证", stats.get("sample_vouchers", 0))
            col2.metric("规则命中凭证", stats.get("total_unique_vouchers", stats.get("total_rule_hits", 0)))
            col3.metric("高风险凭证", stats.get("high_risk", 0))
            col4.metric("人工直入凭证", stats.get("manual_final_vouchers", 0))

        # 下载报告
        report_path = st.session_state.report_path
        if report_path and Path(report_path).exists():
            with open(report_path, "rb") as f:
                st.download_button(
                    "📥 下载样本清单 (Excel)",
                    data=f.read(),
                    file_name=Path(report_path).name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                    use_container_width=True
                )

        st.divider()

        # 重置，开始新项目
        if st.button("🔄 开始新审计项目", use_container_width=True):
            _reset_current_project()
            st.rerun()
