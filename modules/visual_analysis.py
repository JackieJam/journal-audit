"""
Step 2 审计可视化数据准备。

这里保留行级序时账语义：收入/成本同时展示借贷方向，客户和供应商排名
按发生额主口径展示，净额分析留给后续抽样规则或专项分析。
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from config.accounts import (
    REVENUE_PREFIXES,
    COST_PREFIXES,
    AR_PREFIX,
    OTHER_RECEIVABLE_PREFIX,
    AP_PREFIX,
    AP_ACCRUAL_PREFIX,
    OTHER_PAYABLE_PREFIX,
    EXPENSE_PREFIXES,
    RD_EXPENSE_PREFIXES,
    FINANCIAL_EXPENSE_PREFIX,
    TAX_SURCHARGE_PREFIX,
    EXPENSE_CATEGORY_PATTERNS,
    DEFAULT_ADJUSTMENT_KEYWORDS,
)
from modules.data_columns import (
    add_analysis_columns,
    REQUIRED_ANALYSIS_COLUMNS,
    ensure_analysis_columns,
)


def _keyword_pattern(keywords: Iterable[str]) -> str:
    words = [str(k).strip() for k in keywords if str(k).strip()]
    return "|".join(re.escape(k) for k in words)


# Shared helpers and add_analysis_columns now live in modules.data_columns
# All functions below import from there.


def build_monthly_revenue_cost_view(df: pd.DataFrame) -> pd.DataFrame:
    """收入/成本按借贷方向展开：正常方向和冲减方向都保留。"""
    work = add_analysis_columns(df)
    return build_monthly_revenue_cost_view_from_work(work)


def build_income_cost_category_options_from_work(work: pd.DataFrame) -> list[str]:
    """收入成本月度图可选分类：总计 + 按损益科目名称拆出的业务分类。"""
    work = ensure_analysis_columns(work)
    categories = [
        c
        for c in work.loc[work["_acct4"].isin(REVENUE_PREFIXES + COST_PREFIXES), "_pnl_category"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
        if c
    ]
    order = {
        "主营业务-第三方": 10,
        "主营业务-内部关联方": 20,
        "主营业务-外部关联方": 30,
        "主营业务-其他": 40,
        "其他业务": 50,
        "其他业务-第三方": 60,
        "其他业务-内部关联方": 70,
        "其他业务-外部关联方": 80,
        "其他业务-其他": 90,
    }
    return ["总计"] + sorted(categories, key=lambda x: (order.get(x, 999), x))


def build_monthly_revenue_cost_view_from_work(
    work: pd.DataFrame,
    category: str | None = None,
) -> pd.DataFrame:
    """基于已补充分析列的 DataFrame 生成收入/成本月度视图。"""
    work = ensure_analysis_columns(work)
    if category and category != "总计":
        source = work[work["_pnl_category"] == category]
    else:
        source = work

    rows: list[dict] = []
    for month in range(1, 13):
        m = source[source["_month"] == month]
        revenue = m[m["_acct4"].isin(REVENUE_PREFIXES)]
        cost = m[m["_acct4"].isin(COST_PREFIXES)]

        income_h = float(revenue.loc[revenue["_dc"] == "H", "_amount_raw"].sum())
        income_s = float(revenue.loc[revenue["_dc"] == "S", "_amount_raw"].sum())
        cost_s = float(cost.loc[cost["_dc"] == "S", "_amount_raw"].sum())
        cost_h = float(cost.loc[cost["_dc"] == "H", "_amount_raw"].sum())
        net_revenue = -(income_h + income_s)
        net_cost_effect = -(cost_s + cost_h)

        rows.append({
            "月份": month,
            "收入H影响": income_h,
            "收入S影响": income_s,
            "成本S影响": cost_s,
            "成本H影响": cost_h,
            "净收入": net_revenue,
            "净成本影响": net_cost_effect,
            "毛利": net_revenue + net_cost_effect,
        })
    return pd.DataFrame(rows)


def build_customer_top10(df: pd.DataFrame, top_n: int | None = 10) -> pd.DataFrame:
    work = add_analysis_columns(df)
    return build_customer_top10_from_work(work, top_n=top_n)


def build_customer_top10_from_work(work: pd.DataFrame, top_n: int | None = 10) -> pd.DataFrame:
    work = ensure_analysis_columns(work)
    revenue = work[work["_acct4"].isin(REVENUE_PREFIXES) & (work["_customer_display"] != "未维护")]
    if revenue.empty:
        return pd.DataFrame(columns=["客户", "收入H影响", "收入S影响", "净收入", "应收S发生额", "占比"])

    rev_rows = []
    for customer, grp in revenue.groupby("_customer_display"):
        rev_rows.append({
            "客户": customer,
            "收入H影响": float(grp.loc[grp["_dc"] == "H", "_amount_raw"].sum()),
            "收入S影响": float(grp.loc[grp["_dc"] == "S", "_amount_raw"].sum()),
        })
    result = pd.DataFrame(rev_rows)

    ar = work[work["_acct4"] == AR_PREFIX]
    if not ar.empty:
        ar_debit = (
            ar[ar["_customer_display"] != "未维护"]
            .groupby("_customer_display")["_debit_amount"]
            .sum()
            .to_dict()
        )
        result["应收S发生额"] = result["客户"].map(ar_debit).fillna(0.0)
    else:
        result["应收S发生额"] = 0.0

    result["净收入"] = -(result["收入H影响"] + result["收入S影响"])
    total = result["净收入"].sum()
    result["占比"] = result["净收入"] / total if total else 0
    result = result.sort_values("净收入", ascending=False)
    if top_n:
        result = result.head(top_n)
    return result.reset_index(drop=True)


def _filter_category(source: pd.DataFrame, category: str | None) -> pd.DataFrame:
    source = ensure_analysis_columns(source)
    if category and category != "总计":
        return source[source["_pnl_category"] == category].copy()
    return source.copy()


def _revenue_rows(work: pd.DataFrame, category: str | None = None) -> pd.DataFrame:
    source = _filter_category(work, category)
    return source[source["_acct4"].isin(REVENUE_PREFIXES)].copy()


def _cost_rows(work: pd.DataFrame, category: str | None = None) -> pd.DataFrame:
    source = _filter_category(work, category)
    return source[source["_acct4"].isin(COST_PREFIXES)].copy()


def build_revenue_customer_material_summary_from_work(
    work: pd.DataFrame,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """收入按客户 + 物料组归集，作为项目口径第一版。"""
    revenue = _revenue_rows(work, category)
    revenue = revenue[revenue["_customer_display"] != "未维护"].copy()
    if revenue.empty:
        return pd.DataFrame(columns=["客户", "物料组", "收入H影响", "收入S影响", "净收入", "凭证数", "占比"])

    grouped = revenue.groupby(["_customer_display", "_material_group_display"], dropna=False).agg(
        收入H影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "H"].sum())),
        收入S影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "S"].sum())),
        凭证数=("凭证编号", "nunique"),
    ).reset_index()
    grouped = grouped.rename(columns={"_customer_display": "客户", "_material_group_display": "物料组"})
    grouped["净收入"] = -(grouped["收入H影响"] + grouped["收入S影响"])
    total = grouped["净收入"].sum()
    grouped["占比"] = grouped["净收入"] / total if total else 0
    grouped = grouped.sort_values("净收入", ascending=False).reset_index(drop=True)
    return grouped.head(top_n) if top_n else grouped


def build_revenue_customer_material_matrix_from_work(
    work: pd.DataFrame,
    category: str | None = None,
    top_customers: int = 12,
    top_material_groups: int = 8,
) -> pd.DataFrame:
    """客户 + 物料组净收入矩阵，金额单位仍为原币。"""
    summary = build_revenue_customer_material_summary_from_work(work, category)
    if summary.empty:
        return pd.DataFrame()

    top_customer_names = (
        summary.groupby("客户")["净收入"].sum().sort_values(ascending=False).head(top_customers).index
    )
    top_group_names = (
        summary.groupby("物料组")["净收入"].sum().sort_values(ascending=False).head(top_material_groups).index
    )
    source = summary[summary["客户"].isin(top_customer_names) & summary["物料组"].isin(top_group_names)]
    matrix = source.pivot_table(index="客户", columns="物料组", values="净收入", aggfunc="sum", fill_value=0)
    matrix["合计"] = matrix.sum(axis=1)
    matrix = matrix.sort_values("合计", ascending=False).reset_index()
    return matrix


def build_revenue_customer_monthly_focus_from_years(
    year_map: dict[int, pd.DataFrame],
    category: str | None = None,
    top_customers: int = 20,
) -> pd.DataFrame:
    """客户月度收入波动表：突出同比、环比和异常方向收入。"""
    frames: list[pd.DataFrame] = []
    for year, df_year in sorted(year_map.items()):
        work = add_analysis_columns(df_year)
        revenue = _revenue_rows(work, category)
        revenue = revenue[revenue["_customer_display"] != "未维护"].copy()
        if revenue.empty:
            continue
        grouped = revenue.groupby(["_customer_display", "_month"], dropna=False).agg(
            收入H影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "H"].sum())),
            收入S影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "S"].sum())),
            凭证数=("凭证编号", "nunique"),
        ).reset_index()
        grouped = grouped.rename(columns={"_customer_display": "客户", "_month": "月份"})
        grouped["年份"] = int(year)
        grouped["净收入"] = -(grouped["收入H影响"] + grouped["收入S影响"])
        frames.append(grouped)

    if not frames:
        return pd.DataFrame(columns=["年份", "月份", "客户", "净收入", "同比变动率", "环比变动率", "收入S影响", "凭证数", "关注点"])

    all_rows = pd.concat(frames, ignore_index=True)
    top_customer_names = (
        all_rows.groupby("客户")["净收入"].sum().sort_values(ascending=False).head(top_customers).index
    )
    all_rows = all_rows[all_rows["客户"].isin(top_customer_names)].copy()
    all_rows = all_rows.sort_values(["客户", "年份", "月份"])
    all_rows["环比基数"] = all_rows.groupby("客户")["净收入"].shift(1)
    all_rows["同比基数"] = all_rows.groupby(["客户", "月份"])["净收入"].shift(1)
    all_rows["环比变动率"] = _safe_ratio_delta(all_rows["净收入"], all_rows["环比基数"])
    all_rows["同比变动率"] = _safe_ratio_delta(all_rows["净收入"], all_rows["同比基数"])
    all_rows["关注点"] = [
        _revenue_focus_label(month, income_s, yoy, mom)
        for month, income_s, yoy, mom in zip(
            all_rows["月份"], all_rows["收入S影响"], all_rows["同比变动率"], all_rows["环比变动率"], strict=False
        )
    ]
    all_rows["_sort_abs"] = all_rows[["同比变动率", "环比变动率"]].abs().max(axis=1).fillna(0)
    return all_rows.sort_values(["_sort_abs", "收入S影响", "净收入"], ascending=[False, False, False]).drop(columns=["_sort_abs", "环比基数", "同比基数"])


def build_revenue_customer_monthly_focus_from_work_map(
    work_map: dict[int, pd.DataFrame],
    category: str | None = None,
    top_customers: int = 20,
) -> pd.DataFrame:
    """使用已补充分析列的 work_map 生成客户月度收入波动表，避免重复加工大表。"""
    frames: list[pd.DataFrame] = []
    for year, work in sorted(work_map.items()):
        revenue = _revenue_rows(work, category)
        revenue = revenue[revenue["_customer_display"] != "未维护"].copy()
        if revenue.empty:
            continue
        grouped = revenue.groupby(["_customer_display", "_month"], dropna=False).agg(
            收入H影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "H"].sum())),
            收入S影响=("_amount_raw", lambda x: float(x[revenue.loc[x.index, "_dc"] == "S"].sum())),
            凭证数=("凭证编号", "nunique"),
        ).reset_index()
        grouped = grouped.rename(columns={"_customer_display": "客户", "_month": "月份"})
        grouped["年份"] = int(year)
        grouped["净收入"] = -(grouped["收入H影响"] + grouped["收入S影响"])
        frames.append(grouped)

    if not frames:
        return pd.DataFrame(columns=["年份", "月份", "客户", "净收入", "同比变动率", "环比变动率", "收入S影响", "凭证数", "关注点"])

    all_rows = pd.concat(frames, ignore_index=True)
    top_customer_names = (
        all_rows.groupby("客户")["净收入"].sum().sort_values(ascending=False).head(top_customers).index
    )
    all_rows = all_rows[all_rows["客户"].isin(top_customer_names)].copy()
    all_rows = all_rows.sort_values(["客户", "年份", "月份"])
    all_rows["环比基数"] = all_rows.groupby("客户")["净收入"].shift(1)
    all_rows["同比基数"] = all_rows.groupby(["客户", "月份"])["净收入"].shift(1)
    all_rows["环比变动率"] = _safe_ratio_delta(all_rows["净收入"], all_rows["环比基数"])
    all_rows["同比变动率"] = _safe_ratio_delta(all_rows["净收入"], all_rows["同比基数"])
    all_rows["关注点"] = [
        _revenue_focus_label(month, income_s, yoy, mom)
        for month, income_s, yoy, mom in zip(
            all_rows["月份"], all_rows["收入S影响"], all_rows["同比变动率"], all_rows["环比变动率"], strict=False
        )
    ]
    all_rows["_sort_abs"] = all_rows[["同比变动率", "环比变动率"]].abs().max(axis=1).fillna(0)
    return all_rows.sort_values(["_sort_abs", "收入S影响", "净收入"], ascending=[False, False, False]).drop(columns=["_sort_abs", "环比基数", "同比基数"])


def _safe_ratio_delta(current: pd.Series, base: pd.Series) -> pd.Series:
    base_abs = base.abs()
    return ((current - base) / base_abs).where(base_abs > 0)


def _revenue_focus_label(month: int, income_s: float, yoy: float | None, mom: float | None) -> str:
    labels: list[str] = []
    if month == 12:
        labels.append("年末月份")
    if abs(float(income_s or 0)) > 0:
        labels.append("收入反向")
    if pd.notna(yoy) and abs(float(yoy)) >= 0.5:
        labels.append("同比波动")
    if pd.notna(mom) and abs(float(mom)) >= 0.5:
        labels.append("环比波动")
    return "、".join(labels) or "常规波动"


def build_cost_material_account_summary_from_work(
    work: pd.DataFrame,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """成本按物料组 + 成本科目归集。供应商字段覆盖不足时，此口径更稳。"""
    cost = _cost_rows(work, category)
    if cost.empty:
        return pd.DataFrame(columns=["物料组", "成本科目", "成本S影响", "成本H影响", "净成本", "凭证数", "占比"])

    grouped = cost.groupby(["_material_group_display", "_cost_account_display"], dropna=False).agg(
        成本S影响=("_amount_raw", lambda x: float(x[cost.loc[x.index, "_dc"] == "S"].sum())),
        成本H影响=("_amount_raw", lambda x: float(x[cost.loc[x.index, "_dc"] == "H"].sum())),
        凭证数=("凭证编号", "nunique"),
    ).reset_index()
    grouped = grouped.rename(columns={"_material_group_display": "物料组", "_cost_account_display": "成本科目"})
    grouped["净成本"] = grouped["成本S影响"] + grouped["成本H影响"]
    total = grouped["净成本"].abs().sum()
    grouped["占比"] = grouped["净成本"].abs() / total if total else 0
    grouped = grouped.sort_values("净成本", ascending=False).reset_index(drop=True)
    return grouped.head(top_n) if top_n else grouped


def build_supplier_top10(df: pd.DataFrame, top_n: int | None = 10) -> pd.DataFrame:
    """供应商 TopN，按 2202 应付账款贷方发生额排名。"""
    work = add_analysis_columns(df)
    return build_supplier_top10_from_work(work, top_n=top_n)


def build_supplier_top10_from_work(work: pd.DataFrame, top_n: int | None = 10) -> pd.DataFrame:
    """基于已补充分析列的 DataFrame 生成供应商 TopN。"""
    work = ensure_analysis_columns(work)
    ap = work[(work["_acct4"] == AP_PREFIX) & (work["_vendor_display"] != "未维护")]
    if ap.empty:
        return pd.DataFrame(columns=["供应商", "应付H发生额", "应付S发生额", "占比"])

    rows = []
    for vendor, grp in ap.groupby("_vendor_display"):
        rows.append({
            "供应商": vendor,
            "应付H发生额": float(-grp.loc[grp["_dc"] == "H", "_credit_amount"].sum()),
            "应付S发生额": float(grp.loc[grp["_dc"] == "S", "_debit_amount"].sum()),
        })
    result = pd.DataFrame(rows)
    total = result["应付H发生额"].sum()
    result["占比"] = result["应付H发生额"] / total if total else 0
    result = result.sort_values("应付H发生额", ascending=False)
    if top_n:
        result = result.head(top_n)
    return result.reset_index(drop=True)


def _entry_display_columns(detail: pd.DataFrame, amount_label: str) -> pd.DataFrame:
    columns = [
        "凭证编号",
        "过账日期",
        "行项目",
        "凭证类型",
        "总账科目",
        "_account_name",
        "借/贷标识",
        "公司代码货币价值",
        "凭证货币价值",
        amount_label,
        "用户名",
        "_customer_display",
        "_vendor_display",
        "_material_group_display",
        "_material_display",
        "_cost_center_display",
        "_header_text",
        "_line_text",
        "_reversal_text",
    ]
    columns = [c for c in columns if c in detail.columns]
    return detail[columns].rename(columns={
        "_account_name": "科目名称",
        "_customer_display": "客户",
        "_vendor_display": "供应商",
        "_material_group_display": "物料组",
        "_material_display": "物料",
        "_cost_center_display": "成本中心",
        "_header_text": "凭证抬头摘要",
        "_line_text": "摘要",
        "_reversal_text": "反记账/冲销标识",
    })


def build_customer_revenue_entry_top10(
    df: pd.DataFrame,
    customer: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """指定客户的收入科目分录，默认返回全量匹配行。"""
    work = add_analysis_columns(df)
    return build_customer_revenue_entry_top10_from_work(work, customer, top_n=top_n)


def build_customer_revenue_entry_top10_from_work(
    work: pd.DataFrame,
    customer: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """基于已补充分析列的 DataFrame 生成指定客户收入分录，默认全量。"""
    work = ensure_analysis_columns(work)
    detail = work[
        work["_acct4"].isin(REVENUE_PREFIXES)
        & (work["_customer_display"] == customer)
    ].copy()
    if detail.empty:
        return pd.DataFrame()

    detail["收入影响"] = detail["_amount_raw"]
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, "收入影响")


def build_revenue_focus_entries_from_work(
    work: pd.DataFrame,
    customer: str | None = None,
    material_group: str | None = None,
    month: int | None = None,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """按客户/物料组/月度回查收入全量分录。"""
    detail = _revenue_rows(work, category)
    if customer:
        detail = detail[detail["_customer_display"] == customer].copy()
    if material_group:
        detail = detail[detail["_material_group_display"] == material_group].copy()
    if month:
        detail = detail[detail["_month"] == int(month)].copy()
    if detail.empty:
        return pd.DataFrame()

    detail["收入影响"] = detail["_amount_raw"]
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, "收入影响")


def build_monthly_revenue_cost_entry_top10_from_work(
    work: pd.DataFrame,
    month: int,
    metric: str,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """净收入/净成本/月度毛利图点击后的分录，默认返回全量匹配行。"""
    work = ensure_analysis_columns(work)
    source = work
    if category and category != "总计":
        source = source[source["_pnl_category"] == category]

    if metric == "revenue":
        detail = source[
            source["_acct4"].isin(REVENUE_PREFIXES)
            & (source["_month"] == month)
        ].copy()
        amount_label = "收入影响"
        detail[amount_label] = detail["_amount_raw"]
    elif metric == "cost":
        detail = source[
            source["_acct4"].isin(COST_PREFIXES)
            & (source["_month"] == month)
        ].copy()
        amount_label = "成本发生额"
        detail[amount_label] = detail["_amount_raw"]
    elif metric == "gross":
        detail = source[
            source["_acct4"].isin(REVENUE_PREFIXES + COST_PREFIXES)
            & (source["_month"] == month)
        ].copy()
        amount_label = "毛利影响"
        detail[amount_label] = detail["_pnl_effect"]
    else:
        return pd.DataFrame()

    if detail.empty:
        return pd.DataFrame()

    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, amount_label)


def build_income_cost_abnormal_entry_top10_from_work(
    work: pd.DataFrame,
    month: int,
    direction: str,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """收入S、成本H异常方向分录，默认返回全量匹配行。"""
    work = ensure_analysis_columns(work)
    source = work
    if category and category != "总计":
        source = source[source["_pnl_category"] == category]

    if direction == "income_s":
        detail = source[
            source["_acct4"].isin(REVENUE_PREFIXES)
            & (source["_dc"] == "S")
            & (source["_month"] == month)
        ].copy()
        amount_label = "收入S影响"
    elif direction == "cost_h":
        detail = source[
            source["_acct4"].isin(COST_PREFIXES)
            & (source["_dc"] == "H")
            & (source["_month"] == month)
        ].copy()
        amount_label = "成本H影响"
    else:
        return pd.DataFrame()

    if detail.empty:
        return pd.DataFrame()

    detail[amount_label] = detail["_amount_raw"]
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, amount_label)


def _expense_category_masks(work: pd.DataFrame) -> dict[str, pd.Series]:
    work = ensure_analysis_columns(work)
    account_name = work.get("_account_name", pd.Series("", index=work.index)).astype(str)
    return {
        category: account_name.str.contains(pattern, na=False)
        for category, pattern in EXPENSE_CATEGORY_PATTERNS.items()
    }


def build_expense_entry_top10_from_work(
    work: pd.DataFrame,
    category: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """费用明细图/表点击后的分录，默认返回全量匹配行。"""
    work = ensure_analysis_columns(work)
    category = str(category).strip()
    if not category:
        return pd.DataFrame()

    if category == "研发费用":
        detail = work[work["_acct4"].isin(RD_EXPENSE_PREFIXES)].copy()
    elif category in ("财务费用", "财务费用(汇兑)"):
        detail = work[work["_acct4"] == FINANCIAL_EXPENSE_PREFIX].copy()
    elif category == "税金及附加":
        detail = work[work["_acct4"] == TAX_SURCHARGE_PREFIX].copy()
    else:
        expense_base = work[work["_acct4"].isin(EXPENSE_PREFIXES)].copy()
        masks = _expense_category_masks(expense_base)
        if category == "其他费用":
            matched = pd.Series(False, index=expense_base.index)
            for mask in masks.values():
                matched |= mask
            detail = expense_base.loc[~matched].copy()
        else:
            mask = masks.get(category)
            if mask is None:
                return pd.DataFrame()
            detail = expense_base.loc[mask].copy()

    if detail.empty:
        return pd.DataFrame()

    detail["费用发生额"] = detail["_amount_raw"]
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, "费用发生额")


def build_supplier_payable_entry_top10(
    df: pd.DataFrame,
    supplier: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """指定供应商的应付账款分录，默认返回全量匹配行。"""
    work = add_analysis_columns(df)
    return build_supplier_payable_entry_top10_from_work(work, supplier, top_n=top_n)


def build_supplier_payable_entry_top10_from_work(
    work: pd.DataFrame,
    supplier: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """基于已补充分析列的 DataFrame 生成指定供应商应付分录，默认全量。"""
    work = ensure_analysis_columns(work)
    detail = work[
        (work["_acct4"] == AP_PREFIX)
        & (work["_vendor_display"] == supplier)
    ].copy()
    if detail.empty:
        return pd.DataFrame()

    detail["应付发生额"] = detail["_amount_raw"].where(
        detail["_dc"] == "S",
        -detail["_amount_raw"],
    )
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, "应付发生额")


def build_cost_focus_entries_from_work(
    work: pd.DataFrame,
    material_group: str | None = None,
    cost_account: str | None = None,
    month: int | None = None,
    category: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """按物料组/成本科目/月度回查成本全量分录。"""
    detail = _cost_rows(work, category)
    if material_group:
        detail = detail[detail["_material_group_display"] == material_group].copy()
    if cost_account:
        detail = detail[detail["_cost_account_display"] == cost_account].copy()
    if month:
        detail = detail[detail["_month"] == int(month)].copy()
    if detail.empty:
        return pd.DataFrame()

    detail["成本发生额"] = detail["_amount_raw"]
    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, "成本发生额")


def _ap_accrual_rows(work: pd.DataFrame) -> pd.DataFrame:
    work = ensure_analysis_columns(work)
    account_name = work.get("_account_name", pd.Series("", index=work.index)).astype(str)
    return work[
        work["_acct"].str.startswith(AP_ACCRUAL_PREFIX)
        | (work["_acct4"].eq(AP_PREFIX) & account_name.str.contains("暂估|GR/IR", na=False))
    ]


def build_ap_accrual_monthly_view_from_work(work: pd.DataFrame) -> pd.DataFrame:
    """应付账款暂估月度借贷方向视图。"""
    accrual = _ap_accrual_rows(work)
    rows: list[dict] = []
    for month in range(1, 13):
        m = accrual[accrual["_month"] == month]
        credit_increase = float(-m.loc[m["_dc"] == "H", "_credit_amount"].sum())
        debit_decrease = float(m.loc[m["_dc"] == "S", "_debit_amount"].sum())
        rows.append({
            "月份": month,
            "暂估贷方增加": credit_increase,
            "暂估借方减少": debit_decrease,
            "暂估净额": credit_increase - debit_decrease,
        })
    return pd.DataFrame(rows)


def _other_receivable_rows(work: pd.DataFrame) -> pd.DataFrame:
    work = ensure_analysis_columns(work)
    account_name = work.get("_account_name", pd.Series("", index=work.index)).astype(str)
    return work[
        work["_acct4"].eq(OTHER_RECEIVABLE_PREFIX)
        | account_name.str.contains("其他应收", na=False)
    ]


def build_other_receivable_monthly_view_from_work(work: pd.DataFrame) -> pd.DataFrame:
    """其他应收款月度 S/H 原始符号金额和净额视图。"""
    other_receivable = _other_receivable_rows(work)
    rows: list[dict] = []
    for month in range(1, 13):
        m = other_receivable[other_receivable["_month"] == month]
        debit_s = float(m.loc[m["_dc"] == "S", "_amount_raw"].sum())
        credit_h = float((-m.loc[m["_dc"] == "H", "_amount_raw"]).sum())
        rows.append({
            "月份": month,
            "其他应收S发生额": debit_s,
            "其他应收H发生额": credit_h,
            "其他应收净额": debit_s - credit_h,
        })
    return pd.DataFrame(rows)


def build_other_receivable_entry_top10_from_work(
    work: pd.DataFrame,
    month: int,
    direction: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """其他应收款月度 S/H/净额点击后的分录，默认返回全量匹配行。"""
    detail = _other_receivable_rows(work)
    detail = detail[detail["_month"] == month].copy()

    if direction == "debit":
        detail = detail[detail["_dc"] == "S"].copy()
        amount_label = "其他应收S发生额"
        detail[amount_label] = detail["_amount_raw"]
    elif direction == "credit":
        detail = detail[detail["_dc"] == "H"].copy()
        amount_label = "其他应收H发生额"
        detail[amount_label] = -detail["_amount_raw"]
    elif direction == "net":
        amount_label = "其他应收净额影响"
        detail[amount_label] = detail["_amount_raw"]
    else:
        return pd.DataFrame()

    if detail.empty:
        return pd.DataFrame()

    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, amount_label)


def _other_payable_rows(work: pd.DataFrame) -> pd.DataFrame:
    work = ensure_analysis_columns(work)
    account_name = work.get("_account_name", pd.Series("", index=work.index)).astype(str)
    return work[
        work["_acct4"].eq(OTHER_PAYABLE_PREFIX)
        | account_name.str.contains("其他应付", na=False)
    ]


def build_other_payable_monthly_view_from_work(work: pd.DataFrame) -> pd.DataFrame:
    """其他应付款月度预提、核销和净值视图，保留反向金额符号。"""
    other_payable = _other_payable_rows(work)
    rows: list[dict] = []
    for month in range(1, 13):
        m = other_payable[other_payable["_month"] == month]
        accrual_h = float((-m.loc[m["_dc"] == "H", "_amount_raw"]).sum())
        writeoff_s = float(m.loc[m["_dc"] == "S", "_amount_raw"].sum())
        rows.append({
            "月份": month,
            "其他应付预提H": accrual_h,
            "其他应付核销S": writeoff_s,
            "其他应付净值": accrual_h - writeoff_s,
        })
    return pd.DataFrame(rows)


def build_other_payable_entry_top10_from_work(
    work: pd.DataFrame,
    month: int,
    direction: str,
    top_n: int | None = None,
) -> pd.DataFrame:
    """其他应付款月度预提/核销/净值点击后的分录，默认返回全量匹配行。"""
    detail = _other_payable_rows(work)
    detail = detail[detail["_month"] == month].copy()

    if direction == "accrual":
        detail = detail[detail["_dc"] == "H"].copy()
        amount_label = "其他应付预提H"
        detail[amount_label] = -detail["_amount_raw"]
    elif direction == "writeoff":
        detail = detail[detail["_dc"] == "S"].copy()
        amount_label = "其他应付核销S"
        detail[amount_label] = detail["_amount_raw"]
    elif direction == "net":
        amount_label = "其他应付净值影响"
        detail[amount_label] = -detail["_amount_raw"]
    else:
        return pd.DataFrame()

    if detail.empty:
        return pd.DataFrame()

    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, amount_label)


def build_ap_accrual_supplier_comparison_from_work(
    work: pd.DataFrame,
    month: int,
    sort_by: str = "net",
    top_n: int = 10,
) -> pd.DataFrame:
    """指定月份暂估供应商贷方增加、借方减少和净额对比。"""
    accrual = _ap_accrual_rows(work)
    rows = accrual[(accrual["_month"] == month) & (accrual["_vendor_display"] != "未维护")].copy()
    if rows.empty:
        return pd.DataFrame(columns=["供应商", "暂估贷方增加", "暂估借方减少", "暂估净额", "贷方占比", "借方占比", "净额占比"])

    grouped_rows = []
    for vendor, grp in rows.groupby("_vendor_display"):
        credit = float(-grp.loc[grp["_dc"] == "H", "_credit_amount"].sum())
        debit = float(grp.loc[grp["_dc"] == "S", "_debit_amount"].sum())
        grouped_rows.append({
            "供应商": vendor,
            "暂估贷方增加": credit,
            "暂估借方减少": debit,
            "暂估净额": credit - debit,
        })

    result = pd.DataFrame(grouped_rows)
    credit_total = result["暂估贷方增加"].sum()
    debit_total = result["暂估借方减少"].sum()
    net_total = result["暂估净额"].sum()
    result["贷方占比"] = result["暂估贷方增加"] / credit_total if credit_total else 0
    result["借方占比"] = result["暂估借方减少"] / debit_total if debit_total else 0
    result["净额占比"] = result["暂估净额"] / net_total if net_total else 0

    sort_map = {
        "credit": "暂估贷方增加",
        "debit": "暂估借方减少",
        "net": "暂估净额",
    }
    sort_col = sort_map.get(sort_by, "暂估净额")
    result["_sort"] = result[sort_col].abs() if sort_col == "暂估净额" else result[sort_col]
    return result.sort_values("_sort", ascending=False).drop(columns=["_sort"]).head(top_n).reset_index(drop=True)


def build_ap_accrual_entry_top10_from_work(
    work: pd.DataFrame,
    month: int,
    direction: str,
    supplier: str | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """应付账款暂估月份/供应商点击后的分录，默认返回全量匹配行。"""
    detail = _ap_accrual_rows(work)
    detail = detail[detail["_month"] == month].copy()
    if supplier:
        detail = detail[detail["_vendor_display"] == supplier].copy()

    if direction == "credit":
        detail = detail[detail["_dc"] == "H"].copy()
        amount_label = "暂估贷方增加"
        detail[amount_label] = -detail["_credit_amount"]
    elif direction == "debit":
        detail = detail[detail["_dc"] == "S"].copy()
        amount_label = "暂估借方减少"
        detail[amount_label] = detail["_debit_amount"]
    elif direction == "net":
        amount_label = "暂估净额影响"
        detail[amount_label] = -detail["_amount_raw"]
    else:
        return pd.DataFrame()

    if detail.empty:
        return pd.DataFrame()

    detail = detail.sort_values("_amount_abs", ascending=False)
    if top_n:
        detail = detail.head(top_n)
    return _entry_display_columns(detail, amount_label)


def build_ap_accrual_supplier_share_from_work(
    work: pd.DataFrame,
    month: int,
    direction: str,
    top_n: int = 10,
) -> pd.DataFrame:
    """指定月份暂估借贷方向/净额对应供应商占比。"""
    accrual = _ap_accrual_rows(work)
    rows = accrual[(accrual["_month"] == month) & (accrual["_vendor_display"] != "未维护")].copy()
    if rows.empty:
        return pd.DataFrame(columns=["供应商", "金额", "占比"])

    if direction == "credit":
        rows = rows[rows["_dc"] == "H"].copy()
        rows["金额"] = -rows["_credit_amount"]
    elif direction == "debit":
        rows = rows[rows["_dc"] == "S"].copy()
        rows["金额"] = rows["_debit_amount"]
    else:
        rows["金额"] = -rows["_amount_raw"]

    if rows.empty:
        return pd.DataFrame(columns=["供应商", "金额", "占比"])

    result = rows.groupby("_vendor_display", as_index=False)["金额"].sum()
    result = result.rename(columns={"_vendor_display": "供应商"})
    total = result["金额"].sum()
    result["占比"] = result["金额"] / total if total else 0
    sort_col = result["金额"].abs() if direction == "net" else result["金额"]
    result = result.assign(_sort=sort_col).sort_values("_sort", ascending=False)
    return result.drop(columns=["_sort"]).head(top_n).reset_index(drop=True)


def build_adjustment_views(
    df: pd.DataFrame,
    keywords: Iterable[str] = DEFAULT_ADJUSTMENT_KEYWORDS,
    max_vouchers: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回调账/冲销凭证摘要和对应全分录明细。"""
    work = add_analysis_columns(df)
    return build_adjustment_views_from_work(work, keywords=keywords, max_vouchers=max_vouchers)


