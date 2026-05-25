"""
序时账审计抽样工具 — 规则引擎
6 类精确规则：融资性贸易、预提冲销、化整为零、大额异常、手工凭证、年末突击
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class RuleHit:
    """单条规则命中结果"""

    voucher_id: float  # 凭证编号
    rule_type: str  # 规则类型名称
    evidence: str  # 触发证据描述
    line_indices: tuple[int, ...]  # 命中的行 index（DataFrame iloc）
    priority: int = 1  # 优先级 1-5，数值越大越重要


@dataclass
class RuleResult:
    """一类规则的全部命中结果"""

    rule_name: str
    hits: list[RuleHit] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.hits)


def _account_prefix(account_number: float | str, prefixes: list[str]) -> bool:
    """检查科目号是否匹配任一前缀"""
    acct_str = str(int(account_number)) if isinstance(account_number, float) else str(account_number)
    return any(acct_str.startswith(p) for p in prefixes)


def _has_text_keyword(text: str | float, keywords: list[str]) -> bool:
    """检查文本是否包含任一关键词"""
    if not isinstance(text, str):
        return False
    return any(kw in text for kw in keywords)


def _is_round_number(amount: float, threshold: float = 10_000) -> bool:
    """检查金额是否为整数（尾数全 0），且绝对值 >= 阈值"""
    abs_amt = abs(amount)
    return abs_amt >= threshold and abs_amt == int(abs_amt) and int(abs_amt) % 10_000 == 0


def _month_end_day(date) -> int:
    """返回该月最后一天的日期"""
    import calendar

    return calendar.monthrange(date.year, date.month)[1]


def _is_last_n_days_of_month(date, n: int = 3) -> bool:
    """判断日期是否在月末最后 n 天"""
    return date.day > (_month_end_day(date) - n)


def _is_first_n_days_of_month(date, n: int = 3) -> bool:
    """判断日期是否在月初前 n 天"""
    return date.day <= n


def _is_year_end(date) -> bool:
    """判断是否为年末（12/28-12/31）"""
    return date.month == 12 and date.day >= 28


def _is_holiday(date) -> bool:
    """判断是否为法定节假日或周末（使用 chinese_calendar）"""
    try:
        import chinese_calendar

        return chinese_calendar.is_holiday(date)
    except ImportError:
        # fallback：仅判断周末
        return date.weekday() >= 5


# ============================================================
# 白名单过滤
# ============================================================

def apply_whitelist(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    过滤白名单行，返回 (过滤后DataFrame, 被过滤行DataFrame)
    """
    from config import (
        WHITELIST_ACCOUNT_PREFIXES,
        WHITELIST_TEXT_KEYWORDS,
        WHITELIST_VOUCHER_TYPES,
    )

    mask = pd.Series(False, index=df.index)

    # 凭证类型白名单
    mask |= df["凭证类型"].isin(WHITELIST_VOUCHER_TYPES)

    # 文本关键词白名单
    for kw in WHITELIST_TEXT_KEYWORDS:
        mask |= df["文本"].str.contains(kw, na=False)

    # 科目前缀白名单
    for prefix in WHITELIST_ACCOUNT_PREFIXES:
        mask |= df["总账科目"].astype(str).str.startswith(prefix)

    # 金额为 0
    mask |= df["凭证货币价值"].fillna(0) == 0

    filtered = df[mask]
    remaining = df[~mask]
    return remaining, filtered


# ============================================================
# Rule 1: 融资性贸易识别
# ============================================================

