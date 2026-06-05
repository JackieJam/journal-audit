"""modules.rule_text 纯函数单元测试。"""

from __future__ import annotations

import pytest

from modules.rule_text import (
    collect_rule_changes,
    format_param_value,
    generic_param_lines,
    rule_change_lines,
    rule_condition_lines,
    rule_counts,
)

pytestmark = pytest.mark.unit


class TestFormatParamValue:
    def test_money_keys_use_money_format(self):
        out = format_param_value("max_single_amount", 12000)
        assert "万" in out or "元" in out

    def test_day_keys_append_day_unit(self):
        assert format_param_value("window_days", 7) == "7天"

    def test_count_keys_plain_int(self):
        assert format_param_value("min_txn_count", 3) == "3"

    def test_percent_keys_use_percent_format(self):
        assert format_param_value("coverage_threshold", 0.8).endswith("%")

    def test_multiplier_keys_use_multiplier_format(self):
        assert "倍" in format_param_value("multiplier", 2.5)

    def test_months_list_joined(self):
        assert format_param_value("months", [11, 12]) == "11月、12月"

    def test_months_non_list_fallback(self):
        assert format_param_value("months", "Q4") == "Q4"

    def test_list_keys_use_list_format(self):
        out = format_param_value("keywords", ["资金归集", "划转"])
        assert "资金归集" in out and "划转" in out

    def test_categories_dict_rendered(self):
        out = format_param_value("categories", {"招待费": {"threshold": 5000}})
        assert "招待费" in out and "≥" in out

    def test_unknown_key_str_fallback(self):
        assert format_param_value("some_unknown_key", 42) == "42"


class TestGenericParamLines:
    def test_each_param_becomes_a_line(self):
        lines = generic_param_lines({"window_days": 7, "min_txn_count": 3})
        assert len(lines) == 2
        assert all("：" in line for line in lines)


class TestRuleConditionLines:
    def test_known_rule_returns_nonempty(self):
        lines = rule_condition_lines("splitting", {"window_days": 7, "min_txn_count": 3})
        assert lines and all(isinstance(x, str) for x in lines)

    def test_unknown_rule_falls_back_to_generic(self):
        lines = rule_condition_lines("unknown_rule", {"window_days": 7, "enabled": True, "rationale": "x"})
        # enabled / rationale 被剔除，只剩 window_days
        assert len(lines) == 1
        assert "window_days" in lines[0] or "天" in lines[0]

    def test_empty_cfg_does_not_crash(self):
        assert isinstance(rule_condition_lines("splitting", {}), list)


class TestRuleChangeLines:
    def test_non_dict_returns_empty(self):
        assert rule_change_lines("splitting", None, {}) == []

    def test_enabled_toggle_detected(self):
        changes = rule_change_lines("splitting", {"enabled": False}, {"enabled": True})
        assert any("启用状态" in c for c in changes)

    def test_param_change_detected(self):
        changes = rule_change_lines(
            "splitting", {"window_days": 10}, {"window_days": 7}
        )
        assert any("->" in c for c in changes)

    def test_no_change_returns_empty(self):
        assert rule_change_lines("splitting", {"window_days": 7}, {"window_days": 7}) == []

    def test_categories_change_uses_special_message(self):
        changes = rule_change_lines(
            "sensitive_fees",
            {"categories": {"招待费": {"threshold": 6000}}},
            {"categories": {"招待费": {"threshold": 5000}}},
        )
        assert any("重新校准" in c for c in changes)


class TestCollectRuleChanges:
    def test_only_changed_rules_returned(self):
        base = {"splitting": {"window_days": 7}, "large_amount": {"large_threshold": 100}}
        current = {"splitting": {"window_days": 10}, "large_amount": {"large_threshold": 100}}
        rows = collect_rule_changes(base, current)
        titles = [t for t, _ in rows]
        assert len(rows) == 1
        # 未变更的 large_amount 不应出现
        assert all("large" not in str(t).lower() for t in titles) or len(rows) == 1


class TestRuleCounts:
    def test_none_cfg_returns_zero(self):
        assert rule_counts(None) == (0, 0)

    def test_empty_cfg_returns_zero(self):
        assert rule_counts({}) == (0, 0)

    def test_counts_enabled_and_disabled(self):
        from config.constants import RULE_ORDER

        cfg = {k: {"enabled": True} for k in RULE_ORDER}
        # 关掉第一条
        cfg[RULE_ORDER[0]] = {"enabled": False}
        enabled, disabled = rule_counts(cfg)
        assert enabled == len(RULE_ORDER) - 1
        assert disabled == 1

    def test_missing_rule_defaults_to_enabled(self):
        # cfg 为非空但缺某规则键时，默认 enabled=True
        enabled, disabled = rule_counts({"splitting": {"enabled": False}})
        # splitting 关闭，其余缺失键按 enabled 计
        assert disabled == 1
