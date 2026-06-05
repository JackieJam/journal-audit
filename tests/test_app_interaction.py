"""AppTest 交互测试：实际点击关键按钮，验证核心流程不崩，以及我们修过的导航机制。

与 test_app_smoke.py（只验证渲染无异常）互补——这里真正触发 button 交互。

未覆盖（AppTest 1.56 能力限制，仍需手动回归）：
- 「加入疑点库 / 批量直入」等候选池操作藏在 popover 内，且需先在 st.dataframe
  里选中明细行；AppTest 无法模拟行选择 + popover 内元素操作。
- segmented_control 不被 AppTest 暴露，无法模拟「点击切页签」，页签切换仍靠
  预置 widget key（见 test_app_smoke.py）。
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration

APP_PATH = "app.py"


def _load(sample_data, tab: str, **extra) -> AppTest:
    df_unified, year_map = sample_data
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.session_state["df_unified"] = df_unified
    at.session_state["year_map"] = year_map
    at.session_state["engagement_name"] = "interaction-test"
    at.session_state["active_tab_name"] = tab
    for key, value in extra.items():
        at.session_state[key] = value
    return at.run()


def _click(at: AppTest, label_substr: str) -> bool:
    """点击第一个 label 含子串的按钮；找到并点击返回 True。"""
    for button in at.button:
        if label_substr in button.label:
            button.click().run()
            return True
    return False


@pytest.mark.parametrize("tab", ["规则管理", "样本抽取"])
def test_main_tabs_render_with_data(isolated_app_home, sample_data, tab):
    """有数据时规则/样本抽取页渲染不报错（补 test_app_smoke 的空数据场景）。"""
    at = _load(sample_data, tab)
    assert not at.exception


def test_upload_confirm_jumps_to_analysis(isolated_app_home, sample_data):
    """点「确认识别结果，进入分析页」应通过 _pending_tab 跳到分析页（active_tab==1）。

    这是本轮修复的程序化跳转机制的端到端回归。
    """
    at = _load(sample_data, "上传数据")
    assert _click(at, "进入分析页"), "未找到「进入分析页」按钮"
    assert not at.exception
    assert at.session_state["active_tab"] == 1


def test_create_rule_button_does_not_crash(isolated_app_home, sample_data):
    """规则管理「创建规则」按钮可点击且不抛异常。"""
    at = _load(sample_data, "规则管理")
    assert _click(at, "创建规则"), "未找到「创建规则」按钮"
    assert not at.exception


def test_run_sampling_button_does_not_crash(isolated_app_home, sample_data):
    """样本抽取「执行样本抽取」按钮可点击且不抛异常（无 LLM Key 时走 fallback）。"""
    at = _load(sample_data, "样本抽取")
    assert _click(at, "执行样本抽取"), "未找到「执行样本抽取」按钮"
    assert not at.exception


# ── LLM 建议编排器基线 ──
# 编排器（_render_candidate_recommendations_for_module + _detail_for_recommendation
# + _backfill_recommendation_condition + _add_recommendations）此前完全无护网：
# 无 Key 时 _can_use_llm() 直接 return，AppTest 走不到卡片路径。这里预置 _manual_api_key
# （侧边栏每次 run 用 _resolve_api_key() 覆盖 _api_key，故必须从可解析来源注入）并把模型
# 结果直接 seed 进 audit_llm_analysis（绕开真实 LLM 调用），驱动卡片渲染与「加入疑点库」
# 全链路，为后续把编排器抽到 components/llm_orchestration.py 兜底。

_SEEDED_UNIFIED_KEY = "unified::2022,2023::总计"
_SEEDED_RECOMMENDATION = {
    "title": "2023年5月净收入波动",
    "reason": "测试用建议：月度净收入异常，回查当月收入凭证。",
    "risk_level": "中",
    "source_module": "收入成本",
    "source_view": "月度收入成本",
    "tags": ["收入波动"],
    "audit_procedure": "抽查当月大额收入确认凭证",
    "condition": {"kind": "monthly_income_cost", "year": 2023, "month": 5, "metric": "revenue"},
}


def _load_with_seeded_recommendations(sample_data) -> AppTest:
    """加载数据 + 预置 API Key + 模型建议，落在可疑样本库筛选/收入成本内层页签。"""
    return _load(
        sample_data,
        "序时账分析",
        _manual_api_key="test-key",
        _sub_tab_top_name="可疑样本库筛选",
        _sub_tab_inner_name="收入成本",
        audit_year_sel=2023,
        income_cost_category_2023="总计",
        audit_llm_analysis={
            _SEEDED_UNIFIED_KEY: {
                "overview_analysis": {},
                "module_recommendations": {"收入成本": [_SEEDED_RECOMMENDATION]},
            }
        },
    )


def test_recommendation_cards_render_with_seeded_analysis(isolated_app_home, sample_data):
    """有 Key + 已缓存建议时，收入成本页应渲染建议卡片（出现「加入疑点库」按钮）且不报错。"""
    at = _load_with_seeded_recommendations(sample_data)
    assert not at.exception
    assert any("加入疑点库" in b.label for b in at.button), "未渲染出建议卡片的入库按钮"


def test_recommendation_add_to_pool(isolated_app_home, sample_data):
    """点「一键全部加入疑点库」应把建议匹配到的明细写入候选池（覆盖编排器取数全链路）。"""
    at = _load_with_seeded_recommendations(sample_data)
    assert _click(at, "一键全部加入疑点库"), "未找到「一键全部加入疑点库」按钮"
    assert not at.exception
    assert at.session_state["candidate_pool"], "建议未写入候选池，编排器取数链路可能回归"
