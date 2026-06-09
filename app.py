"""
序时账审计分析平台 — Streamlit 主入口

运行：uv run streamlit run app.py
"""

from __future__ import annotations

import functools
import logging
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
from components.styles import inject_global_css

inject_global_css()

# ── 模块导入 ──
from modules.data_columns import add_analysis_columns
from modules.visual_analysis import (
    build_ap_accrual_monthly_view_from_work,
    build_adjustment_views_from_work,
    build_customer_top10_from_work,
    build_monthly_revenue_cost_view_from_work,
    build_other_receivable_monthly_view_from_work,
    build_other_payable_monthly_view_from_work,
    build_supplier_top10_from_work,
)
from modules import knowledge_base as kb
from modules import candidate_pool as cp
from modules import llm_config
from modules.formatting import (
    format_money as _format_money,
    format_years as _format_years,
)
from components.chart_selection import (
    selected_ap_accrual_point as _selected_ap_accrual_point,
    selected_bar_label as _selected_bar_label,
    selected_bar_label_and_direction as _selected_bar_label_and_direction,
    selected_dataframe_row_index as _selected_dataframe_row_index,
    selected_expense_cross_year_point as _selected_expense_cross_year_point,
    selected_income_cost_abnormal_point as _selected_income_cost_abnormal_point,
    selected_monthly_metric_point as _selected_monthly_metric_point,
    toggle_chart_selection as _toggle_chart_selection,
)
from modules.rule_text import (
    collect_rule_changes as _collect_rule_changes,
    rule_counts as _rule_counts,
)
from components.llm_orchestration import (
    RecommendationDeps,
    render_candidate_recommendations_for_module as _lo_render_candidate_recommendations_for_module,
    render_unified_generation_controls as _lo_render_unified_generation_controls,
    unified_llm_key as _unified_llm_key,
)
from components.candidate_actions import (
    render_candidate_add_popover as _ca_render_candidate_add_popover,
    render_detail_with_actions as _ca_render_detail_with_actions,
)
from components.exports import (
    render_chart_title_with_download as _render_chart_title_with_download,
)
from components.cross_year_view import (
    cross_year_expense_table as _cross_year_expense_table,
    expense_summary_table as _expense_summary_table,
    render_cross_year_finding as _render_cross_year_finding,
    render_library_rules as _render_library_rules,
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

# ── 全局常量（来自 config/）──
from config.constants import (
    DEFAULT_LLM_CONFIG, AUDIT_CACHE_VERSION, PROJECT_MEMORY_KEYS,
)

logger = logging.getLogger(__name__)



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
        # 但必须留痕，避免用户数据丢失而无任何线索。
        logger.warning("autosave (save_project_state) failed", exc_info=True)


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


def _require_loaded_data() -> bool:
    """Check if data is loaded. Returns True if OK, False if not."""
    if _has_project_payload() and _has_loaded_years():
        return True
    st.info("请先在「上传数据」页签中上传序时账文件。")
    return False


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


# 推荐编排器（payload 构造 + LLM 并发生成 + 卡片渲染）已抽到 components/llm_orchestration.py。
# 把 app 私有 helper（含两个仍留在 app.py 的 @st.cache_data 视图缓存）打包成 RecommendationDeps，
# 用 functools.partial 预绑定，保持注入 helper key 与调用签名不变。
_recommendation_deps = RecommendationDeps(
    build_audit_cache=_build_audit_cache,
    build_adjustment_cache=_build_adjustment_cache,
    can_use_llm=_can_use_llm,
    llm_model=_llm_model,
    llm_base_url=_llm_base_url,
    autosave_current_project_state=_autosave_current_project_state,
    expense_summary_table=_expense_summary_table,
    cross_year_expense_table=_cross_year_expense_table,
)
_render_candidate_recommendations_for_module = functools.partial(
    _lo_render_candidate_recommendations_for_module, deps=_recommendation_deps
)
_render_unified_generation_controls = functools.partial(
    _lo_render_unified_generation_controls, deps=_recommendation_deps
)


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