def rule_financing_trade(df: pd.DataFrame) -> RuleResult:
    """
    找有贸易形式但无实质货物流转的凭证组。
    触发条件（满足任一组合）：
    - A+C：有收入科目+无对应成本 + 文本含关键词
    - B：毛利率异常（收入与成本差额 > 50%）
    - D：同一供应商 30 天内同时出现应付增加+应收增加（背靠背）
    """
    from config import (
        FINANCING_MARGIN_THRESHOLD,
        FINANCING_TRADE_KEYWORDS,
        FINANCING_TRADE_WINDOW_DAYS,
    )

    result = RuleResult(rule_name="融资性贸易识别")

    income_prefixes = ["6001", "6051"]
    cost_prefixes = ["6401"]
    inventory_prefixes = ["1403"]
    ap_prefix = "2202"
    ar_prefix = "1122"

    # 非贸易收入排除：租金、利息、存款、开票（非贸易）、项目组（内部服务）等
    NON_TRADE_REVENUE_KEYWORDS = ["租金", "利息", "存款", "理财", "保险", "补贴", "开票", "项目组", "管理服", "计提", "冲销预提", "期租", "预提", "冲销", "调整"]

    # --- 条件 A+C：收入科目 + 无成本/库存 + 文本含关键词 ---
    income_rows = df[df["总账科目"].astype(str).str[:4].isin(income_prefixes)]
    for voucher_id, grp in income_rows.groupby("凭证编号"):
        voucher_all = df[df["凭证编号"] == voucher_id]
        voucher_accounts = voucher_all["总账科目"].astype(str).tolist()

        has_cost = any(a[:4] in cost_prefixes + inventory_prefixes for a in voucher_accounts)
        has_keyword = _has_text_keyword(
            voucher_all["文本"].iloc[0], FINANCING_TRADE_KEYWORDS
        )

        # 排除非贸易收入（租金、利息等）
        voucher_text = str(voucher_all["文本"].iloc[0]) if not voucher_all["文本"].isna().all() else ""
        is_non_trade = any(kw in voucher_text for kw in NON_TRADE_REVENUE_KEYWORDS)

        if not has_cost and has_keyword and not is_non_trade:
            result.hits.append(
                RuleHit(
                    voucher_id=voucher_id,
                    rule_type="融资性贸易(A+C)",
                    evidence=f"收入科目但无对应成本科目，文本含关键词",
                    line_indices=tuple(grp.index.tolist()),
                    priority=4,
                )
            )

    # --- 条件 B：毛利率异常 ---
    for voucher_id, voucher_all in df.groupby("凭证编号"):
        revenue = 0.0
        cost = 0.0
        for _, row in voucher_all.iterrows():
            acct = str(int(row["总账科目"])) if isinstance(row["总账科目"], float) else str(row["总账科目"])
            amt = row["凭证货币价值"]
            if acct[:4] in income_prefixes:
                revenue += abs(amt)
            elif acct[:4] in cost_prefixes:
                cost += abs(amt)

        # 排除非贸易收入
        voucher_text = str(voucher_all["文本"].iloc[0]) if not voucher_all["文本"].isna().all() else ""
        is_non_trade = any(kw in voucher_text for kw in NON_TRADE_REVENUE_KEYWORDS)

        if revenue > 0 and not is_non_trade:
            margin = abs(revenue - cost) / revenue
            if margin > FINANCING_MARGIN_THRESHOLD:
                # 避免与 A+C 重复
                already_hit = any(h.voucher_id == voucher_id for h in result.hits)
                if not already_hit:
                    result.hits.append(
                        RuleHit(
                            voucher_id=voucher_id,
                            rule_type="融资性贸易(毛利率异常)",
                            evidence=f"收入={revenue:,.0f}, 成本={cost:,.0f}, 差异率={margin:.0%}",
                            line_indices=tuple(voucher_all.index.tolist()),
                            priority=4,
                        )
                    )

    # --- 条件 D：同一供应商 30 天内背靠背（应付+应收同时增加）---
    vendors = df["供应商编号"].dropna().unique()
    for vendor in vendors:
        v_rows = df[df["供应商编号"] == vendor].copy()
        if v_rows.empty:
            continue

        v_rows = v_rows.sort_values("过账日期")
        dates = v_rows["过账日期"].values

        for i in range(len(dates)):
            window_end = dates[i] + pd.Timedelta(days=FINANCING_TRADE_WINDOW_DAYS)
            window_rows = v_rows[
                (v_rows["过账日期"] >= dates[i]) & (v_rows["过账日期"] <= window_end)
            ]

            ap_rows = window_rows[
                window_rows["总账科目"].astype(str).str.startswith(ap_prefix)
                & (window_rows["借/贷标识"] == "S")
            ]
            ar_rows = window_rows[
                window_rows["总账科目"].astype(str).str.startswith(ar_prefix)
                & (window_rows["借/贷标识"] == "S")
            ]

            if not ap_rows.empty and not ar_rows.empty:
                for vid in window_rows["凭证编号"].unique():
                    already_hit = any(h.voucher_id == vid for h in result.hits)
                    if not already_hit:
                        result.hits.append(
                            RuleHit(
                                voucher_id=vid,
                                rule_type="融资性贸易(背靠背)",
                                evidence=f"供应商{vendor}在{FINANCING_TRADE_WINDOW_DAYS}天内应付+应收同时增加",
                                line_indices=tuple(
                                    window_rows[window_rows["凭证编号"] == vid].index.tolist()
                                ),
                                priority=4,
                            )
                        )

    return result


