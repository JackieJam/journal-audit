"""规则参数 / 条件 / 变更的中文文本渲染工具。

把 rules_config 里的规则参数翻译成审计师可读的条件描述、变更对比和启用计数。
纯函数，无 Streamlit / session 依赖，可被任意层调用并单独测试。
从 app.py 抽离；app.py 通过 alias 保留原调用名（_rule_condition_lines 等），
调用点与注入给各子页签的 helper key 不变。
"""

from __future__ import annotations

from typing import Any

from modules.formatting import (
    format_list,
    format_money,
    format_multiplier,
    format_percent,
)
from config.constants import RULE_ORDER, RULE_META, PARAM_LABELS


def format_param_value(key: str, value: Any) -> str:
    if key in {"max_single_amount", "min_total", "round_number_threshold", "repeat_threshold",
               "holiday_min_amount", "pnl_amount_threshold", "min_amount", "large_threshold",
               "min_revenue_amount"}:
        return format_money(value)
    if key in {"window_days", "repeat_window_days", "match_window_days", "month_end_days"}:
        return f"{value}天"
    if key in {"min_txn_count", "repeat_min_count", "frequent_count", "max_sample_size",
               "max_candidate_groups", "max_related_vouchers"}:
        return f"{value}"
    if key in {"amount_tolerance", "coverage_threshold", "concentration_threshold", "margin_threshold",
               "low_margin_threshold", "max_loss_rate", "min_match_score"}:
        return format_percent(value)
    if key in {"burst_multiplier", "multiplier", "dec_multiplier", "baseline_multiplier"}:
        return format_multiplier(value)
    if key == "months":
        return "、".join(f"{m}月" for m in value) if isinstance(value, list) else str(value)
    if key in {"keywords", "whitelist_keywords", "whitelist_voucher_types",
               "income_account_prefixes", "cost_account_prefixes"}:
        return format_list(value)
    if key == "categories" and isinstance(value, dict):
        parts = []
        for name, cfg in value.items():
            threshold = cfg.get("threshold")
            parts.append(f"{name}≥{format_money(threshold)}")
        return "；".join(parts)
    return str(value)


def generic_param_lines(params: dict[str, Any]) -> list[str]:
    lines = []
    for key, value in params.items():
        label = PARAM_LABELS.get(key, key)
        lines.append(f"{label}：{format_param_value(key, value)}")
    return lines


