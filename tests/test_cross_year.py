"""跨年勾稽的回归测试。

跨年预提-冲回配对是检测跨期调节利润的核心规则之一。这里锁住"悬空预提"
（冲回不足）能被识别这一关键行为，避免重构时悄悄失效。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.cross_year import (
    _accrual_reversal_pairs,
    _overrides_signature,
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