# ============================================================
# Rule 2: 预提冲销异常
# ============================================================

def rule_accrual_anomaly(df: pd.DataFrame) -> RuleResult:
    """
    找预提后未按原金额冲销或无合理背景的预提。
    """
    from config import (
        ACCRUAL_AMOUNT_TOLERANCE,
        ACCRUAL_FREQUENT_COUNT,
        ACCRUAL_MATCH_WINDOW_DAYS,
    )

    result = RuleResult(rule_name="预提冲销异常")

    # Step 1：找所有预提凭证行（通过文本匹配，因为实际预提科目在 2202/6401 等标准科目中）
    # 排除正常的冲销预提（文本含"冲销预提"）
    accrual_rows = df[
        df["文本"].str.contains("预提", na=False)
        & ~df["文本"].str.contains("冲销预提|冲预提", na=False)
    ]

    if accrual_rows.empty:
        return result

    # 按科目分组，找借贷配对
    accrual_accounts = accrual_rows["总账科目"].astype(str).str[:4].unique()
    for acct_prefix in accrual_accounts:
        acct_rows = accrual_rows[accrual_rows["总账科目"].astype(str).str[:4] == acct_prefix].copy()
        if acct_rows.empty:
            continue

        # 找借方行（预提增加）和贷方行（冲销）
        debit_rows = acct_rows[acct_rows["借/贷标识"] == "S"]
        credit_rows = acct_rows[acct_rows["借/贷标识"] == "H"]

        matched_vouchers: set[float] = set()

        for _, d_row in debit_rows.iterrows():
            vid = d_row["凭证编号"]
            d_date = d_row["过账日期"]
            d_amt = abs(d_row["凭证货币价值"])

            # 在 90 天内找金额接近的贷方冲销
            window_end = d_date + pd.Timedelta(days=ACCRUAL_MATCH_WINDOW_DAYS)
            candidates = credit_rows[
                (credit_rows["过账日期"] > d_date)
                & (credit_rows["过账日期"] <= window_end)
            ]

            found_match = False
            for _, c_row in candidates.iterrows():
                c_amt = abs(c_row["凭证货币价值"])
                if d_amt > 0 and abs(c_amt - d_amt) / d_amt <= ACCRUAL_AMOUNT_TOLERANCE:
                    found_match = True
                    matched_vouchers.add(vid)
                    break

            if not found_match and vid not in matched_vouchers:
                # 异常 A：悬空预提
                result.hits.append(
                    RuleHit(
                        voucher_id=vid,
                        rule_type="预提冲销(悬空预提)",
                        evidence=f"科目{acct_prefix}预提{d_amt:,.0f}，{ACCRUAL_MATCH_WINDOW_DAYS}天内无冲销",
                        line_indices=tuple([d_row.name]),
                        priority=3,
                    )
                )
                matched_vouchers.add(vid)

        # 异常 D：频繁预提冲销
        for _, row in acct_rows.iterrows():
            vid = row["凭证编号"]
            if vid in {h.voucher_id for h in result.hits}:
                continue

        # 按凭证统计年内出现次数
        voucher_counts = acct_rows.groupby("凭证编号").size()
        frequent_vids = voucher_counts[voucher_counts >= ACCRUAL_FREQUENT_COUNT].index
        for vid in frequent_vids:
            already = any(h.voucher_id == vid and "频繁" in h.rule_type for h in result.hits)
            if not already:
                result.hits.append(
                    RuleHit(
                        voucher_id=vid,
                        rule_type="预提冲销(频繁洗账)",
                        evidence=f"年内同科目预提冲销≥{ACCRUAL_FREQUENT_COUNT}次",
                        line_indices=tuple(
                            acct_rows[acct_rows["凭证编号"] == vid].index.tolist()
                        ),
                        priority=3,
                    )
                )

    return result


