"""
跨年交叉稽核模块：对多年数据执行七类跨年异常检测。
每类返回 CrossYearFinding 列表，供 LLM 规则校准和可视化使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from config.accounts import AUTO_VOUCHER_TYPES


@dataclass
class CrossYearFinding:
    category: str          # 异常类型
    description: str       # 具体描述
    years_involved: list[int]
    voucher_ids: list[str]
    amount: float
    severity: str          # "高" | "中" | "低"
    evidence: dict[str, Any] = field(default_factory=dict)


def run_cross_year_analysis(
    year_map: dict[int, pd.DataFrame],
) -> list[CrossYearFinding]:
    """执行全部跨年稽核，返回所有发现。"""
    if len(year_map) < 2:
        return []

    findings: list[CrossYearFinding] = []
    findings.extend(_accrual_reversal_pairs(year_map))
    findings.extend(_revenue_timing_drift(year_map))
    findings.extend(_yearend_balance_buildup(year_map))
    findings.extend(_counterparty_circular_flow(year_map))
    findings.extend(_expense_category_spike(year_map))
    findings.extend(_manual_entry_trend(year_map))
    findings.extend(_account_relationship_drift(year_map))
    return findings


# ─────────────────────────────────────────────
# 1. 预提-冲回跨年配对
# ─────────────────────────────────────────────

def _accrual_reversal_pairs(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    years = sorted(year_map.keys())

    for i in range(len(years) - 1):
        yr_n, yr_n1 = years[i], years[i + 1]
        df_n = year_map[yr_n]
        df_n1 = year_map[yr_n1]

        # 年末预提：12月，文本含"预提"，非冲销
        dec_accruals = df_n[
            (df_n["过账日期"].dt.month == 12)
            & df_n["文本"].str.contains("预提", na=False)
            & ~df_n["文本"].str.contains("冲销|冲回|红字", na=False)
        ].copy()

        if dec_accruals.empty:
            continue

        # 次年 Q1 冲回：1-3月，文本含"冲销"或"冲回"
        q1_reversals = df_n1[
            (df_n1["过账日期"].dt.month <= 3)
            & df_n1["文本"].str.contains("冲销|冲回|红字", na=False)
        ].copy()

        total_accrual = dec_accruals["凭证货币价值"].abs().sum()
        total_reversal = q1_reversals["凭证货币价值"].abs().sum() if not q1_reversals.empty else 0.0

        if total_accrual < 10_000:
            continue

        coverage = total_reversal / total_accrual if total_accrual > 0 else 0
        unmatched = total_accrual - total_reversal

        # 悬空预提（冲回不足80%）
        if coverage < 0.80:
            findings.append(CrossYearFinding(
                category="预提冲回配对",
                description=f"{yr_n}年末预提{total_accrual:,.0f}，{yr_n1}年Q1仅冲回{total_reversal:,.0f}（{coverage:.0%}），悬空{unmatched:,.0f}",
                years_involved=[yr_n, yr_n1],
                voucher_ids=dec_accruals["凭证编号"].unique().tolist(),
                amount=unmatched,
                severity="高" if unmatched > 1_000_000 else "中",
                evidence={
                    "accrual_amount": round(total_accrual, 2),
                    "reversal_amount": round(total_reversal, 2),
                    "coverage_ratio": round(coverage, 4),
                },
            ))
        # 金额不等的冲回（调节利润）
        elif abs(coverage - 1.0) > 0.05:
            findings.append(CrossYearFinding(
                category="预提冲回金额不符",
                description=f"{yr_n}年末预提与{yr_n1}年Q1冲回金额差异{abs(coverage-1):.0%}，疑似调节跨年损益",
                years_involved=[yr_n, yr_n1],
                voucher_ids=dec_accruals["凭证编号"].unique().tolist(),
                amount=abs(total_accrual - total_reversal),
                severity="中",
                evidence={"coverage_ratio": round(coverage, 4)},
            ))

    return findings


# ─────────────────────────────────────────────
# 2. 收入确认时点漂移
# ─────────────────────────────────────────────

def _revenue_timing_drift(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    income_prefixes = ["6001", "6051"]
    years = sorted(year_map.keys())

    year_dec_ratio: dict[int, float] = {}
    for yr, df in year_map.items():
        rev = df[df["总账科目"].astype(str).str[:4].isin(income_prefixes)]
        if rev.empty:
            continue
        rev = rev.copy()
        rev["_month"] = rev["过账日期"].dt.month
        monthly = rev.groupby("_month")["凭证货币价值"].apply(lambda x: x.abs().sum())
        if len(monthly) < 2:
            continue
        dec = float(monthly.get(12, 0))
        avg_other = float(monthly[monthly.index != 12].mean())
        year_dec_ratio[yr] = dec / avg_other if avg_other > 0 else 0

    for i in range(len(years) - 1):
        yr_n, yr_n1 = years[i], years[i + 1]
        ratio_n = year_dec_ratio.get(yr_n, 0)
        ratio_n1 = year_dec_ratio.get(yr_n1, 0)

        # 某年12月收入异常高，且次年1月出现大额红字
        if ratio_n > 1.8:
            df_n1 = year_map[yr_n1]
            jan_red = df_n1[
                (df_n1["过账日期"].dt.month == 1)
                & df_n1["总账科目"].astype(str).str[:4].isin(income_prefixes)
                & (df_n1["凭证货币价值"] < 0)
            ]
            if not jan_red.empty:
                red_amt = jan_red["凭证货币价值"].abs().sum()
                findings.append(CrossYearFinding(
                    category="收入跨年确认",
                    description=f"{yr_n}年12月收入是前11月均值的{ratio_n:.1f}倍，且{yr_n1}年1月出现红字冲回{red_amt:,.0f}，疑似提前确认收入",
                    years_involved=[yr_n, yr_n1],
                    voucher_ids=jan_red["凭证编号"].unique().tolist(),
                    amount=red_amt,
                    severity="高",
                    evidence={"dec_ratio": round(ratio_n, 2), "jan_reversal": round(red_amt, 2)},
                ))

    return findings


# ─────────────────────────────────────────────
# 3. 期末余额异常堆积（应收/预付/其他应收）
# ─────────────────────────────────────────────

def _yearend_balance_buildup(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    watch_prefixes = {
        "应收账款": "1122",
        "预付款项": "1221",
        "其他应收款": "1123",
    }
    years = sorted(year_map.keys())

    for acct_name, prefix in watch_prefixes.items():
        year_end_balances: dict[int, float] = {}
        year_avg_balances: dict[int, float] = {}

        for yr, df in year_map.items():
            acct_rows = df[df["总账科目"].astype(str).str[:4] == prefix]
            if acct_rows.empty:
                continue
            dec_rows = acct_rows[acct_rows["过账日期"].dt.month == 12]
            year_end_balances[yr] = float(dec_rows["凭证货币价值"].abs().sum())
            year_avg_balances[yr] = float(acct_rows["凭证货币价值"].abs().sum() / 12)

        if len(year_end_balances) < 2:
            continue

        # 检测余额逐年递增
        bal_list = [(yr, year_end_balances[yr]) for yr in sorted(year_end_balances.keys())]
        if all(bal_list[i][1] < bal_list[i+1][1] for i in range(len(bal_list)-1)):
            last_yr, last_bal = bal_list[-1]
            first_yr, first_bal = bal_list[0]
            if first_bal > 0 and last_bal / first_bal > 1.5:
                findings.append(CrossYearFinding(
                    category="期末余额持续累积",
                    description=f"{acct_name}（{prefix}）年末余额从{first_yr}到{last_yr}持续增长，累计增幅{last_bal/first_bal:.1f}x，疑似虚增资产或收入造假积累",
                    years_involved=list(year_end_balances.keys()),
                    voucher_ids=[],
                    amount=last_bal - first_bal,
                    severity="中",
                    evidence={yr: round(b, 2) for yr, b in bal_list},
                ))

    return findings


# ─────────────────────────────────────────────
# 4. 对手方跨年资金循环
# ─────────────────────────────────────────────

def _counterparty_circular_flow(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    years = sorted(year_map.keys())

    for i in range(len(years) - 1):
        yr_n, yr_n1 = years[i], years[i + 1]
        df_n = year_map[yr_n]
        df_n1 = year_map[yr_n1]

        # Year N 年末大额支出
        dec_large_out = df_n[
            (df_n["过账日期"].dt.month == 12)
            & (df_n["凭证货币价值"] < -500_000)
            & df_n["供应商编号"].notna()
        ]

        if dec_large_out.empty:
            continue

        # Year N+1 年初同供应商大额收入（反向）
        q1_large_in = df_n1[
            (df_n1["过账日期"].dt.month <= 3)
            & (df_n1["凭证货币价值"] > 500_000)
            & df_n1["供应商编号"].notna()
        ]

        if q1_large_in.empty:
            continue

        overlap_vendors = set(dec_large_out["供应商编号"]) & set(q1_large_in["供应商编号"])
        for vendor in overlap_vendors:
            out_amt = dec_large_out[dec_large_out["供应商编号"] == vendor]["凭证货币价值"].abs().sum()
            in_amt = q1_large_in[q1_large_in["供应商编号"] == vendor]["凭证货币价值"].abs().sum()
            ratio = min(out_amt, in_amt) / max(out_amt, in_amt) if max(out_amt, in_amt) > 0 else 0

            if ratio > 0.7:
                vids = (
                    dec_large_out[dec_large_out["供应商编号"] == vendor]["凭证编号"].tolist()
                    + q1_large_in[q1_large_in["供应商编号"] == vendor]["凭证编号"].tolist()
                )
                vendor_name = dec_large_out[dec_large_out["供应商编号"] == vendor]["供应商科目：名称 1"].iloc[0] if "供应商科目：名称 1" in dec_large_out.columns else vendor
                findings.append(CrossYearFinding(
                    category="对手方跨年资金循环",
                    description=f"供应商{vendor_name}：{yr_n}年末付出{out_amt:,.0f}，{yr_n1}年Q1收回{in_amt:,.0f}（匹配度{ratio:.0%}），疑似资金空转",
                    years_involved=[yr_n, yr_n1],
                    voucher_ids=list(set(vids)),
                    amount=(out_amt + in_amt) / 2,
                    severity="高",
                    evidence={"vendor": str(vendor), "out_amount": round(out_amt, 2), "in_amount": round(in_amt, 2)},
                ))

    return findings


# ─────────────────────────────────────────────
# 5. 费用科目年度突变
# ─────────────────────────────────────────────

def _expense_category_spike(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    years = sorted(year_map.keys())
    if len(years) < 2:
        return findings

    # 关注费用类科目（6开头，非收入）
    expense_prefixes = ["6601", "6602", "6603", "6711", "6801"]

    for prefix in expense_prefixes:
        year_totals: dict[int, float] = {}
        for yr, df in year_map.items():
            rows = df[df["总账科目"].astype(str).str[:4] == prefix]
            year_totals[yr] = float(rows["凭证货币价值"].abs().sum())

        if len(year_totals) < 2 or all(v == 0 for v in year_totals.values()):
            continue

        totals = [(yr, year_totals[yr]) for yr in sorted(year_totals.keys())]
        for i in range(1, len(totals)):
            prev_yr, prev_amt = totals[i - 1]
            curr_yr, curr_amt = totals[i]
            if prev_amt > 0 and curr_amt / prev_amt > 2.5:
                findings.append(CrossYearFinding(
                    category="费用科目年度突变",
                    description=f"科目{prefix}：{curr_yr}年发生额{curr_amt:,.0f}，是{prev_yr}年{prev_amt:,.0f}的{curr_amt/prev_amt:.1f}倍，异常放量",
                    years_involved=[prev_yr, curr_yr],
                    voucher_ids=[],
                    amount=curr_amt - prev_amt,
                    severity="中",
                    evidence={"account_prefix": prefix, "prev_amount": round(prev_amt, 2), "curr_amount": round(curr_amt, 2)},
                ))

    return findings


# ─────────────────────────────────────────────
# 6. 手工凭证占比趋势
# ─────────────────────────────────────────────

def _manual_entry_trend(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    findings = []
    years = sorted(year_map.keys())

    year_ratios: dict[int, float] = {}
    for yr, df in year_map.items():
        if "凭证类型" not in df.columns or df.empty:
            continue
        manual = (~df["凭证类型"].isin(AUTO_VOUCHER_TYPES)).sum()
        year_ratios[yr] = round(manual / len(df), 4)

    if len(year_ratios) < 2:
        return findings

    ratios = [(yr, year_ratios[yr]) for yr in sorted(year_ratios.keys())]
    # 逐年上升且末年比首年高 15ppt
    if all(ratios[i][1] <= ratios[i+1][1] for i in range(len(ratios)-1)):
        delta = ratios[-1][1] - ratios[0][1]
        if delta > 0.15:
            findings.append(CrossYearFinding(
                category="手工凭证占比持续上升",
                description=f"手工凭证占比从{ratios[0][0]}年的{ratios[0][1]:.1%}逐年上升至{ratios[-1][0]}年的{ratios[-1][1]:.1%}，内控可能在弱化",
                years_involved=[r[0] for r in ratios],
                voucher_ids=[],
                amount=0,
                severity="中",
                evidence={str(yr): round(r, 4) for yr, r in ratios},
            ))

    return findings


# ─────────────────────────────────────────────
# 7. 科目组合稳定性（借贷科目对）
# ─────────────────────────────────────────────

def _account_relationship_drift(year_map: dict[int, pd.DataFrame]) -> list[CrossYearFinding]:
    """检测某年出现大量历史从未出现过的新科目组合。"""
    findings = []
    years = sorted(year_map.keys())
    if len(years) < 2:
        return findings

    def _get_acct_pairs(df: pd.DataFrame) -> set[tuple[str, str]]:
        pairs = set()
        for vid, grp in df.groupby("凭证编号"):
            accounts = grp["总账科目"].astype(str).str[:4].unique().tolist()
            accounts.sort()
            for i in range(len(accounts)):
                for j in range(i + 1, len(accounts)):
                    pairs.add((accounts[i], accounts[j]))
        return pairs

    historical_pairs: set[tuple[str, str]] = set()
    for i, yr in enumerate(years):
        current_pairs = _get_acct_pairs(year_map[yr])
        if i > 0:
            new_pairs = current_pairs - historical_pairs
            if len(new_pairs) > 20:
                findings.append(CrossYearFinding(
                    category="新科目组合涌现",
                    description=f"{yr}年出现{len(new_pairs)}个历史从未有过的科目借贷组合，可能是新业务通道或绕过内控的新做账方式",
                    years_involved=[years[i-1], yr],
                    voucher_ids=[],
                    amount=0,
                    severity="低",
                    evidence={"new_pair_count": len(new_pairs), "sample_pairs": list(new_pairs)[:5]},
                ))
        historical_pairs |= current_pairs

    return findings


def findings_to_summary_text(findings: list[CrossYearFinding]) -> str:
    """转为 LLM prompt 用的文本摘要。"""
    if not findings:
        return "未发现跨年异常。"

    lines = [f"发现 {len(findings)} 条跨年异常：\n"]
    for i, f in enumerate(findings, 1):
        lines.append(f"{i}. [{f.severity}] {f.category}（涉及年份：{f.years_involved}，金额：{f.amount:,.0f}）")
        lines.append(f"   {f.description}")
    return "\n".join(lines)
