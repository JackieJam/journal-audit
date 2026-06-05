"""AppTest 交互层测试的共享 fixture。

- isolated_app_home：把 HOME 指向临时目录，隔离 ~/.audit_tool 持久化，
  并清空 LLM 环境变量，避免测试触碰真实 Key / 钥匙串。
- sample_data：两年最小但列齐全的 SAP 序时账，足以驱动 analysis 各子页签渲染。
"""

from __future__ import annotations

import pandas as pd
import pytest

# 与 config/accounts 一致的最小科目集合：收入 / 成本 / 费用 / 应付 / 应收，
# 覆盖 income_cost、expense、working_capital 等子页签的取数路径。
_SAMPLE_ACCOUNTS = [
    ("6001", "主营业务收入", "H"),
    ("6401", "主营业务成本", "S"),
    ("6601", "销售费用", "S"),
    ("2202", "应付账款", "H"),
    ("1122", "应收账款", "S"),
]


def _make_year(year: int) -> pd.DataFrame:
    rows = []
    for month in range(1, 13):
        for idx, (code, name, dc) in enumerate(_SAMPLE_ACCOUNTS):
            amount = 100000.0 + month * 1000 + idx * 500
            rows.append(
                {
                    "凭证编号": f"{year}{month:02d}{idx:03d}",
                    "过账日期": pd.Timestamp(f"{year}-{month:02d}-15"),
                    "凭证类型": "SA",
                    "文本": f"{name}业务{month}月",
                    "总账科目": code,
                    "总账科目：长文本": name,
                    "借/贷标识": dc,
                    "凭证货币价值": amount,
                    "公司代码货币价值": amount,
                    "供应商编号": f"V{idx:03d}" if code == "2202" else "",
                    "供应商科目：名称 1": f"供应商{idx}" if code == "2202" else "",
                    "客户": f"C{idx:03d}" if code == "1122" else "",
                    "客户科目：姓名 1": f"客户{idx}" if code == "1122" else "",
                    "用户名": f"USER{idx % 2}",
                    "过账期间": month,
                    "会计年度": year,
                    "录入时间": pd.Timestamp(f"{year}-{month:02d}-16"),
                }
            )
    df = pd.DataFrame(rows)
    df["_year"] = year
    return df


@pytest.fixture
def isolated_app_home(tmp_path, monkeypatch):
    """隔离持久化根目录与 LLM 环境变量，确保 AppTest 不污染真实环境。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def sample_data() -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """返回 (df_unified, year_map)：两年、列齐全的最小序时账。"""
    year_map = {2022: _make_year(2022), 2023: _make_year(2023)}
    df_unified = pd.concat(year_map.values(), ignore_index=True)
    return df_unified, year_map