# ============================================================
# Rule 3: 化整为零（金额拆分）
# ============================================================

def rule_splitting(df: pd.DataFrame) -> RuleResult:
    """
    找将大额支付拆分为多笔小额以规避审批的凭证组。
    两个维度：同日同供应商、7天窗口同供应商。
    """
    from config import (
        SPLITTING_AMOUNT_VARIANCE,
        SPLITTING_MAX_SINGLE_AMOUNT,
        SPLITTING_MIN_LINES,
        SPLITTING_MIN_TOTAL,
        SPLITTING_WINDOW_DAYS,
        SPLITTING_WINDOW_MIN_LINES,
    )

    result = RuleResult(rule_name="化整为零")

    # 仅看贷方（付款方向）或借方（收款方向），取绝对值
    payment_rows = df[
        df["供应商编号"].notna()
        & (df["凭证货币价值"].fillna(0).abs() > 0)
        & (df["凭证货币价值"].fillna(0).abs() < SPLITTING_MAX_SINGLE_AMOUNT)
    ].copy()

    if payment_rows.empty:
        return result

    payment_rows["_abs_amt"] = payment_rows["凭证货币价值"].abs()

    flagged_vouchers: set[float] = set()

    # 维度 1：同日同供应商
    for (vendor, date), grp in payment_rows.groupby(["供应商编号", "过账日期"]):
        if len(grp) < SPLITTING_MIN_LINES:
            continue

        total = grp["_abs_amt"].sum()
        if total < SPLITTING_MIN_TOTAL:
            continue

        for vid in grp["凭证编号"].unique():
            if vid not in flagged_vouchers:
                flagged_vouchers.add(vid)
                result.hits.append(
                    RuleHit(
                        voucher_id=vid,
                        rule_type="化整为零(同日拆分)",
                        evidence=f"供应商{vendor}同日{len(grp)}笔，单笔<{SPLITTING_MAX_SINGLE_AMOUNT:,.0f}，合计{total:,.0f}",
                        line_indices=tuple(grp[grp["凭证编号"] == vid].index.tolist()),
                        priority=5,
                    )
                )

    # 维度 2：7天窗口内金额高度相似
    for vendor, v_rows in payment_rows.groupby("供应商编号"):
        v_rows = v_rows.sort_values("过账日期")
        if len(v_rows) < SPLITTING_WINDOW_MIN_LINES:
            continue

        dates = v_rows["过账日期"].values
        for i in range(len(dates)):
            window_end = dates[i] + pd.Timedelta(days=SPLITTING_WINDOW_DAYS)
            window = v_rows[
                (v_rows["过账日期"] >= dates[i]) & (v_rows["过账日期"] <= window_end)
            ]

            if len(window) < SPLITTING_WINDOW_MIN_LINES:
                continue

            # 检查金额相似度
            amts = window["_abs_amt"].values
            mean_amt = amts.mean()
            if mean_amt == 0:
                continue

            variance = max(abs(a - mean_amt) / mean_amt for a in amts)
            if variance <= SPLITTING_AMOUNT_VARIANCE:
                for vid in window["凭证编号"].unique():
                    if vid not in flagged_vouchers:
                        flagged_vouchers.add(vid)
                        result.hits.append(
                            RuleHit(
                                voucher_id=vid,
                                rule_type="化整为零(窗口相似)",
                                evidence=f"供应商{vendor}在{SPLITTING_WINDOW_DAYS}天内{len(window)}笔金额相似（差异≤{SPLITTING_AMOUNT_VARIANCE:.0%}）",
                                line_indices=tuple(
                                    window[window["凭证编号"] == vid].index.tolist()
                                ),
                                priority=5,
                            )
                        )

    return result


