"""规则引擎接入跨年发现的开关回归测试。"""

from __future__ import annotations

import pytest

from modules.cross_year import CrossYearFinding
from modules.rule_engine import cross_year_findings_to_hits

pytestmark = pytest.mark.unit


def _finding(category: str, voucher_id: str) -> CrossYearFinding:
    return CrossYearFinding(
        category=category,
        description=f"{category} finding",
        years_involved=[2023, 2024],
        voucher_ids=[voucher_id],
        amount=100.0,
        severity="高",
    )


def test_cross_year_findings_respect_basic_rule_switches() -> None:
    result = cross_year_findings_to_hits(
        [
            _finding("预提冲回配对", "ACCRUAL"),
            _finding("收入跨年确认", "REVENUE"),
        ],
        {
            "cross_year_accrual": {"enabled": False},
            "cross_year_revenue": {"enabled": True},
        },
    )

    assert [hit.voucher_id for hit in result.hits] == ["REVENUE"]
    assert result.hits[0].rule_type == "跨年:收入跨年确认"


def test_advanced_cross_year_findings_can_be_disabled() -> None:
    disabled = cross_year_findings_to_hits(
        [_finding("对手方跨年资金循环", "CIRCULAR")],
        {
            "cross_year_accrual": {"enabled": False},
            "cross_year_revenue": {"enabled": False},
        },
    )
    enabled = cross_year_findings_to_hits(
        [_finding("对手方跨年资金循环", "CIRCULAR")],
        {
            "cross_year_accrual": {"enabled": False},
            "cross_year_revenue": {"enabled": False},
            "cross_year_detection": {"enabled": True},
        },
    )

    assert disabled.hits == []
    assert [hit.voucher_id for hit in enabled.hits] == ["CIRCULAR"]
