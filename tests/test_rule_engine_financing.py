"""融资性贸易规则的凭证事实表回归测试。

锁定 _pnl_category 的调用参数顺序（acct4, account_name）。
历史 bug：rule_engine 调用时把两个参数颠倒，导致 category 恒为空，
rule_financing_trade 的分类匹配（0.15 权重）永久失效。
此测试若参数再次颠倒会立即失败。
"""

from __future__ import annotations

import pytest

from modules.data_columns import _pnl_category
from modules.rule_engine import _build_trade_voucher_facts


@pytest.mark.unit
def test_pnl_category_signature_acct4_first():
    """直接锁定函数签名语义：第一个参数是 4 位科目，第二个是科目名称。"""
    assert _pnl_category("6001", "主营业务收入") == "主营业务-第三方"
    # 参数颠倒时（科目名称当作 acct4）必然落空，作为反例固化语义
    assert _pnl_category("主营业务收入", "6001") == ""


@pytest.mark.unit
def test_trade_voucher_facts_category_not_empty(sample_data):
    """_build_trade_voucher_facts 必须为主营收入/成本凭证产出非空 category。

    这是参数颠倒 bug 的端到端守卫：颠倒后所有 category 都会变成空串。
    """
    df_unified, _ = sample_data
    facts = _build_trade_voucher_facts(df_unified)

    assert not facts.empty
    # 至少存在主营业务相关的分类（6001/6401 科目）
    main_business = facts["category"].str.startswith("主营业务")
    assert main_business.any(), (
        "所有 category 均为空——_pnl_category 调用参数可能再次被颠倒"
    )
