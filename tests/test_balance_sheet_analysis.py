"""资产负债分析：科目分类扩展 + 通用「科目类别月度变动」引擎测试。

口径定调：序时账是流量数据，本页只做发生额/变动分析，非余额表。
净变动按资产/负债大类的方向约定（资产借增、负债贷增）给符号，便于审计直读。
"""

from __future__ import annotations

import pandas as pd
import pytest

from modules.account_classifier import (
    BALANCE_SHEET_CATEGORIES,
    BALANCE_SHEET_SIDE,
    CAT_ADVANCE_RECEIPT,
    CAT_AP,
    CAT_CASH,
    CAT_EQUITY,
    CAT_FIXED_ASSET,
    CAT_INVENTORY,
    CAT_LOAN,
    CAT_PREPAY,
    CAT_TAX_PAYABLE,
    auto_classify,
)
from modules.data_columns import add_analysis_columns
from modules.visual_analysis import (
    build_category_account_breakdown_from_work,
    build_category_account_entry_top10_from_work,
    build_category_entry_top10_from_work,
    build_category_monthly_movement_from_work,
)

pytestmark = pytest.mark.unit


# ── 科目分类扩展 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "name,expected",
    [
        ("银行存款", CAT_CASH),
        ("库存现金", CAT_CASH),
        ("库存商品", CAT_INVENTORY),
        ("原材料", CAT_INVENTORY),
        ("固定资产", CAT_FIXED_ASSET),
        ("在建工程", CAT_FIXED_ASSET),
        ("预付账款", CAT_PREPAY),
        ("预收账款", CAT_ADVANCE_RECEIPT),
        ("合同负债", CAT_ADVANCE_RECEIPT),
        ("应交税费", CAT_TAX_PAYABLE),
        ("短期借款", CAT_LOAN),
        ("实收资本", CAT_EQUITY),
        ("未分配利润", CAT_EQUITY),
    ],
)
def test_balance_sheet_account_classification(name: str, expected: str) -> None:
    assert auto_classify(name) == expected


def test_new_categories_do_not_break_existing() -> None:
    # 回归：原有类别不被新关键词抢走
    assert auto_classify("主营业务收入") == "收入"
    assert auto_classify("应付账款") == CAT_AP
    assert auto_classify("其他应收款") == "其他应收"
    assert auto_classify("税金及附加") == "税金及附加"


def test_balance_sheet_side_mapping() -> None:
    assert BALANCE_SHEET_SIDE[CAT_CASH] == "资产"
    assert BALANCE_SHEET_SIDE[CAT_AP] == "负债"
    assert CAT_CASH in BALANCE_SHEET_CATEGORIES
    # P&L 类别不应出现在资产负债页
    assert "收入" not in BALANCE_SHEET_CATEGORIES


# ── 通用月度变动引擎 ────────────────────────────────────────


def _work(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    return add_analysis_columns(df)


def test_asset_net_change_is_debit_minus_credit() -> None:
    # 货币资金（资产）：借增贷减，净变动 = 借 - 贷
    work = _work([
        {"凭证编号": "1", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "S", "公司代码货币价值": 100.0},
        {"凭证编号": "2", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-20"), "借/贷标识": "H", "公司代码货币价值": 30.0},
    ])
    monthly = build_category_monthly_movement_from_work(work, CAT_CASH)
    jan = monthly[monthly["月份"] == 1].iloc[0]
    assert jan["借方发生额"] == pytest.approx(100.0)
    assert jan["贷方发生额"] == pytest.approx(30.0)
    assert jan["净变动"] == pytest.approx(70.0)


def test_liability_net_change_is_credit_minus_debit() -> None:
    # 应付账款（负债）：贷增借减，净变动 = 贷 - 借
    work = _work([
        {"凭证编号": "1", "总账科目": "2202", "总账科目：长文本": "应付账款",
         "过账日期": pd.Timestamp("2024-03-10"), "借/贷标识": "H", "公司代码货币价值": 100.0},
        {"凭证编号": "2", "总账科目": "2202", "总账科目：长文本": "应付账款",
         "过账日期": pd.Timestamp("2024-03-15"), "借/贷标识": "S", "公司代码货币价值": 20.0},
    ])
    monthly = build_category_monthly_movement_from_work(work, CAT_AP)
    mar = monthly[monthly["月份"] == 3].iloc[0]
    assert mar["借方发生额"] == pytest.approx(20.0)
    assert mar["贷方发生额"] == pytest.approx(100.0)
    assert mar["净变动"] == pytest.approx(80.0)


def test_monthly_movement_covers_all_12_months() -> None:
    work = _work([
        {"凭证编号": "1", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "S", "公司代码货币价值": 100.0},
    ])
    monthly = build_category_monthly_movement_from_work(work, CAT_CASH)
    assert monthly["月份"].tolist() == list(range(1, 13))


def test_entry_drilldown_filters_by_month_and_direction() -> None:
    work = _work([
        {"凭证编号": "A", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "S", "公司代码货币价值": 100.0},
        {"凭证编号": "B", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-20"), "借/贷标识": "H", "公司代码货币价值": 30.0},
    ])
    debit_entries = build_category_entry_top10_from_work(work, CAT_CASH, month=1, direction="debit")
    assert debit_entries["凭证编号"].tolist() == ["A"]
    credit_entries = build_category_entry_top10_from_work(work, CAT_CASH, month=1, direction="credit")
    assert credit_entries["凭证编号"].tolist() == ["B"]
    net_entries = build_category_entry_top10_from_work(work, CAT_CASH, month=1, direction="net")
    assert set(net_entries["凭证编号"]) == {"A", "B"}


def test_account_breakdown_groups_and_ranks() -> None:
    work = _work([
        {"凭证编号": "1", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "S", "公司代码货币价值": 100.0},
        {"凭证编号": "2", "总账科目": "1001", "总账科目：长文本": "库存现金",
         "过账日期": pd.Timestamp("2024-01-11"), "借/贷标识": "S", "公司代码货币价值": 10.0},
    ])
    breakdown = build_category_account_breakdown_from_work(work, CAT_CASH)
    # 按净变动绝对值降序：银行存款(100) 在库存现金(10) 之前
    assert breakdown.iloc[0]["科目编号"] == "1002"
    assert "占比" in breakdown.columns


def test_account_entry_drilldown_filters_by_code() -> None:
    work = _work([
        {"凭证编号": "A", "总账科目": "1002", "总账科目：长文本": "银行存款",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "S", "公司代码货币价值": 100.0},
        {"凭证编号": "B", "总账科目": "1001", "总账科目：长文本": "库存现金",
         "过账日期": pd.Timestamp("2024-01-11"), "借/贷标识": "S", "公司代码货币价值": 10.0},
    ])
    entries = build_category_account_entry_top10_from_work(work, CAT_CASH, "1002")
    assert set(entries["凭证编号"]) == {"A"}


def test_empty_category_returns_empty_frames() -> None:
    work = _work([
        {"凭证编号": "1", "总账科目": "6001", "总账科目：长文本": "主营业务收入",
         "过账日期": pd.Timestamp("2024-01-10"), "借/贷标识": "H", "公司代码货币价值": 100.0},
    ])
    # 数据里没有存货科目
    monthly = build_category_monthly_movement_from_work(work, CAT_INVENTORY)
    assert (monthly["借方发生额"] == 0).all()
    assert build_category_entry_top10_from_work(work, CAT_INVENTORY, month=1, direction="debit").empty