# ============================================================
# Rule 4: 大额异常流水
# ============================================================

def rule_large_anomaly(df: pd.DataFrame) -> RuleResult:
    """
    找金额巨大、频繁发生或时机异常的凭证。
    """
    from config import (
        LARGE_AMOUNT_THRESHOLD,
        LARGE_REPEAT_MIN_COUNT,
        LARGE_REPEAT_THRESHOLD,
        LARGE_REPEAT_WINDOW_DAYS,
    )

    result = RuleResult(rule_name="大额异常流水")

    # 大额整数排除：银行转账、内部资金调度等正常业务
    ROUND_NUMBER_WHITELIST = ["转开", "通知存款", "转回", "财司", "同名划转", "资金池", "银行账户调整", "调整银行", "关联"]

    # 情形 A：大额整数
    large_round = df[
        df["凭证货币价值"].abs().fillna(0) >= LARGE_AMOUNT_THRESHOLD
    ]
    for _, row in large_round.iterrows():
        if _is_round_number(row["凭证货币价值"], LARGE_AMOUNT_THRESHOLD):
            text = str(row.get("文本", ""))
            is_whitelisted = any(kw in text for kw in ROUND_NUMBER_WHITELIST)
            if not is_whitelisted:
                result.hits.append(
                    RuleHit(
                        voucher_id=row["凭证编号"],
                        rule_type="大额整数",
                        evidence=f"金额{row['凭证货币价值']:,.0f}为整数",
                        line_indices=tuple([row.name]),
                        priority=2,
                    )
                )

    # 情形 B：大额重复（同供应商 30 天内 ≥2 笔，每笔 ≥5000 万）
    vendors = df["供应商编号"].dropna().unique()
    for vendor in vendors:
        v_rows = df[df["供应商编号"] == vendor].copy()
        v_large = v_rows[v_rows["凭证货币价值"].abs().fillna(0) >= LARGE_REPEAT_THRESHOLD]
        if len(v_large) < LARGE_REPEAT_MIN_COUNT:
            continue

        v_large = v_large.sort_values("过账日期")
        dates = v_large["过账日期"].values

        for i in range(len(dates)):
            window_end = dates[i] + pd.Timedelta(days=LARGE_REPEAT_WINDOW_DAYS)
            window = v_large[
                (v_large["过账日期"] >= dates[i]) & (v_large["过账日期"] <= window_end)
            ]
            if len(window) >= LARGE_REPEAT_MIN_COUNT:
                for vid in window["凭证编号"].unique():
                    already = any(
                        h.voucher_id == vid and "大额重复" in h.rule_type
                        for h in result.hits
                    )
                    if not already:
                        result.hits.append(
                            RuleHit(
                                voucher_id=vid,
                                rule_type="大额重复",
                                evidence=f"供应商{vendor}在{LARGE_REPEAT_WINDOW_DAYS}天内≥{LARGE_REPEAT_MIN_COUNT}笔，每笔≥{LARGE_REPEAT_THRESHOLD/1e6:.0f}M",
                                line_indices=tuple(
                                    window[window["凭证编号"] == vid].index.tolist()
                                ),
                                priority=4,
                            )
                        )

    # 情形 C：节假日过账（按凭证去重）
    holiday_vouchers: set[float] = set()
    for _, row in df.iterrows():
        vid = row["凭证编号"]
        if vid in holiday_vouchers:
            continue
        date = row["过账日期"]
        if isinstance(date, pd.Timestamp) and _is_holiday(date):
            holiday_vouchers.add(vid)
            voucher_rows = df[df["凭证编号"] == vid]
            result.hits.append(
                RuleHit(
                    voucher_id=vid,
                    rule_type="节假日过账",
                    evidence=f"过账日期{date.strftime('%Y-%m-%d')}为节假日",
                    line_indices=tuple(voucher_rows.index.tolist()),
                    priority=2,
                )
            )

    # 情形 D：非工作时间录入（00:00-06:00，按凭证去重）
    night_vouchers: set[float] = set()
    for _, row in df.iterrows():
        vid = row["凭证编号"]
        if vid in night_vouchers:
            continue
        time_str = row.get("录入时间")
        if isinstance(time_str, str) and re.match(r"^\d{2}:\d{2}:\d{2}$", time_str):
            hour = int(time_str[:2])
            if 0 <= hour < 6:
                night_vouchers.add(vid)
                voucher_rows = df[df["凭证编号"] == vid]
                result.hits.append(
                    RuleHit(
                        voucher_id=vid,
                        rule_type="非工作时间录入",
                        evidence=f"录入时间{time_str}（凌晨0-6点）",
                        line_indices=tuple(voucher_rows.index.tolist()),
                        priority=3,
                    )
                )

    return result


