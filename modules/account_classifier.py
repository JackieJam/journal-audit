"""
基于科目名称的自动分类器。

每家被审单位科目体系不同，但「主营业务收入」「制造费用-人工」「应付账款-暂估」
这类科目名称的语义是稳定的。比起让用户维护一组组前缀清单，直接按
科目名称做关键词匹配更直观。

匹配规则：
- 单向、按优先级顺序，先命中先终止；
- 名称为空 / 不命中任何规则 → "未分类"，相关分析自动跳过；
- 用户可针对个别科目编号在 UI 中手动覆盖（per-project，跟随项目状态保存）。

不依赖 streamlit；脱离 UI 也能调用 auto_classify 和 classify_dataframe。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


# ── 类别常量 ────────────────────────────────────────────────
# 字符串值与 UI 下拉、各分析模块比较保持一致。

CAT_REVENUE = "收入"
CAT_COST = "成本"
CAT_EXPENSE = "费用"
CAT_RD_EXPENSE = "研发费用"
CAT_FINANCIAL_EXPENSE = "财务费用"
CAT_TAX_SURCHARGE = "税金及附加"
CAT_AR = "应收"
CAT_OTHER_RECEIVABLE = "其他应收"
CAT_AP = "应付"
CAT_AP_ACCRUAL = "应付暂估"
CAT_OTHER_PAYABLE = "其他应付"
CAT_UNCATEGORIZED = "未分类"

ALL_CATEGORIES: tuple[str, ...] = (
    CAT_REVENUE,
    CAT_COST,
    CAT_EXPENSE,
    CAT_RD_EXPENSE,
    CAT_FINANCIAL_EXPENSE,
    CAT_TAX_SURCHARGE,
    CAT_AR,
    CAT_OTHER_RECEIVABLE,
    CAT_AP,
    CAT_AP_ACCRUAL,
    CAT_OTHER_PAYABLE,
    CAT_UNCATEGORIZED,
)


# ── 优先级匹配规则 ──────────────────────────────────────────
# 每条规则：(类别, 必含关键词列表)。
# 单向匹配——按本表顺序，第一个命中的关键词决定类别。
# 「应付暂估」放最前避免被「应付」吞掉；「其他应收/应付」放在「应收/应付」之前。

@dataclass(frozen=True)
class _Rule:
    category: str
    keywords: tuple[str, ...]


_PRIORITY_RULES: tuple[_Rule, ...] = (
    _Rule(CAT_AP_ACCRUAL, ("暂估", "GR/IR", "GRIR")),
    _Rule(CAT_OTHER_RECEIVABLE, ("其他应收",)),
    _Rule(CAT_OTHER_PAYABLE, ("其他应付",)),
    _Rule(CAT_AR, ("应收",)),
    _Rule(CAT_AP, ("应付",)),
    _Rule(CAT_TAX_SURCHARGE, ("税金及附加",)),
    _Rule(CAT_RD_EXPENSE, ("研发",)),
    _Rule(CAT_FINANCIAL_EXPENSE, ("财务费用", "汇兑损益")),
    _Rule(CAT_REVENUE, ("收入",)),
    _Rule(CAT_COST, ("成本",)),
    _Rule(CAT_EXPENSE, ("费用",)),
)


# ─────────────────────────────────────────────
# 公开 API
# ─────────────────────────────────────────────


def auto_classify(account_name: str | None) -> str:
    """按科目名称自动分类。

    - 名称为空、None、NaN → "未分类"
    - 不命中任一关键词 → "未分类"
    """
    if account_name is None:
        return CAT_UNCATEGORIZED
    name = str(account_name).strip()
    if not name or name.lower() == "nan":
        return CAT_UNCATEGORIZED
    for rule in _PRIORITY_RULES:
        for keyword in rule.keywords:
            if keyword in name:
                return rule.category
    return CAT_UNCATEGORIZED


def classify_dataframe(
    df: pd.DataFrame,
    *,
    overrides: dict[str, str] | None = None,
) -> pd.DataFrame:
    """为 DataFrame 添加 _acct_category 列，不修改原 df。

    Args:
        df: 必须含 `总账科目` 列；若有 `总账科目：长文本` 用作分类依据。
        overrides: {科目编号: 类别}，用户的手动覆盖。优先于自动分类。

    Returns:
        新的 DataFrame（拷贝），多了 `_acct_category` 列。
    """
    out = df.copy()
    overrides = overrides or {}

    name_col = _resolve_name_column(out)
    if name_col is None:
        names = pd.Series("", index=out.index)
    else:
        names = out[name_col].fillna("").astype(str)

    # 自动分类
    auto = names.map(auto_classify)

    # 应用用户覆盖（按完整科目编号字符串）
    if overrides:
        acct_str = out["总账科目"].astype(str).str.strip()
        # 用户也可能填了 nan 之类的脏数据，先过滤
        valid_overrides = {
            str(k).strip(): str(v).strip()
            for k, v in overrides.items()
            if str(k).strip() and str(v).strip() in ALL_CATEGORIES
        }
        if valid_overrides:
            mapped = acct_str.map(valid_overrides)
            auto = mapped.where(mapped.notna(), auto)

    out["_acct_category"] = auto
    return out


def build_account_overview(
    df: pd.DataFrame,
    *,
    overrides: dict[str, str] | None = None,
) -> pd.DataFrame:
    """生成"科目 -> 行数 / 金额 / 自动分类 / 人工调整" 的总览表，给 UI 用。"""
    if df is None or df.empty or "总账科目" not in df.columns:
        return pd.DataFrame()

    name_col = _resolve_name_column(df)
    amount_col = "公司代码货币价值" if "公司代码货币价值" in df.columns else "凭证货币价值"

    work = df.copy()
    work["_code"] = work["总账科目"].astype(str).str.strip()
    work["_name"] = work[name_col].fillna("").astype(str) if name_col else ""
    work["_amt"] = pd.to_numeric(work.get(amount_col, 0), errors="coerce").fillna(0).abs()

    name_per_code = (
        work.groupby("_code")["_name"]
        .agg(lambda s: next((n for n in s if n), ""))
    )

    grouped = (
        work.groupby("_code")
        .agg(行数=("_code", "count"), 金额=("_amt", "sum"))
        .reset_index()
        .rename(columns={"_code": "科目编号"})
    )
    grouped["科目名称"] = grouped["科目编号"].map(name_per_code).fillna("")
    grouped["自动分类"] = grouped["科目名称"].map(auto_classify)

    overrides = overrides or {}
    grouped["人工分类"] = grouped["科目编号"].map(overrides).fillna("")
    grouped["生效分类"] = grouped["人工分类"].where(
        grouped["人工分类"].astype(bool), grouped["自动分类"]
    )

    grouped = grouped.sort_values("金额", ascending=False).reset_index(drop=True)
    return grouped[["科目编号", "科目名称", "行数", "金额", "自动分类", "人工分类", "生效分类"]]


def _resolve_name_column(df: pd.DataFrame) -> str | None:
    for col in ("总账科目：长文本", "总账科目：短文本"):
        if col in df.columns:
            return col
    return None
