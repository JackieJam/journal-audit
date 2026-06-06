"""跨年异常 / 费用结构 / 经验库规则的展示层。

从 app.py 抽离的纯展示与数据整形函数：接收 finding / financial / 规则字典，
返回 DataFrame 或直接渲染 Streamlit 组件，不读写 session_state。
app.py 以相同的私有别名 re-import 后注入各分析子页签。
"""

from __future__ import annotations

from typing import Any

import streamlit as st
import pandas as pd

from modules.formatting import (
    format_money,
    format_multiplier,
    format_percent,
    format_years,
    plain_value,
)
from modules.rule_text import generic_param_lines


def expense_summary_table(financial: dict) -> pd.DataFrame:
    expenses = dict(financial.get("expenses", {}))
    if financial.get("rd_expense", 0) != 0:
        expenses["研发费用"] = financial["rd_expense"]
    if financial.get("financial_expense", 0) != 0:
        expenses["财务费用(汇兑)"] = financial["financial_expense"]
    if financial.get("tax_surcharge", 0) != 0:
        expenses["税金及附加"] = financial["tax_surcharge"]

    items = sorted(expenses.items(), key=lambda x: x[1], reverse=True)
    total = sum(value for _, value in items)
    rows = [
        {
            "费用类别": category,
            "金额": value,
            "占比": value / total if total else 0,
        }
        for category, value in items
    ]
    return pd.DataFrame(rows)


def cross_year_expense_table(financials: dict[int, dict]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for year, financial in sorted(financials.items()):
        summary = expense_summary_table(financial)
        if summary.empty:
            continue
        for row in summary.to_dict("records"):
            rows.append(
                {
                    "年份": int(year),
                    "费用类别": str(row.get("费用类别", "")),
                    "金额": float(row.get("金额", 0) or 0),
                    "占比": float(row.get("占比", 0) or 0),
                }
            )
    return pd.DataFrame(rows)


def cross_year_focus_text(category: str) -> str:
    focus_map = {
        "预提冲回配对": "关注年末计提在次年一季度是否足额冲回，判断是否存在跨期悬挂。",
        "预提冲回金额不符": "关注年末计提和期后冲回金额是否接近，判断是否存在跨年损益调节。",
        "收入跨年确认": "关注年末收入冲高后次年一月红字冲回，判断是否存在收入提前确认。",
        "期末余额持续累积": "关注应收、预付或其他应收余额是否连续堆积，判断资产是否虚增或长期未清理。",
        "对手方跨年资金循环": "关注同一对手方年末资金流出和次年年初资金流入是否高度匹配。",
        "费用科目年度突变": "关注费用科目是否跨年异常放量，判断是否存在集中确认或重分类。",
        "手工凭证占比持续上升": "关注手工过账比例是否连续抬升，判断内控自动化和职责分离是否弱化。",
        "新科目组合涌现": "关注历史未出现过的借贷科目组合，判断是否存在新业务通道或绕过既有流程。",
    }
    return focus_map.get(category, "关注跨年金额、比例、对手方和凭证线索是否共同指向同一异常模式。")


def format_evidence_cell(key: str, value: Any) -> str:
    value = plain_value(value)
    if value is None:
        return "无"
    if key in {
        "accrual_amount",
        "reversal_amount",
        "jan_reversal",
        "out_amount",
        "in_amount",
        "prev_amount",
        "curr_amount",
    }:
        return format_money(value)
    if key == "coverage_ratio":
        return format_percent(value)
    if key == "dec_ratio":
        return format_multiplier(value)
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, list):
        if all(isinstance(item, list) and len(item) == 2 for item in value):
            return "、".join(f"{item[0]}-{item[1]}" for item in value) if value else "无"
        return "、".join(str(v) for v in value) if value else "无"
    return str(value)