# ============================================================
# Rule 5: 手工凭证 & 关键人员
# ============================================================

def rule_manual_entries(df: pd.DataFrame) -> RuleResult:
    """
    找非系统自动产生的高风险手工调整凭证。
    排除：自动凭证(AA/AB/ZP)、批量过账凭证(AFB/AFG/AFK)。
    仅保留：关键人员凭证、大额损益调整、月末/年末调整。
    """
    from config import (
        KEY_PERSONNEL,
        MANUAL_EXCLUDE_VOUCHER_TYPES,
        MANUAL_MONTH_END_DAYS,
        MANUAL_PNL_AMOUNT_THRESHOLD,
    )

    result = RuleResult(rule_name="手工凭证")

    # Step 1：凭证类型 = AF（手工调整），排除自动凭证和批量过账凭证（AFB/AFG/AFK）
    manual_rows = df[
        (df["凭证类型"] == "AF")
        & (~df["凭证类型"].isin(MANUAL_EXCLUDE_VOUCHER_TYPES))
        & (~df["文本"].str.contains("AFB|AFG|AFK", na=False))
    ]

    if manual_rows.empty:
        return result

    for _, row in manual_rows.iterrows():
        vid = row["凭证编号"]
        user = str(row.get("用户名", ""))
        acct = str(int(row["总账科目"])) if isinstance(row["总账科目"], float) else str(row["总账科目"])
        amt = abs(row["凭证货币价值"])
        date = row["过账日期"]

        priority = 1
        evidence_parts: list[str] = []

        # 优先级 1：关键人员
        if user in KEY_PERSONNEL:
            priority = 5
            evidence_parts.append(f"关键人员{user}手工凭证")

        # 优先级 2：损益科目且金额 > 阈值
        elif acct[0] in ("5", "6") and amt > MANUAL_PNL_AMOUNT_THRESHOLD:
            priority = 3
            evidence_parts.append(f"损益科目{acct}，金额{amt:,.0f}")

        # 优先级 3：月末/年末
        elif isinstance(date, pd.Timestamp):
            month_end = date.day > (_month_end_day(date) - MANUAL_MONTH_END_DAYS)
            year_end = _is_year_end(date)
            if month_end or year_end:
                priority = 2
                timing = "年末" if year_end else "月末"
                evidence_parts.append(f"{timing}手工调整")

        if evidence_parts:
            result.hits.append(
                RuleHit(
                    voucher_id=vid,
                    rule_type="手工凭证",
                    evidence="，".join(evidence_parts),
                    line_indices=tuple([row.name]),
                    priority=priority,
                )
            )

    return result


