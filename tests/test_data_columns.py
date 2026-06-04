"""借贷方向（SAP S/H）派生列的回归测试。

S=借方、H=贷方是 SAP 序时账的核心语义，金额拆借/贷错了会直接误导
所有金额类分析。这是必须锁死的不变量。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.data_columns import (
    REQUIRED_ANALYSIS_COLUMNS,
    add_analysis_columns,
    ensure_analysis_columns,
)

pytestmark = pytest.mark.unit


def _minimal_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "总账科目": ["1001", "2202"],
            "过账日期": pd.to_datetime(["2024-03-15", "2024-03-15"]),
            "凭证货币价值": [100.0, -100.0],
            "借/贷标识": ["S", "H"],
        }
    )


def test_debit_credit_split_by_sh() -> None:
    out = add_analysis_columns(_minimal_df())
    # S=借方 → _debit_amount 取原值，_credit_amount=0
    assert out.loc[0, "_debit_amount"] == 100.0
    assert out.loc[0, "_credit_amount"] == 0
    # H=贷方 → _credit_amount 取原值，_debit_amount=0
    assert out.loc[1, "_credit_amount"] == -100.0
    assert out.loc[1, "_debit_amount"] == 0


def test_abs_columns_are_nonnegative() -> None:
    out = add_analysis_columns(_minimal_df())
    assert (out["_amount_abs"] >= 0).all()
    assert out.loc[1, "_credit_abs"] == 100.0  # H 行绝对值


def test_pnl_effect_is_negated_amount() -> None:
    out = add_analysis_columns(_minimal_df())
    assert out["_pnl_effect"].tolist() == [-100.0, 100.0]


def test_does_not_mutate_input() -> None:
    df = _minimal_df()
    add_analysis_columns(df)
    assert "_debit_amount" not in df.columns


def test_tolerates_missing_optional_columns() -> None:
    # 缺少客户/供应商/物料等可选列时不应报错，派生列填默认值
    out = add_analysis_columns(_minimal_df())
    assert REQUIRED_ANALYSIS_COLUMNS.issubset(set(out.columns))
    assert (out["_customer_display"] == "未维护").all()


def test_ensure_analysis_columns_skips_when_present() -> None:
    out = add_analysis_columns(_minimal_df())
    # 已含全部派生列时应原样返回（同一对象）
    assert ensure_analysis_columns(out) is out
