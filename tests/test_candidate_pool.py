"""候选池抽样口径回归测试。"""

from __future__ import annotations

import pandas as pd
import pytest

from modules import candidate_pool as cp
from modules.rule_engine import RuleHit, RuleResult

pytestmark = pytest.mark.unit


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "凭证编号": ["V1", "V2"],
        "过账日期": pd.to_datetime(["2024-12-31", "2024-12-31"]),
        "凭证类型": ["SA", "SA"],
        "文本": ["费用调整", "收入冲回"],
        "总账科目": ["6601", "6001"],
        "总账科目：长文本": ["销售费用", "主营业务收入"],
        "借/贷标识": ["S", "H"],
        "凭证货币价值": [123.45, 456.78],
    })


def test_sample_from_rule_results_works_without_candidate_pool() -> None:
    """候选池为空时，最终样本仍应来自已执行的规则结果。"""
    result = RuleResult(
        rule_name="测试规则",
        hits=[
            RuleHit(
                voucher_id="V1",
                rule_type="测试",
                evidence="命中主凭证",
                line_indices=(0,),
                priority=5,
                related_voucher_ids=("V2",),
            )
        ],
    )

    samples = cp.sample_from_rule_results([result], _sample_df(), size=10, pool=[])
    lookup = {row["凭证编号"]: row for row in samples}

    assert set(lookup) == {"V1", "V2"}
    assert lookup["V1"]["借方金额"] == pytest.approx(123.45)
    assert lookup["V1"]["贷方金额"] == 0
    assert lookup["V2"]["贷方金额"] == pytest.approx(456.78)
    assert lookup["V2"]["来源模块"] == "其他"


def test_voucher_ids_from_rule_results_respects_priority_limit() -> None:
    result = RuleResult(
        rule_name="测试规则",
        hits=[
            RuleHit("LOW", "低优先级", "evidence", (), priority=1),
            RuleHit("HIGH", "高优先级", "evidence", (), priority=5),
        ],
    )

    assert cp.voucher_ids_from_rule_results([result], size=1) == ["HIGH"]
