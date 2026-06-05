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
