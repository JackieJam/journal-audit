"""跨年勾稽的回归测试。

跨年预提-冲回配对是检测跨期调节利润的核心规则之一。这里锁住"悬空预提"
（冲回不足）能被识别这一关键行为，避免重构时悄悄失效。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.cross_year import (
    _CROSS_YEAR_DETECTION_DEFAULTS,
    _accrual_reversal_pairs,
    _cross_year_thresholds,
    _manual_entry_trend,
    _overrides_signature,
    _revenue_timing_drift,
    _thresholds_signature,
    run_cross_year_analysis,
)

pytestmark = pytest.mark.unit


def _accrual_df(year: int, amount: float, text: str, month: int = 12) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "凭证编号": [f"{year}-{month}-001"],
            "过账日期": pd.to_datetime([f"{year}-{month:02d}-20"]),
            "文本": [text],
            "凭证货币价值": [amount],
        }
    )


def test_detects_dangling_accrual() -> None:
    # 2023 年末预提 200 万，2024 年 Q1 完全没有冲回 → 悬空预提（悬空 >100万 → 高风险）
    year_map = {
        2023: _accrual_df(2023, 2_000_000.0, "年末预提费用"),
        2024: _accrual_df(2024, 5_000.0, "正常费用", month=2),
    }
    findings = _accrual_reversal_pairs(year_map)
    assert any(f.category == "预提冲回配对" for f in findings)
    finding = next(f for f in findings if f.category == "预提冲回配对")
    assert finding.severity == "高"
    assert 2023 in finding.years_involved and 2024 in finding.years_involved


def test_small_accrual_ignored() -> None:
    # 低于 10000 的预提不触发（避免噪声）
    year_map = {
        2023: _accrual_df(2023, 500.0, "年末预提费用"),
        2024: _accrual_df(2024, 0.0, "无", month=2),
    }
    assert _accrual_reversal_pairs(year_map) == []


def test_full_reversal_not_flagged() -> None:
    # 足额冲回（覆盖率≈1）不应被标为悬空
    year_map = {
        2023: _accrual_df(2023, 1_000_000.0, "年末预提费用"),
        2024: _accrual_df(2024, 1_000_000.0, "冲销预提", month=1),
    }
    findings = _accrual_reversal_pairs(year_map)
    assert not any(f.category == "预提冲回配对" for f in findings)


def test_single_year_returns_empty() -> None:
    assert run_cross_year_analysis({2023: _accrual_df(2023, 1_000_000.0, "预提")}) == []


def test_overrides_signature_is_hashable_tuple() -> None:
    sig = _overrides_signature()
    assert isinstance(sig, tuple)
    hash(sig)  # 必须可哈希，否则不能作缓存键


# ── 阈值参数化（去耦版方案三）回归测试 ──
# 以下测试在阈值仍硬编码时为红灯，Phase1/2 接线后转绿。


def _revenue_df(year: int, monthly_amounts: dict[int, float]) -> pd.DataFrame:
    rows = [
        {
            "凭证编号": f"{year}-{month}-R",
            "过账日期": pd.Timestamp(f"{year}-{month:02d}-15"),
            "总账科目": "6001",
            "总账科目：长文本": "主营业务收入",
            "凭证货币价值": amt,
            "文本": "收入",
        }
        for month, amt in monthly_amounts.items()
    ]
    return pd.DataFrame(rows)


def test_accrual_coverage_threshold_respected() -> None:
    """覆盖率 75% 的悬空预提：阈值 0.80 应命中，阈值 0.70 不应命中。"""
    year_map = {
        2023: _accrual_df(2023, 1_000_000.0, "年末预提费用"),          # 12 月预提 100 万
        2024: _accrual_df(2024, 750_000.0, "冲销预提", month=1),       # 次年 Q1 冲回 75 万
    }
    flagged_080 = _accrual_reversal_pairs(year_map, coverage_threshold=0.80)
    flagged_070 = _accrual_reversal_pairs(year_map, coverage_threshold=0.70)

    assert any(f.category == "预提冲回配对" for f in flagged_080), "0.80 阈值下 75% 覆盖率应判为悬空"
    assert not any(f.category == "预提冲回配对" for f in flagged_070), "0.70 阈值下 75% 覆盖率不应判为悬空"


def test_revenue_multiplier_threshold_respected() -> None:
    """12 月收入为均值 1.65 倍：阈值 1.8 不触发，阈值 1.5 触发。"""
    months = {m: 100_000.0 for m in range(1, 12)}   # 1-11 月各 10 万
    months[12] = 165_000.0                           # 12 月 16.5 万 → 比值 1.65
    year_map = {
        2023: _revenue_df(2023, months),
        2024: _revenue_df(2024, {1: -50_000.0}),     # 次年 1 月红字冲回
    }
    flagged_18 = _revenue_timing_drift(year_map, dec_multiplier=1.8)
    flagged_15 = _revenue_timing_drift(year_map, dec_multiplier=1.5)

    assert not any(f.category == "收入跨年确认" for f in flagged_18), "1.8 阈值下 1.65 倍不应触发"
    assert any(f.category == "收入跨年确认" for f in flagged_15), "1.5 阈值下 1.65 倍应触发"


def _full_accrual_row(year: int, amount: float, text: str, month: int) -> dict:
    """含全部跨年函数会触达的列，避免 run_cross_year_analysis 跑其余函数时 KeyError。"""
    return {
        "凭证编号": f"{year}-{month}-001",
        "过账日期": pd.Timestamp(f"{year}-{month:02d}-20"),
        "文本": text,
        "凭证货币价值": amount,
        "总账科目": "6601",
        "凭证类型": "SA",
        "供应商编号": "",
        "供应商科目：名称 1": "",
    }


def test_cross_year_cache_invalidates_on_threshold_change() -> None:
    """同一 year_map，不同 coverage_threshold 必须产出不同结果（证明缓存键含阈值）。"""
    year_map = {
        2023: pd.DataFrame([_full_accrual_row(2023, 1_000_000.0, "年末预提费用", 12)]),
        2024: pd.DataFrame([_full_accrual_row(2024, 750_000.0, "冲销预提", 1)]),
    }
    res_080 = run_cross_year_analysis(year_map, {"cross_year_accrual": {"coverage_threshold": 0.80}})
    res_070 = run_cross_year_analysis(year_map, {"cross_year_accrual": {"coverage_threshold": 0.70}})

    has_dangling_080 = any(f.category == "预提冲回配对" for f in res_080)
    has_dangling_070 = any(f.category == "预提冲回配对" for f in res_070)
    assert has_dangling_080 != has_dangling_070, "阈值变化未改变结果——缓存键可能未包含阈值"


# ── Phase2：全部跨年检测阈值 config 化 ──


def test_cross_year_thresholds_defaults_and_detection_block() -> None:
    """空 cfg 回落默认；cross_year_detection 自定义值被正确读出。"""
    defaults = _cross_year_thresholds(None)
    # 两个 UI 阈值 + 全部高级阈值都应在返回 dict 中
    assert defaults["coverage_threshold"] == 0.80
    assert defaults["dec_multiplier"] == 1.8
    for key, val in _CROSS_YEAR_DETECTION_DEFAULTS.items():
        assert defaults[key] == val

    custom = _cross_year_thresholds({
        "cross_year_detection": {"expense_spike_multiplier": 9.0, "circular_match_ratio": 0.9},
    })
    assert custom["expense_spike_multiplier"] == 9.0
    assert custom["circular_match_ratio"] == 0.9
    # 未覆盖项仍回默认
    assert custom["balance_buildup_growth_ratio"] == _CROSS_YEAR_DETECTION_DEFAULTS["balance_buildup_growth_ratio"]


def test_thresholds_signature_includes_detection_keys() -> None:
    """缓存签名必须包含高级阈值，否则改了不失效。"""
    sig = dict(_thresholds_signature(_cross_year_thresholds(None)))
    assert "expense_spike_multiplier" in sig
    assert "new_pair_count_threshold" in sig


def _manual_df(year: int, n_total: int, n_manual: int) -> pd.DataFrame:
    # 手工类型用 "SA"（不在 AUTO_VOUCHER_TYPES），自动类型用 "AA"
    types = ["SA"] * n_manual + ["AA"] * (n_total - n_manual)
    return pd.DataFrame({
        "凭证编号": [f"{year}-{i}" for i in range(n_total)],
        "凭证类型": types,
        "过账日期": pd.to_datetime([f"{year}-06-15"] * n_total),
        "文本": ["x"] * n_total,
        "凭证货币价值": [1000.0] * n_total,
    })


def test_manual_entry_delta_threshold_respected() -> None:
    """手工占比从 10% 升到 25%（delta=0.15）：阈值 0.15 不触发，0.10 触发。"""
    year_map = {
        2023: _manual_df(2023, 10, 1),   # 0.10
        2024: _manual_df(2024, 4, 1),    # 0.25
    }
    flagged_015 = _manual_entry_trend(year_map, delta_threshold=0.15)
    flagged_010 = _manual_entry_trend(year_map, delta_threshold=0.10)
    assert not any(f.category == "手工凭证占比持续上升" for f in flagged_015)
    assert any(f.category == "手工凭证占比持续上升" for f in flagged_010)