def build_adjustment_views_from_work(
    work: pd.DataFrame,
    keywords: Iterable[str] = DEFAULT_ADJUSTMENT_KEYWORDS,
    max_vouchers: int = 300,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """基于已补充分析列的 DataFrame 生成调账/冲销摘要和明细。"""
    work = ensure_analysis_columns(work)
    pattern = _keyword_pattern(keywords)
    if not pattern:
        return pd.DataFrame(), pd.DataFrame()

    text_hit = work["_combined_text"].str.contains(pattern, na=False, regex=True)
    reversal_hit = work["_reversal_text"].str.strip().astype(bool)
    hit_rows = work[text_hit | reversal_hit].copy()
    if hit_rows.empty:
        return pd.DataFrame(), pd.DataFrame()

    hit_keys = hit_rows[["凭证编号", "过账日期"]].drop_duplicates()
    detail = work.merge(hit_keys, on=["凭证编号", "过账日期"], how="inner")

    def _matched_words(s: pd.Series) -> str:
        found: list[str] = []
        for text in s.dropna().astype(str):
            for kw in keywords:
                if kw and kw in text and kw not in found:
                    found.append(str(kw))
        return "、".join(found[:8])

    summary = detail.groupby(["凭证编号", "过账日期"]).agg(
        行数=("凭证编号", "size"),
        凭证类型=("凭证类型", lambda x: "、".join(sorted({str(v) for v in x.dropna()}))),
        命中关键词=("_combined_text", _matched_words),
        反记账标识=("_reversal_text", lambda x: "、".join(sorted({v for v in x.astype(str) if v.strip() and v != "nan"}))),
        借方金额=("_debit_abs", "sum"),
        贷方金额=("_credit_abs", "sum"),
        最大行金额=("_amount_abs", "max"),
        用户名=("用户名", lambda x: "、".join(sorted({str(v) for v in x.dropna()}))[:120]),
        凭证抬头摘要=("_header_text", "first"),
        摘要=("_line_text", lambda x: " | ".join(dict.fromkeys([str(v) for v in x.dropna() if str(v).strip()]))[:240]),
    ).reset_index()
    summary = summary.sort_values(["过账日期", "最大行金额"], ascending=[False, False]).head(max_vouchers)

    detail_cols = [
        "凭证编号",
        "过账日期",
        "行项目",
        "凭证类型",
        "总账科目",
        "_account_name",
        "借/贷标识",
        "公司代码货币价值",
        "凭证货币价值",
        "用户名",
        "_customer_display",
        "_vendor_display",
        "_header_text",
        "_line_text",
        "_reversal_text",
    ]
    detail_cols = [c for c in detail_cols if c in detail.columns]
    detail = detail[detail_cols].rename(columns={
        "_account_name": "科目名称",
        "_customer_display": "客户",
        "_vendor_display": "供应商",
        "_header_text": "凭证抬头摘要",
        "_line_text": "摘要",
        "_reversal_text": "反记账/冲销标识",
    })
    detail = detail.sort_values(["过账日期", "凭证编号", "行项目" if "行项目" in detail.columns else "总账科目"])

    return summary, detail