def cross_year_evidence_rows(finding: Any) -> list[dict[str, str]]:
    labels = {
        "accrual_amount": ("年末预提金额", "年末已经计提、需要在期后核销或冲回的金额。"),
        "reversal_amount": ("次年Q1冲回金额", "次年一季度已找到的冲销或冲回金额。"),
        "coverage_ratio": ("冲回覆盖率", "覆盖率越低，跨期悬挂风险越高。"),
        "dec_ratio": ("12月收入放大倍数", "12月收入相对前11月均值的放大程度。"),
        "jan_reversal": ("次年1月红字冲回", "期后红字金额越大，越需要检查收入截止。"),
        "vendor": ("对手方编号", "用于定位需要进一步穿透的供应商或客户。"),
        "out_amount": ("年末流出金额", "年末向该对手方付出的资金规模。"),
        "in_amount": ("次年Q1流入金额", "次年一季度从同一对手方收回的资金规模。"),
        "account_prefix": ("科目前缀", "用于定位异常放量的会计科目。"),
        "category": ("科目类别", "按自动分类识别出的费用大类（费用 / 研发 / 财务 / 税金）。"),
        "prev_amount": ("上年发生额", "对比基准年份的发生额。"),
        "curr_amount": ("本年发生额", "异常年份的发生额。"),
        "new_pair_count": ("新增科目组合数", "历史未出现过的借贷组合数量。"),
        "sample_pairs": ("样例科目组合", "抽样展示的新增借贷组合，用于后续穿透。"),
    }
    evidence = plain_value(getattr(finding, "evidence", {}) or {})
    rows: list[dict[str, str]] = [
        {
            "维度": "涉及年份",
            "观察值": format_years(getattr(finding, "years_involved", [])),
            "怎么解读": "先按这些年度之间的交易连续性和期后变化做穿透。",
        },
        {
            "维度": "异常方向金额",
            "观察值": format_money(getattr(finding, "amount", 0)),
            "怎么解读": "用于判断该异常是否值得进入审计抽样优先级。",
        },
    ]

    if evidence and all(str(k).isdigit() for k in evidence.keys()):
        for year, amount in sorted(evidence.items()):
            rows.append(
                {
                    "维度": f"{year}年余额/发生额",
                    "观察值": format_money(amount),
                    "怎么解读": "用于观察跨年趋势是否连续累积或异常跳升。",
                }
            )
        return rows

    for key, value in evidence.items():
        label, explanation = labels.get(str(key), (str(key), "规则识别时保留的关键证据。"))
        rows.append(
            {
                "维度": label,
                "观察值": format_evidence_cell(str(key), value),
                "怎么解读": explanation,
            }
        )
    return rows


def render_cross_year_finding(finding: Any) -> None:
    st.markdown(f"**异常说明**：{finding.description}")
    st.caption(f"关注点：{cross_year_focus_text(finding.category)}")
    st.dataframe(
        pd.DataFrame(cross_year_evidence_rows(finding)),
        width="stretch",
        hide_index=True,
    )
    voucher_ids = plain_value(getattr(finding, "voucher_ids", []) or [])
    if voucher_ids:
        st.caption(f"关联凭证：已识别 {len(voucher_ids)} 个凭证号，优先抽查金额最大或期后冲回相关凭证。")
    raw_evidence = plain_value(getattr(finding, "evidence", {}) or {})
    if raw_evidence:
        with st.expander("技术明细（用于核对规则证据）", expanded=False):
            st.json(raw_evidence)


def render_library_rules(lib_rules: list[dict[str, Any]]) -> None:
    if not lib_rules:
        st.info("💡 经验库里还没有可推荐的历史规则。")
        return

    for rule in lib_rules:
        name = rule.get("name") or "未命名规则"
        rate = rule.get("performance", {}).get("confirmation_rate", 0)
        category = rule.get("category") or "未分类"

        rate_color = "green" if rate >= 0.7 else ("orange" if rate >= 0.4 else "gray")

        with st.expander(f"📚 {name} | 历史确认率 :{rate_color}[{rate:.0%}]", expanded=False):
            st.markdown(f"**类别**：{category}")
            perf = rule.get("performance", {})
            st.caption(
                f"📊 历史表现：已在 {perf.get('engagements_used', 0)} 个项目中使用，"
                f"累计命中 {perf.get('total_hits', 0)}，累计确认 {perf.get('total_confirmed', 0)}。"
            )

            params = rule.get("parameters", {})
            if params:
                st.markdown("**⚙️ 经验参数**")
                for line in generic_param_lines(params):
                    st.markdown(f"- {line}")

            rationale = rule.get("rationale", "")
            if rationale:
                st.success(f"**💡 经验说明**：{rationale}")

            notes = rule.get("applicable_context", {}).get("notes", "")
            if notes:
                st.info(f"📍 适用背景：{notes}")
            source_engagement = rule.get("source_engagement", "")
            if source_engagement:
                st.caption(f"来源项目：{source_engagement}")