# ============================================================
# Rule 6: 年末突击确认
# ============================================================

def rule_yearend_surge(df: pd.DataFrame) -> RuleResult:
    """
    找年末集中认收入或冲成本的异常凭证。
    """
    from config import YEAREND_SURGE_MULTIPLIER

    result = RuleResult(rule_name="年末突击确认")

    income_prefixes = ["6001", "6051"]
    cost_prefix = "6401"

    # 按月汇总收入贷方发生额
    df_income = df[
        df["总账科目"].astype(str).str[:4].isin(income_prefixes)
        & (df["借/贷标识"] == "H")
    ].copy()

    if df_income.empty:
        return result

    df_income["_month"] = df_income["过账日期"].dt.month
    df_income["_abs_amt"] = df_income["凭证货币价值"].abs()

    monthly = df_income.groupby("_month")["_abs_amt"].sum()

    if len(monthly) < 2:
        return result

    # 前 11 月月均
    non_dec_months = monthly[monthly.index < 12]
    if non_dec_months.empty:
        return result

    avg_non_dec = non_dec_months.mean()
    dec_amount = monthly.get(12, 0)

    if avg_non_dec > 0 and dec_amount > avg_non_dec * YEAREND_SURGE_MULTIPLIER:
        # 12 月收入突增，纳入全部 12 月该类科目凭证
        surge_vids = df_income[df_income["_month"] == 12]["凭证编号"].unique()

        # 检查成本科目是否同步增长
        df_cost = df[
            df["总账科目"].astype(str).str[:4] == cost_prefix
        ].copy()
        df_cost["_month"] = df_cost["过账日期"].dt.month
        df_cost["_abs_amt"] = df_cost["凭证货币价值"].abs()
        cost_monthly = df_cost.groupby("_month")["_abs_amt"].sum()
        cost_non_dec = cost_monthly[cost_monthly.index < 12]
        cost_dec = cost_monthly.get(12, 0)
        cost_avg = cost_non_dec.mean() if not cost_non_dec.empty else 0

        cost_surge = cost_avg > 0 and cost_dec > cost_avg * YEAREND_SURGE_MULTIPLIER

        for vid in surge_vids:
            evidence = f"12月收入{dec_amount:,.0f}，前11月月均{avg_non_dec:,.0f}，倍数{dec_amount/avg_non_dec:.1f}x"
            if not cost_surge:
                evidence += "（成本无对应增长，疑点加重）"

            result.hits.append(
                RuleHit(
                    voucher_id=vid,
                    rule_type="年末突击确认",
                    evidence=evidence,
                    line_indices=tuple(
                        df_income[
                            (df_income["凭证编号"] == vid) & (df_income["_month"] == 12)
                        ].index.tolist()
                    ),
                    priority=3,
                )
            )

    return result


# ============================================================
# 全部规则执行入口
# ============================================================

ALL_RULES = [
    rule_financing_trade,
    rule_accrual_anomaly,
    rule_splitting,
    rule_large_anomaly,
    rule_manual_entries,
    rule_yearend_surge,
]


def run_all_rules(df: pd.DataFrame, rule_filter: str | None = None) -> list[RuleResult]:
    """
    执行全部或指定规则，返回 RuleResult 列表。
    rule_filter: 指定规则名称前缀，如 "financing_trade"
    """
    rule_map = {
        "financing_trade": rule_financing_trade,
        "accrual_anomaly": rule_accrual_anomaly,
        "splitting": rule_splitting,
        "large_anomaly": rule_large_anomaly,
        "manual_entries": rule_manual_entries,
        "yearend_surge": rule_yearend_surge,
    }

    if rule_filter:
        if rule_filter not in rule_map:
            available = ", ".join(rule_map.keys())
            raise ValueError(f"未知规则: {rule_filter}，可用规则: {available}")
        funcs = [rule_map[rule_filter]]
    else:
        funcs = ALL_RULES

    results: list[RuleResult] = []
    for func in funcs:
        r = func(df)
        results.append(r)

    return results
