"""斩断 LLM 反馈环：跨年检测阈值不应被校准结果改写。

cross_year 的 coverage_threshold / dec_multiplier 驱动实际检测计算，
若让 LLM 校准改写会形成"发现→校准→发现"的反馈环，损害可复现性。
pin_cross_year_thresholds 必须把这些参数还原为用户当前值或默认值。
"""

from __future__ import annotations

import pytest

from modules.rule_generator import (
    CROSS_YEAR_PINNED_PARAMS,
    default_rules_config,
    pin_cross_year_thresholds,
)

pytestmark = pytest.mark.unit


def test_pin_restores_user_value_over_llm():
    """LLM 把阈值改成离谱值时，应被还原为用户当前值。"""
    user_cfg = default_rules_config()
    user_cfg["cross_year_accrual"]["coverage_threshold"] = 0.70  # 用户手动设的
    user_cfg["cross_year_revenue"]["dec_multiplier"] = 2.5

    llm_cfg = default_rules_config()
    llm_cfg["cross_year_accrual"]["coverage_threshold"] = 0.99   # LLM 乱改
    llm_cfg["cross_year_revenue"]["dec_multiplier"] = 9.9

    pinned = pin_cross_year_thresholds(llm_cfg, prior=user_cfg)

    assert pinned["cross_year_accrual"]["coverage_threshold"] == 0.70
    assert pinned["cross_year_revenue"]["dec_multiplier"] == 2.5


def test_pin_falls_back_to_default_when_no_prior():
    """无 prior 时回落默认值，不保留 LLM 改写值。"""
    defaults = default_rules_config()
    llm_cfg = default_rules_config()
    llm_cfg["cross_year_accrual"]["coverage_threshold"] = 0.99

    pinned = pin_cross_year_thresholds(llm_cfg, prior=None)

    assert pinned["cross_year_accrual"]["coverage_threshold"] == (
        defaults["cross_year_accrual"]["coverage_threshold"]
    )


def test_pin_leaves_other_rules_untouched():
    """非跨年规则的 LLM 校准值不应被动。"""
    llm_cfg = default_rules_config()
    llm_cfg["large_amount"]["enabled"] = False
    sentinel = llm_cfg["large_amount"].copy()

    pin_cross_year_thresholds(llm_cfg, prior=default_rules_config())

    assert llm_cfg["large_amount"] == sentinel


def test_pinned_params_cover_configured_keys():
    """守卫：被钉住的参数键必须真实存在于默认配置，防止配置漂移。"""
    defaults = default_rules_config()
    for rule_key, params in CROSS_YEAR_PINNED_PARAMS.items():
        assert rule_key in defaults
        for pk in params:
            assert pk in defaults[rule_key], f"{rule_key}.{pk} 不在 default_rules.json"
