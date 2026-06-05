"""AppTest 交互层冒烟测试。

为什么需要：tab 切换、fragment、duplicate element id 等回归都出在渲染层，
普通单元测试覆盖不到（最近三个线上 bug 全部如此）。这里用 Streamlit AppTest
实际执行 app.py，确保各页签加载/渲染不抛异常、不出现重复 element id——重复 key
会在 run 时抛 StreamlitDuplicateElementId，被 at.exception 捕获。

已知限制：Streamlit 1.56 的 AppTest 不暴露 segmented_control 元素，无法直接
模拟「点击」切换页签。改用预置 widget key（active_tab_name / _sub_tab_top_name /
_sub_tab_inner_name）切换当前页签后 run，再断言渲染无异常。这覆盖了「各页签能否
正确渲染」与「无 duplicate id」，但不覆盖切换动作本身的前端交互。
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.integration

APP_PATH = "app.py"
TAB_NAMES = ["上传数据", "序时账分析", "规则管理", "样本抽取"]
TOP_SUBTABS = ["财务概况", "可疑样本库筛选", "疑点库管理"]
INNER_SUBTABS = ["收入成本", "费用", "暂估往来", "调账冲销", "跨年交叉稽核", "统计画像"]


def test_app_loads_without_data(isolated_app_home):
    """空状态启动不报错——可抓 import 错误与 sidebar 的 duplicate id。"""
    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception


@pytest.mark.parametrize("tab", TAB_NAMES)
def test_each_main_tab_renders_empty(isolated_app_home, tab):
    """无数据时四个主页签各自渲染不报错，且预置 key 能正确切换 active_tab。"""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["active_tab_name"] = tab
    at.run()
    assert not at.exception
    assert at.session_state["active_tab"] == TAB_NAMES.index(tab)


def _load_with_data(sample_data) -> AppTest:
    df_unified, year_map = sample_data
    at = AppTest.from_file(APP_PATH, default_timeout=120)
    at.session_state["df_unified"] = df_unified
    at.session_state["year_map"] = year_map
    at.session_state["engagement_name"] = "smoke-test"
    at.session_state["active_tab_name"] = "序时账分析"
    return at


def test_analysis_top_subtabs_render(isolated_app_home, sample_data):
    """有数据时，分析页三个顶层子页签轮流渲染不报错。"""
    at = _load_with_data(sample_data)
    at.session_state["_sub_tab_top_name"] = TOP_SUBTABS[0]
    at.run()  # 首跑生成 profiles/financials
    assert not at.exception
    for sub in TOP_SUBTABS:
        at.session_state["_sub_tab_top_name"] = sub
        at.run()
        assert not at.exception, f"top sub-tab {sub} 渲染异常：{at.exception}"


def test_analysis_inner_subtabs_render(isolated_app_home, sample_data):
    """可疑样本库筛选下，6 个 fragment 内层子页签轮流渲染不报错。

    这是最近 fragment 重构的回归护网：任一子页签渲染异常或出现 duplicate id
    都会被 at.exception 抓到。
    """
    at = _load_with_data(sample_data)
    at.session_state["_sub_tab_top_name"] = "可疑样本库筛选"
    at.run()
    assert not at.exception
    for inner in INNER_SUBTABS:
        at.session_state["_sub_tab_inner_name"] = inner
        at.run()
        assert not at.exception, f"inner sub-tab {inner} 渲染异常：{at.exception}"