def rule_condition_lines(rule_key: str, rule_cfg: dict[str, Any]) -> list[str]:
    c = rule_cfg or {}
    if rule_key == "splitting":
        return [
            f"同一供应商在 {c.get('window_days', '—')} 天内至少 {c.get('min_txn_count', '—')} 笔。",
            f"单笔不超过 {format_money(c.get('max_single_amount', 0))}，合计超过 {format_money(c.get('min_total', 0))}。",
            f"当日笔数超过该供应商日均 {format_multiplier(c.get('burst_multiplier', 0))}，同时继续关注同日/窗口内金额高度相似的模式。",
        ]
    if rule_key == "large_amount":
        return [
            f"把最大行金额达到 {format_money(c.get('round_number_threshold', 0))} 的整数金额交易先拉出来。",
            f"同一供应商在 {c.get('repeat_window_days', '—')} 天内出现至少 {c.get('repeat_min_count', '—')} 笔、每笔达到 {format_money(c.get('repeat_threshold', 0))} 的重复大额也进入样本。",
            f"若节假日/周末过账金额达到 {format_money(c.get('holiday_min_amount', 0))}，且操作者周末率显著高于公司基线，也一并标记。",
        ]
    if rule_key == "manual_entry":
        return [
            "先识别 SA 型凭证或文本中直接出现“手工”的凭证。",
            f"重点关注损益科目金额达到 {format_money(c.get('pnl_amount_threshold', 0))} 的手工凭证。",
            f"同时关注月末前 {c.get('month_end_days', '—')} 天内的手工调整，以及手工率显著高于公司均值的用户。",
        ]
    if rule_key == "accrual_anomaly":
        return [
            f"先抓取金额不低于 {format_money(c.get('min_amount', 0))} 的非常规预提/计提。",
            f"如果 {c.get('match_window_days', '—')} 天内没有找到对应冲回，或金额差异超过 {format_percent(c.get('amount_tolerance', 0))}，就视为悬空计提。",
            "同时关注谁在集中做非常规计提，防止个别用户长期独占该类分录。",
        ]
    if rule_key == "yearend_surge":
        focus_months = format_param_value("months", c.get("months", []))
        return [
            f"把 {focus_months} 的收入与其他月份均值做比较。",
            f"当目标月份收入高于基线 {format_multiplier(c.get('multiplier', 0))} 以上时，整个月份相关收入凭证进入样本。",
        ]
    if rule_key == "financing_trade":
        return [
            f"以 {format_list(c.get('income_account_prefixes', ['6001', '6051']))} 收入凭证为主凭证，收入达到 {format_money(c.get('min_revenue_amount', 0))} 后进入配对池。",
            f"在 {c.get('window_days', '—')} 天内寻找 {format_list(c.get('cost_account_prefixes', ['6401', '6402']))} 成本凭证，按日期、对手方、文本关键词、业务类别和金额关系计算匹配得分。",
            f"当匹配得分不低于 {format_percent(c.get('min_match_score', 0))}、组合毛利率不高于 {format_percent(c.get('low_margin_threshold', 0))}，且亏损率不超过 {format_percent(c.get('max_loss_rate', 0))} 时，作为“疑点组合”进入复核。",
            f"每次最多保留 {c.get('max_candidate_groups', '—')} 组候选，每组最多关联 {c.get('max_related_vouchers', '—')} 张成本凭证；文本出现 {format_list(c.get('keywords', []))} 但找不到成本时，也作为低证据候选提示。",
        ]
    if rule_key == "cross_year_accrual":
        return [
            f"跨年预提在 {c.get('match_window_days', '—')} 天内的冲回覆盖率若低于 {format_percent(c.get('coverage_threshold', 0))}，就进入跨期风险样本。",
            "这类规则依赖跨年交叉稽核发现，重点看预提是否真正被后续期间消化。",
        ]
    if rule_key == "cross_year_revenue":
        return [
            f"12 月收入若高于前 11 个月平均水平 {format_multiplier(c.get('dec_multiplier', 0))}，就作为跨年收入前置迹象保留。",
            "它和年末突击确认规则互相补位：一个看单年内部的异常高点，一个看跨年层面的收入漂移。",
        ]
    if rule_key == "cash_pool":
        return [
            f"文本中若出现 {format_list(c.get('keywords', []))} 等资金归集/划转关键词，就先做同凭证穿透。",
            f"其中最大行金额达到 {format_money(c.get('large_threshold', 0))} 的交易优先进入样本。",
        ]
    if rule_key == "user_concentration":
        return [
            f"当单一用户过账行数占比达到 {format_percent(c.get('concentration_threshold', 0))} 及以上时，视为职责分离风险信号。",
            "这条规则不是直接判断舞弊，而是把“谁过于集中”显式拉出来供审计师复核。",
        ]
    if rule_key == "reversal_pattern":
        return [
            f"文本出现冲销/反记账关键词的凭证，会继续按大额和频繁两个方向筛查。",
            f"单笔冲销达到 {format_money(c.get('large_threshold', 0))} 的，直接作为大额冲销关注。",
            f"同一用户若至少冲销 {c.get('frequent_count', '—')} 笔，也会被归为频繁冲销用户。",
        ]
    if rule_key == "sensitive_fees":
        category_cfg = c.get("categories", {})
        category_bits = []
        for name, cfg in category_cfg.items():
            category_bits.append(f"{name}≥{format_money(cfg.get('threshold', 0))}")
        bits = "；".join(category_bits)
        return [
            f"对敏感费用按类别设门槛：{bits}。",
            f"若某个用户的敏感费用占比高于公司均值 {format_multiplier(c.get('baseline_multiplier', 0))}，则该用户相关敏感费用凭证会被整组拉出。",
            "对于非异常用户，仅保留超过类别金额阈值的凭证，避免被零碎小额淹没。",
        ]
    return generic_param_lines({k: v for k, v in c.items() if k not in {"enabled", "rationale"}})


def rule_change_lines(rule_key: str, current_rule: dict[str, Any], base_rule: dict[str, Any]) -> list[str]:
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
                f"{label}：{format_param_value(key, base_value)} -> {format_param_value(key, value)}"
            )
    return changes


def collect_rule_changes(base_cfg: dict[str, Any], current_cfg: dict[str, Any]) -> list[tuple[str, list[str]]]:
    rows = []
    for rule_key in RULE_ORDER:
        current_rule = current_cfg.get(rule_key, {})
        base_rule = base_cfg.get(rule_key, {})
        changes = rule_change_lines(rule_key, current_rule, base_rule)
        if changes:
            rows.append((RULE_META.get(rule_key, {}).get("title", rule_key), changes))
    return rows


def rule_counts(cfg: dict[str, Any] | None) -> tuple[int, int]:
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
