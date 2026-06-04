"""科目自动分类的回归测试。

分类正确性直接决定跨年勾稽、可视化分类汇总的准确性，是审计结论的上游，
必须有回归保护。重点验证优先级顺序（先命中先终止）这一最易回归的逻辑。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.account_classifier import (
    CAT_AP,
    CAT_AP_ACCRUAL,
    CAT_AR,
    CAT_COST,
    CAT_EXPENSE,
    CAT_OTHER_PAYABLE,
    CAT_OTHER_RECEIVABLE,
    CAT_REVENUE,
    CAT_UNCATEGORIZED,
    auto_classify,
    build_account_overview,
    classify_dataframe,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "name, expected",
    [
        ("应付账款-暂估", CAT_AP_ACCRUAL),   # 暂估优先于应付
        ("GR/IR 暂估", CAT_AP_ACCRUAL),
        ("其他应收款", CAT_OTHER_RECEIVABLE),  # 其他应收优先于应收
        ("其他应付款", CAT_OTHER_PAYABLE),     # 其他应付优先于应付
        ("应收账款", CAT_AR),
        ("应付账款", CAT_AP),
        ("主营业务收入", CAT_REVENUE),
        ("主营业务成本", CAT_COST),
        ("管理费用", CAT_EXPENSE),
    ],
)
def test_priority_order(name: str, expected: str) -> None:
    assert auto_classify(name) == expected


@pytest.mark.parametrize("value", [None, "", "   ", "nan", "NaN", "无关科目"])
def test_uncategorized(value) -> None:
    assert auto_classify(value) == CAT_UNCATEGORIZED


def test_classify_dataframe_is_immutable() -> None:
    df = pd.DataFrame(
        {"总账科目": ["1001", "2202"], "总账科目：长文本": ["应收账款", "应付账款"]}
    )
    out = classify_dataframe(df)
    assert "_acct_category" not in df.columns       # 原 df 未被污染
    assert out["_acct_category"].tolist() == [CAT_AR, CAT_AP]


def test_classify_dataframe_override_wins() -> None:
    df = pd.DataFrame(
        {"总账科目": ["1001"], "总账科目：长文本": ["应收账款"]}
    )
    # 用户手动把这个科目改判为成本
    out = classify_dataframe(df, overrides={"1001": CAT_COST})
    assert out["_acct_category"].tolist() == [CAT_COST]


def test_classify_dataframe_ignores_invalid_override() -> None:
    df = pd.DataFrame({"总账科目": ["1001"], "总账科目：长文本": ["应收账款"]})
    # 非法类别的覆盖应被忽略，回退到自动分类
    out = classify_dataframe(df, overrides={"1001": "不存在的类别"})
    assert out["_acct_category"].tolist() == [CAT_AR]


def test_build_account_overview_effective_category() -> None:
    df = pd.DataFrame(
        {
            "总账科目": ["1001", "1001", "6001"],
            "总账科目：长文本": ["应收账款", "应收账款", "主营业务收入"],
            "凭证货币价值": [100.0, -50.0, 200.0],
        }
    )
    overview = build_account_overview(df, overrides={"1001": CAT_COST})
    row_1001 = overview.set_index("科目编号").loc["1001"]
    assert row_1001["生效分类"] == CAT_COST       # 人工覆盖生效
    assert row_1001["行数"] == 2
    assert row_1001["金额"] == 150.0              # 绝对值求和
