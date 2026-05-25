"""
Plotly 图表组件库，供 Streamlit 页面调用。
所有函数返回 plotly.graph_objects.Figure 或 plotly.express Figure，
Streamlit 用 st.plotly_chart(fig, use_container_width=True) 渲染。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# 现代专业审计配色方案
COLORS = [
    "#3b82f6", # Blue 500   → 年1
    "#f59e0b", # Amber 500  → 年2
    "#10b981", # Emerald 500 → 年3
    "#ef4444", # Red 500    → 年4
    "#8b5cf6", # Violet 500 → 年5
    "#ec4899", # Pink 500   → 年6
]


def _quiet_profile_layout(
    fig: go.Figure,
    *,
    title: str,
    height: int = 420,
    bottom: int = 64,
    legend_y: float = -0.18,
) -> go.Figure:
    """Shared spacing for compact Streamlit profile charts."""
    fig.update_layout(
        title=dict(
            text=f"<b>{title}</b>", 
            y=0.98, 
            x=0.0, 
            xanchor="left",
            font=dict(size=16)
        ),
        height=height,
        margin=dict(t=70, b=bottom, l=60, r=20),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=legend_y,
            xanchor="center",
            x=0.5,
            font=dict(size=11)
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            showgrid=False,
            tickfont=dict(size=11)
        ),
        yaxis=dict(
            tickfont=dict(size=11)
        ),
        uniformtext=dict(mode="hide", minsize=10),
    )
    return fig


# ─────────────────────────────────────────────
# 画像图表
# ─────────────────────────────────────────────

def monthly_trend_chart(profiles: dict[int, dict], view: str = "both") -> go.Figure:
    """三年月度凭证数/金额趋势对比。view: 'vouchers' | 'amount' | 'both'"""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    months = list(range(1, 13))
    month_labels = [f"{m}月" for m in months]

    for i, (year, profile) in enumerate(sorted(profiles.items())):
        tp = profile.get("temporal_patterns", {})
        counts = [tp.get("monthly_count", {}).get(m, 0) for m in months]
        amounts = [tp.get("monthly_amount", {}).get(m, 0) / 1e4 for m in months]  # 万元

        color = COLORS[i % len(COLORS)]
        show_vouchers = view in ("vouchers", "both")
        show_amount = view in ("amount", "both")

        if show_vouchers:
            fig.add_trace(
                go.Bar(name=f"{year}年凭证数", x=month_labels, y=counts,
                       marker_color=color, opacity=0.6, legendgroup=str(year)),
                secondary_y=False,
            )
        if show_amount:
            fig.add_trace(
                go.Scatter(name=f"{year}年金额(万)", x=month_labels, y=amounts,
                           line=dict(color=color, width=2), mode="lines+markers",
                           legendgroup=str(year)),
                secondary_y=True,
            )

    fig.update_layout(
        barmode="group",
    )
    title_map = {"vouchers": "月度凭证数趋势（多年对比）", "amount": "月度金额趋势（多年对比）", "both": "月度凭证数 & 金额趋势（多年对比）"}
    _quiet_profile_layout(fig, title=title_map.get(view, title_map["both"]), height=460, bottom=92)
    if view in ("vouchers", "both"):
        fig.update_yaxes(title_text="凭证数", secondary_y=False)
    if view in ("amount", "both"):
        fig.update_yaxes(title_text="金额（万元）", secondary_y=True)
    return fig


def amount_distribution_chart(profiles: dict[int, dict]) -> go.Figure:
    """金额分布分位数箱线图（多年并排）。"""
    fig = go.Figure()

    for year, profile in sorted(profiles.items()):
        amt = profile.get("amount_distribution", {}).get("overall", {})
        if not amt:
            continue
        fig.add_trace(go.Box(
            name=str(year),
            q1=[amt.get("p25", amt.get("p50", 0))],
            median=[amt.get("p50", 0)],
            q3=[amt.get("p75", 0)],
            lowerfence=[0],
            upperfence=[amt.get("p99", 0)],
            mean=[amt.get("mean", 0)],
            boxmean=True,
        ))

    _quiet_profile_layout(fig, title="金额分布箱线图（P25/P50/P75/P99）", height=420, bottom=72)
    fig.update_yaxes(title_text="金额（元）")
    return fig


def voucher_type_pie(profile: dict, year: int) -> go.Figure:
    """凭证类型结构饼图（单年）。"""
    vt = profile.get("voucher_type_structure", {}).get("all", {})
    if not vt:
        return go.Figure()

    labels = list(vt.keys())
    values = list(vt.values())

    fig = px.pie(
        names=labels, values=values,
        title=f"{year}年凭证类型结构",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.35,
    )
    fig.update_traces(
        textinfo="percent",
        textposition="inside",
        hovertemplate="%{label}<br>%{value:,} 行<br>%{percent}<extra></extra>",
    )
    _quiet_profile_layout(fig, title=f"{year}年凭证类型结构", height=420, bottom=110, legend_y=-0.22)
    return fig


def month_end_heatmap(profiles: dict[int, dict]) -> go.Figure:
    """月末集中度热力图（月份 × 年份）。"""
    years = sorted(profiles.keys())
    months = list(range(1, 13))

    z = []
    for year in years:
        tp = profiles[year].get("temporal_patterns", {})
        ratios = tp.get("month_end_concentration", {})
        z.append([ratios.get(m, 0) for m in months])

    fig = go.Figure(go.Heatmap(
        z=z,
        x=[f"{m}月" for m in months],
        y=[str(y) for y in years],
        colorscale="RdYlGn_r",
        text=[[f"{v:.0%}" for v in row] for row in z],
        texttemplate="%{text}",
        colorbar=dict(title="月末占比"),
    ))
    _quiet_profile_layout(fig, title="月末最后5天凭证集中度（各年各月）", height=340, bottom=64)
    return fig


def user_bar_chart(profile: dict, year: int) -> go.Figure:
    """Top 用户操作量柱状图。"""
    users = profile.get("user_patterns", {}).get("top_users", {})
    if not users:
        return go.Figure()

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)[:10]
    names = [u[0] for u in sorted_users]
    counts = [u[1] for u in sorted_users]

    fig = px.bar(
        x=counts, y=names, orientation="h",
        title=f"{year}年 Top 10 操作用户",
        labels={"x": "凭证行数", "y": "用户名"},
        color=counts, color_continuous_scale="Blues",
    )
    fig.update_traces(texttemplate="%{x:,}", textposition="outside", cliponaxis=False)
    _quiet_profile_layout(fig, title=f"{year}年 Top 10 操作用户", height=440, bottom=64)
    fig.update_layout(coloraxis_showscale=False, showlegend=False)
    fig.update_yaxes(automargin=True)
    return fig


def benford_first_digit_chart(profile: dict, year: int) -> go.Figure:
    """本福特定律首位数字：实际分布 vs 理论分布。"""
    benford = profile.get("benford_first_digit", {})
    observed = benford.get("observed", {})
    expected = benford.get("expected", {})
    digits = list(range(1, 10))
    obs_vals = [observed.get(d, observed.get(str(d), 0)) * 100 for d in digits]
    exp_vals = [expected.get(d, expected.get(str(d), 0)) * 100 for d in digits]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="实际占比",
        x=[str(d) for d in digits],
        y=obs_vals,
        marker_color="#2F5496",
        text=[f"{v:.1f}%" for v in obs_vals],
        textposition="outside",
        cliponaxis=False,
        hovertemplate="首位数字 %{x}<br>实际 %{y:.2f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="本福特期望",
        x=[str(d) for d in digits],
        y=exp_vals,
        mode="lines+markers",
        line=dict(color="#ED7D31", width=2.5),
        marker=dict(size=8),
        hovertemplate="首位数字 %{x}<br>期望 %{y:.2f}%<extra></extra>",
    ))
    _quiet_profile_layout(fig, title=f"{year}年金额首位数字分布（本福特定律）", height=440, bottom=88)
    fig.update_xaxes(title_text="金额首位数字")
    fig.update_yaxes(title_text="占比", ticksuffix="%", rangemode="tozero")
    return fig


def vendor_treemap(profile: dict, year: int) -> go.Figure:
    """供应商金额分布 treemap。"""
    vendors = profile.get("vendor_patterns", {}).get("top_vendors_by_amount", {})
    if not vendors:
        return go.Figure()

    names = [str(v) for v in vendors.keys()]
    values = [v.get("total_amount", 0) for v in vendors.values()]

    fig = px.treemap(
        names=names, values=values, parents=[""] * len(names),
        title=f"{year}年 Top 供应商金额分布",
        color=values, color_continuous_scale="Blues",
    )
    fig.update_layout(height=400, margin=dict(t=60, b=10))
    return fig


# ─────────────────────────────────────────────
# 跨年图表
# ─────────────────────────────────────────────

def cross_year_revenue_chart(financials: dict[int, dict]) -> go.Figure:
    """三年收入月度走势叠加图，突出年末异常。"""
    fig = go.Figure()

    income_prefixes_note = "（科目6001/6051）"
    for i, (year, financial) in enumerate(sorted(financials.items())):
        amounts = {m: financial.get("monthly_revenue", {}).get(m, 0) / 1e4 for m in range(1, 13)}
        months_labels = [f"{m}月" for m in amounts.keys()]
        vals = list(amounts.values())

        color = COLORS[i % len(COLORS)]
        fig.add_trace(go.Scatter(
            x=months_labels, y=vals,
            name=str(year),
            line=dict(color=color, width=2),
            mode="lines+markers",
        ))

    fig.update_layout(
        title=f"月度金额走势（三年对比）{income_prefixes_note}",
        yaxis_title="金额（万元）",
        legend=dict(orientation="h"),
        height=400,
        margin=dict(t=60, b=40),
    )
    return fig


def cross_year_findings_chart(findings: list) -> go.Figure:
    """跨年发现按类型 & 严重程度汇总柱状图。"""
    if not findings:
        return go.Figure().update_layout(title="无跨年异常发现")

    categories = {}
    for f in findings:
        key = f.category
        categories.setdefault(key, {"高": 0, "中": 0, "低": 0})
        categories[key][f.severity] = categories[key].get(f.severity, 0) + 1

    cats = list(categories.keys())
    highs = [categories[c]["高"] for c in cats]
    meds = [categories[c]["中"] for c in cats]
    lows = [categories[c]["低"] for c in cats]

    fig = go.Figure([
        go.Bar(name="高风险", x=cats, y=highs, marker_color="#E53935"),
        go.Bar(name="中风险", x=cats, y=meds, marker_color="#FB8C00"),
        go.Bar(name="低风险", x=cats, y=lows, marker_color="#43A047"),
    ])
    fig.update_layout(
        title="跨年异常发现汇总",
        barmode="stack",
        height=380,
        margin=dict(t=60, b=60),
        xaxis_tickangle=-20,
    )
    return fig


# ─────────────────────────────────────────────
# 抽样结果图表
# ─────────────────────────────────────────────

def rule_hit_bar(hits_summary: list[dict]) -> go.Figure:
    """规则命中数 vs LLM 确认数对比柱状图。"""
    names = [r["规则"] for r in hits_summary]
    hit_counts = [r["命中数"] for r in hits_summary]
    voucher_counts = [r["凭证数"] for r in hits_summary]

    fig = go.Figure([
        go.Bar(name="命中行数", x=names, y=hit_counts, marker_color="#4472C4"),
        go.Bar(name="命中凭证数", x=names, y=voucher_counts, marker_color="#ED7D31"),
    ])
    fig.update_layout(
        title="规则命中统计",
        barmode="group",
        height=380,
        margin=dict(t=60, b=80),
        xaxis_tickangle=-20,
    )
    return fig


def risk_level_pie(llm_judgments: dict) -> go.Figure:
    """LLM 核实风险级别分布饼图。"""
    high = med = fallback = 0
    for judgments in llm_judgments.values():
        for j in judgments:
            if j.source == "fallback":
                fallback += 1
            elif j.risk_level == "高":
                high += 1
            else:
                med += 1

    fig = px.pie(
        names=["高风险", "中风险", "待复核(fallback)"],
        values=[high, med, fallback],
        color_discrete_map={"高风险": "#E53935", "中风险": "#FB8C00", "待复核(fallback)": "#9E9E9E"},
        title="LLM 核实结果分布",
        hole=0.4,
    )
    fig.update_layout(height=340, margin=dict(t=60, b=20))
    return fig


# ─────────────────────────────────────────────
# 财务画像图表
# ─────────────────────────────────────────────

def financial_overview_chart(financials: dict[int, dict]) -> go.Figure:
    """财务总览：2x2 子图 — 收入/成本/毛利对比、毛利率、费用结构、收入构成。"""
    years = sorted(financials.keys())
    if not years:
        return go.Figure()

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("收入 / 成本 / 毛利", "毛利率趋势", "费用结构", "收入构成"),
        specs=[[{"type": "bar"}, {"type": "scatter"}],
               [{"type": "pie"}, {"type": "bar"}]],
        vertical_spacing=0.22,
        horizontal_spacing=0.10,
    )

    # 左上：收入/成本/毛利柱状图
    rev_vals = [financials[y]["revenue"]["total"] / 1e4 for y in years]
    cost_vals = [financials[y]["cost"]["total"] / 1e4 for y in years]
    gp_vals = [financials[y]["gross_profit"] / 1e4 for y in years]
    year_labels = [f"{y}年" for y in years]
    fig.add_trace(go.Bar(name="收入", x=year_labels, y=rev_vals, marker_color="#2F5496"), row=1, col=1)
    fig.add_trace(go.Bar(name="成本", x=year_labels, y=cost_vals, marker_color="#ED7D31"), row=1, col=1)
    fig.add_trace(go.Bar(name="毛利", x=year_labels, y=gp_vals, marker_color="#70AD47"), row=1, col=1)
    fig.update_yaxes(title_text="金额（万元）", row=1, col=1)

    # 右上：毛利率折线
    gm_vals = [financials[y]["gross_margin"] * 100 for y in years]
    fig.add_trace(go.Scatter(
        x=year_labels, y=gm_vals, mode="lines+markers",
        line=dict(color="#2F5496", width=2.5), name="毛利率",
        text=[f"{v:.1f}%" for v in gm_vals], textposition="top center",
    ), row=1, col=2)
    fig.update_yaxes(title_text="%", row=1, col=2)

    # 左下：费用结构饼图（最新年份）
    latest = financials[years[-1]]
    exp = dict(latest.get("expenses", {}))
    if latest.get("rd_expense", 0) > 0:
        exp["研发费用"] = latest["rd_expense"]
    if latest.get("financial_expense", 0) > 0:
        exp["财务费用"] = latest["financial_expense"]
    if latest.get("tax_surcharge", 0) > 0:
        exp["税金及附加"] = latest["tax_surcharge"]
    exp_labels = list(exp.keys())
    exp_values = [v / 1e4 for v in exp.values()]
    fig.add_trace(go.Pie(
        labels=exp_labels, values=exp_values,
        textinfo="percent", hole=0.35,
        showlegend=False,
        marker_colors=px.colors.qualitative.Set2,
        hovertemplate="%{label}<br>%{value:,.0f}万<br>%{percent}<extra></extra>",
    ), row=2, col=1)

    # 右下：收入构成分组柱状图。保持全图 barmode=group，避免左上收入/成本/毛利被误堆叠。
    for cls_key, color in [("主营业务收入_第三方", "#2F5496"), ("主营业务收入_内部关联方", "#ED7D31"),
                            ("主营业务收入_外部关联方", "#70AD47"), ("其他业务收入", "#FFC000")]:
        vals = [financials[y]["revenue"].get(cls_key, 0) / 1e4 for y in years]
        fig.add_trace(go.Bar(name=cls_key.replace("主营业务收入_", ""), x=year_labels, y=vals, marker_color=color), row=2, col=2)
    fig.update_yaxes(title_text="金额（万元）", row=2, col=2)

    fig.update_layout(
        height=780,
        margin=dict(t=90, b=120, l=70, r=40),
        barmode="group",
        legend=dict(orientation="h", yanchor="top", y=-0.10, xanchor="center", x=0.5),
        showlegend=True,
        uniformtext=dict(mode="hide", minsize=10),
    )
    fig.update_annotations(font_size=14)
    return fig


def multi_year_financial_overview(financials: dict[int, dict]) -> go.Figure:
    """多年度财务趋势总览：左柱(收入/成本/毛利/净利)、右折线(毛利率/净利率/研发费率)。"""
    years = sorted(financials.keys())
    if not years:
        return go.Figure()

    rev_vals = [financials[y]["revenue"]["total"] / 1e4 for y in years]
    cost_vals = [financials[y]["cost"]["total"] / 1e4 for y in years]
    gp_vals = [financials[y]["gross_profit"] / 1e4 for y in years]
    gm_vals = [financials[y]["gross_margin"] * 100 for y in years]

    # 净利润 = 毛利 - 费用 - 财务费用 - 税金 + 投资收益 + 营业外收支
    net_vals = []
    net_margin_vals = []
    for y in years:
        f = financials[y]
        rev = f["revenue"]["total"]
        gp = f["gross_profit"]
        exp_total = sum(f.get("expenses", {}).values())
        fin_exp = f.get("financial_expense", 0)
        tax = f.get("tax_surcharge", 0)
        inv_inc = f.get("investment_income", 0)
        non_op_inc = f.get("non_operating_income", 0)
        non_op_exp = f.get("non_operating_expense", 0)
        net = gp - exp_total - fin_exp - tax + inv_inc + non_op_inc - non_op_exp
        net_vals.append(net / 1e4)
        net_margin_vals.append((net / rev * 100) if rev > 0 else 0)

    rd_ratios = [financials[y].get("rd_ratio", 0) * 100 for y in years]
    year_labels = [f"{y}年" for y in years]

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("收入 / 成本 / 毛利 / 净利", "毛利率 / 净利率 / 研发费率"),
        horizontal_spacing=0.12,
        specs=[[{"type": "bar"}, {"type": "scatter"}]],
    )

    # 左：柱状图
    fig.add_trace(go.Bar(name="收入", x=year_labels, y=rev_vals, marker_color="#2F5496"), row=1, col=1)
    fig.add_trace(go.Bar(name="成本", x=year_labels, y=cost_vals, marker_color="#ED7D31"), row=1, col=1)
    fig.add_trace(go.Bar(name="毛利", x=year_labels, y=gp_vals, marker_color="#70AD47"), row=1, col=1)
    fig.add_trace(go.Bar(name="净利", x=year_labels, y=net_vals, marker_color="#7c3aed"), row=1, col=1)
    fig.update_yaxes(title_text="金额（万元）", row=1, col=1)

    # 右：折线图（均为 %，共用主 Y 轴）
    fig.add_trace(
        go.Scatter(
            x=year_labels, y=gm_vals, mode="lines+markers",
            line=dict(color="#2F5496", width=2.5), name="毛利率",
            text=[f"{v:.1f}%" for v in gm_vals], textposition="top center",
        ), row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=year_labels, y=net_margin_vals, mode="lines+markers",
            line=dict(color="#7c3aed", width=2.5), name="净利率",
            text=[f"{v:.1f}%" for v in net_margin_vals], textposition="bottom center",
        ), row=1, col=2,
    )
    fig.add_trace(
        go.Scatter(
            x=year_labels, y=rd_ratios, mode="lines+markers",
            line=dict(color="#DC2626", width=2, dash="dash"), name="研发费用率",
            text=[f"{v:.1f}%" for v in rd_ratios], textposition="top center",
        ), row=1, col=2,
    )
    fig.update_yaxes(title_text="%", row=1, col=2)

    fig.update_layout(
        height=460,
        margin=dict(t=70, b=60, l=60, r=40),
        barmode="group",
        legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="center", x=0.5),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        uniformtext=dict(mode="hide", minsize=10),
    )
    fig.update_annotations(font_size=14)
    return fig


def monthly_pl_trend_chart(financials: dict[int, dict], year: int) -> go.Figure:
    """单年月度收入/成本/毛利率趋势（双 Y 轴）。"""
    f = financials.get(year)
    if not f:
        return go.Figure()

    months = list(range(1, 13))
    month_labels = [f"{m}月" for m in months]
    rev = [f["monthly_revenue"].get(m, 0) / 1e4 for m in months]
    cost = [f["monthly_cost"].get(m, 0) / 1e4 for m in months]
    gp = [f["monthly_gp"].get(m, 0) / 1e4 for m in months]
    margin = []
    for m in months:
        r = f["monthly_revenue"].get(m, 0)
        margin.append((f["monthly_gp"].get(m, 0) / r * 100) if r > 0 else 0)

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(name="收入", x=month_labels, y=rev, marker_color="#2F5496", opacity=0.7), secondary_y=False)
    fig.add_trace(go.Bar(name="成本", x=month_labels, y=cost, marker_color="#ED7D31", opacity=0.7), secondary_y=False)
    fig.add_trace(go.Scatter(
        name="毛利率", x=month_labels, y=margin,
        line=dict(color="#70AD47", width=2.5), mode="lines+markers",
        text=[f"{v:.1f}%" for v in margin], textposition="top center",
    ), secondary_y=True)

    fig.update_layout(
        title=dict(text=f"{year}年 月度收入/成本/毛利率", y=0.97),
        barmode="group",
        legend=dict(orientation="h", yanchor="top", y=-0.16, xanchor="center", x=0.5),
        height=460,
        margin=dict(t=80, b=95, l=60, r=60),
    )
    fig.update_yaxes(title_text="金额（万元）", secondary_y=False)
    fig.update_yaxes(title_text="毛利率 %", secondary_y=True)
    return fig


def cost_structure_chart(financials: dict[int, dict], year: int) -> go.Figure:
    """单年制造成本结构柱状图。"""
    f = financials.get(year)
    if not f:
        return go.Figure()

    cs = f.get("cost_structure", {})
    items = sorted(cs.items(), key=lambda x: x[1], reverse=True)
    labels = [k for k, v in items if v > 0]
    values = [v / 1e4 for k, v in items if v > 0]

    fig = go.Figure(go.Bar(
        x=labels, y=values,
        marker_color=[COLORS[i % len(COLORS)] for i in range(len(labels))],
        text=[f"{v:,.0f}万" for v in values], textposition="outside",
    ))
    fig.update_layout(
        title=dict(text=f"{year}年 制造成本结构", y=0.97),
        yaxis_title="金额（万元）",
        height=420,
        margin=dict(t=80, b=115, l=60, r=60),
        xaxis_tickangle=-25,
    )
    return fig


def expense_breakdown_chart(financial: dict, sample_counts: dict[str, int] | None = None) -> go.Figure:
    """单年费用明细横向条形图（纵轴=费用科目，横轴=金额）。"""
    expenses = dict(financial.get("expenses", {}))
    if financial.get("rd_expense", 0) != 0:
        expenses["研发费用"] = financial["rd_expense"]
    if financial.get("financial_expense", 0) != 0:
        expenses["财务费用(汇兑)"] = financial["financial_expense"]
    if financial.get("tax_surcharge", 0) != 0:
        expenses["税金及附加"] = financial["tax_surcharge"]

    items = sorted(expenses.items(), key=lambda x: x[1])  # 升序，大的在上面
    labels = [k for k, v in items]
    values = [v / 1e4 for k, v in items]
    total = sum(values) or 1
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        y=labels,
        x=values,
        orientation='h',
        marker_color="#4472C4",
        text=[f"{v:,.1f}万" for v in values],
        textposition="outside",
        customdata=[[int((sample_counts or {}).get(str(label), 0) or 0)] for label in labels],
        hovertemplate=(
            "费用类别=%{y}<br>"
            "金额=%{x:,.1f}万<br>"
            "已入库凭证=%{customdata[0]:,}<extra></extra>"
        ),
        name="金额",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        y=labels,
        x=[v / total * 100 for v in values],
        mode="lines+markers+text",
        line=dict(color="#F97316", width=3),
        marker=dict(size=8),
        text=[f"{v / total * 100:.1f}%" for v in values],
        textposition="middle right",
        name="占比",
        hovertemplate="费用类别=%{y}<br>占比=%{x:.1f}%<extra></extra>",
    ), secondary_y=True)
    fig.update_layout(
        title=dict(text=f"{financial.get('year', '')}年 费用明细", y=0.98, font=dict(size=18)),
        yaxis_title="",
        font=dict(size=13),
        height=max(450, min(850, len(labels) * 36 + 150)),
        margin=dict(t=80, b=50, l=140, r=90),
    )
    fig.update_xaxes(title_text="金额（万元）", tickfont=dict(size=11))
    fig.update_yaxes(title_text="费用科目", autorange="reversed", secondary_y=False, tickfont=dict(size=12))
    fig.update_yaxes(title_text="占比 %", secondary_y=True, rangemode="tozero")
    fig.update_traces(textfont=dict(size=11))
    return fig


def cross_year_expense_compare_chart(expense_df: pd.DataFrame) -> go.Figure:
    """同一费用类别跨年对比横向条形图（纵轴=费用科目，横轴=金额）。"""
    if expense_df.empty:
        return go.Figure().update_layout(title="暂无跨年费用对比数据")

    data = expense_df.copy()
    data["年份"] = data["年份"].astype(str)
    fig = go.Figure()
    years = sorted(data["年份"].unique())
    for i, year in enumerate(years):
        year_df = data[data["年份"] == year].copy()
        if year_df.empty:
            continue
        year_df["_pct"] = year_df["金额"] / year_df["金额"].sum() * 100 if year_df["金额"].sum() else 0
        fig.add_trace(go.Bar(
            name=year,
            x=year_df["金额"],
            y=year_df["费用类别"],
            orientation="h",
            marker_color=COLORS[i % len(COLORS)],
            customdata=year_df["年份"],
            text=[f"{v/1e4:,.1f}万 ({p:.0f}%)" for v, p in zip(year_df["金额"], year_df["_pct"])],
            textposition="outside",
            textfont=dict(size=11),
            hovertemplate="费用类别=%{y}<br>金额=%{x:,.0f}元<br>年份=%{customdata}<extra></extra>",
        ))
    categories = data["费用类别"].nunique()
    fig.update_layout(
        title=dict(text="同一费用类别跨年对比", y=0.98, font=dict(size=18)),
        xaxis_title="金额（元）",
        yaxis_title="",
        font=dict(size=13),
        clickmode="event+select",
        height=max(450, min(850, categories * 45 + 150)),
        margin=dict(t=80, b=50, l=140, r=80),
        legend=dict(orientation="h", yanchor="top", y=-0.12, font=dict(size=12)),
    )
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=12))
    fig.update_xaxes(tickfont=dict(size=11))
    fig.update_traces(textfont=dict(size=11))
    return fig


def audit_monthly_revenue_cost_chart(
    monthly_df: pd.DataFrame,
    year: int,
    category_label: str = "总计",
    sample_counts: dict[int, int] | None = None,
) -> go.Figure:
    """净收入和净成本双柱状图，叠加毛利折线。"""
    if monthly_df.empty:
        return go.Figure().update_layout(title="暂无收入/成本数据")

    title_suffix = "" if category_label == "总计" else f"（{category_label}）"
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    month_labels = [f"{int(m)}月" for m in monthly_df["月份"]]
    fig.add_trace(go.Bar(
        name="净收入",
        x=month_labels,
        y=monthly_df["净收入"] / 1e4,
        marker_color="#2F5496",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" for v in monthly_df["净收入"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="净成本",
        x=month_labels,
        y=-monthly_df["净成本影响"] / 1e4,
        marker_color="#C55A11",
        opacity=0.86,
        text=[f"{-v/1e4:,.0f}万" for v in monthly_df["净成本影响"]],
        textposition="outside",
    ))

    fig.add_trace(go.Scatter(
        name="毛利",
        x=month_labels,
        y=monthly_df["毛利"] / 1e4,
        mode="lines+markers",
        line=dict(color="#2E7D32", width=3),
        marker=dict(size=7),
        text=[f"{v/1e4:,.0f}万" for v in monthly_df["毛利"]],
        textposition="top center",
    ))

    fig.add_hline(y=0, line_width=1, line_color="#666")
    if sample_counts:
        max_y = max(
            [0]
            + (monthly_df["净收入"] / 1e4).abs().tolist()
            + (-monthly_df["净成本影响"] / 1e4).abs().tolist()
            + (monthly_df["毛利"] / 1e4).abs().tolist()
        )
        marker_y = max_y * 1.12 if max_y else 1
        marked_months = [m for m in monthly_df["月份"].astype(int).tolist() if sample_counts.get(m, 0)]
        if marked_months:
            fig.add_trace(go.Scatter(
                name="已入库样本",
                x=[f"{m}月" for m in marked_months],
                y=[marker_y] * len(marked_months),
                mode="markers+text",
                marker=dict(color="#16A34A", size=9, symbol="diamond"),
                text=[f"{sample_counts[m]}个" for m in marked_months],
                textposition="top center",
                hovertemplate="月份=%{x}<br>已入库凭证=%{text}<extra></extra>",
            ))
    fig.update_layout(
        title=dict(text=f"{year}年 净收入 / 净成本月度对比{title_suffix}", y=0.97),
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        yaxis_title="金额（万元）",
        clickmode="event+select",
        height=470,
        margin=dict(t=90, b=45),
    )
    return fig


def audit_multi_year_overview_chart(scope_df: pd.DataFrame, category_label: str = "总计") -> go.Figure:
    """总览页跨年收入、成本、毛利和异常方向金额对比。"""
    if scope_df.empty:
        return go.Figure().update_layout(title="暂无跨年审计总览数据")

    data = scope_df.copy()
    data["年份"] = data["年份"].astype(str)
    if "净成本影响(万)" in data.columns:
        data["净成本(万)"] = -data["净成本影响(万)"]
    else:
        data["净成本(万)"] = 0

    title_suffix = "" if category_label == "总计" else f"（{category_label}）"
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="净收入",
        x=data["年份"],
        y=data["净收入(万)"],
        marker_color="#2F5496",
        opacity=0.86,
        text=[f"{v:,.0f}万" for v in data["净收入(万)"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="净成本",
        x=data["年份"],
        y=data["净成本(万)"],
        marker_color="#C55A11",
        opacity=0.86,
        text=[f"{v:,.0f}万" for v in data["净成本(万)"]],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="毛利",
        x=data["年份"],
        y=data["毛利(万)"],
        mode="lines+markers",
        line=dict(color="#2E7D32", width=3),
        marker=dict(size=8),
        text=[f"{v:,.0f}万" for v in data["毛利(万)"]],
        textposition="top center",
    ))
    fig.add_trace(go.Scatter(
        name="异常方向金额",
        x=data["年份"],
        y=data["异常方向金额(万)"],
        mode="lines+markers",
        line=dict(color="#B00020", width=2, dash="dot"),
        marker=dict(size=8, symbol="diamond"),
        text=[f"{v:,.0f}万" if v else "" for v in data["异常方向金额(万)"]],
        textposition="bottom center",
    ))

    fig.add_hline(y=0, line_width=1, line_color="#666")
    fig.update_layout(
        title=dict(text=f"所有已上传年份 收入 / 成本 / 毛利 / 异常方向对比{title_suffix}", y=0.97),
        yaxis_title="金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        height=420,
        margin=dict(t=85, b=45, l=70, r=40),
        uniformtext=dict(mode="hide", minsize=10),
    )
    return fig


def audit_income_cost_abnormal_chart(
    monthly_df: pd.DataFrame,
    year: int,
    category_label: str = "总计",
    sample_counts: dict[int, int] | None = None,
) -> go.Figure:
    """收入S和成本H异常方向双柱状图。"""
    if monthly_df.empty:
        return go.Figure().update_layout(title="暂无异常方向数据")

    title_suffix = "" if category_label == "总计" else f"（{category_label}）"
    month_labels = [f"{int(m)}月" for m in monthly_df["月份"]]
    income_s = monthly_df["收入S影响"].abs()
    cost_h = monthly_df["成本H影响"].abs()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="收入S",
        x=month_labels,
        y=income_s / 1e4,
        marker_color="#8FAADC",
        opacity=0.88,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in income_s],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="成本H",
        x=month_labels,
        y=cost_h / 1e4,
        marker_color="#F4B183",
        opacity=0.88,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in cost_h],
        textposition="outside",
    ))
    if sample_counts:
        max_y = max([0] + (income_s / 1e4).tolist() + (cost_h / 1e4).tolist())
        marker_y = max_y * 1.12 if max_y else 1
        marked_months = [m for m in monthly_df["月份"].astype(int).tolist() if sample_counts.get(m, 0)]
        if marked_months:
            fig.add_trace(go.Scatter(
                name="已入库样本",
                x=[f"{m}月" for m in marked_months],
                y=[marker_y] * len(marked_months),
                mode="markers+text",
                marker=dict(color="#16A34A", size=9, symbol="diamond"),
                text=[f"{sample_counts[m]}个" for m in marked_months],
                textposition="top center",
                hovertemplate="月份=%{x}<br>已入库凭证=%{text}<extra></extra>",
            ))
    fig.update_layout(
        title=dict(text=f"{year}年 收入S / 成本H异常方向{title_suffix}", y=0.97),
        yaxis_title="绝对金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        clickmode="event+select",
        height=340,
        margin=dict(t=85, b=45),
    )
    return fig


def customer_revenue_top_chart(customer_df: pd.DataFrame, year: int) -> go.Figure:
    """客户收入横向柱状图。"""
    if customer_df.empty:
        return go.Figure().update_layout(title="暂无客户收入数据")

    data = customer_df.sort_values("净收入", ascending=True)
    sample_counts = customer_df.attrs.get("sample_counts", {}) or {}
    customdata = pd.DataFrame({
        "收入H影响": data["收入H影响"] / 1e4,
        "收入S影响": data["收入S影响"] / 1e4,
        "净收入": data["净收入"] / 1e4,
        "应收S发生额": data["应收S发生额"] / 1e4,
        "占比": data["占比"],
        "已入库凭证": [int(sample_counts.get(str(name), 0) or 0) for name in data["客户"]],
    })
    fig = go.Figure(go.Bar(
        x=data["净收入"] / 1e4,
        y=data["客户"],
        orientation="h",
        marker_color="#2F5496",
        text=[f"{v/1e4:,.0f}万" for v in data["净收入"]],
        textposition="outside",
        customdata=customdata,
        hovertemplate=(
            "客户=%{y}<br>"
            "净收入=%{x:,.0f}万<br>"
            "收入H影响=%{customdata[0]:,.0f}万<br>"
            "收入S影响=%{customdata[1]:,.0f}万<br>"
            "应收S发生额=%{customdata[3]:,.0f}万<br>"
            "占比=%{customdata[4]:.1%}<br>"
            "已入库凭证=%{customdata[5]:,}<extra></extra>"
        ),
    ))
    if sample_counts:
        fig.add_trace(go.Scatter(
            name="已入库样本",
            x=[0] * len(data),
            y=data["客户"],
            mode="text",
            text=[
                f"已入库{int(sample_counts.get(str(name), 0))}个"
                if int(sample_counts.get(str(name), 0) or 0)
                else ""
                for name in data["客户"]
            ],
            textposition="middle right",
            textfont=dict(color="#16A34A", size=11),
            hoverinfo="skip",
        ))
    fig.update_layout(
        title=dict(text=f"{year}年 客户收入分布", y=0.97),
        xaxis_title="净收入（万元，公司代码货币）",
        clickmode="event+select",
        height=max(380, min(920, len(data) * 30 + 130)),
        margin=dict(t=80, b=40, l=180),
    )
    return fig


def supplier_payables_top_chart(supplier_df: pd.DataFrame, year: int) -> go.Figure:
    """供应商应付账款发生额 Top10 横向柱状图。"""
    if supplier_df.empty:
        return go.Figure().update_layout(title="暂无供应商应付数据")

    data = supplier_df.sort_values("应付H发生额", ascending=True)
    sample_counts = supplier_df.attrs.get("sample_counts", {}) or {}
    customdata = pd.DataFrame({
        "应付S发生额": data["应付S发生额"] / 1e4,
        "占比": data["占比"],
        "已入库凭证": [int(sample_counts.get(str(name), 0) or 0) for name in data["供应商"]],
    })
    fig = go.Figure(go.Bar(
        x=data["应付H发生额"] / 1e4,
        y=data["供应商"],
        orientation="h",
        marker_color="#9E480E",
        text=[f"{v/1e4:,.0f}万" for v in data["应付H发生额"]],
        textposition="outside",
        customdata=customdata,
        hovertemplate=(
            "供应商=%{y}<br>"
            "应付H发生额=%{x:,.0f}万<br>"
            "应付S发生额=%{customdata[0]:,.0f}万<br>"
            "占比=%{customdata[1]:.1%}<br>"
            "已入库凭证=%{customdata[2]:,}<extra></extra>"
        ),
    ))
    if sample_counts:
        fig.add_trace(go.Scatter(
            name="已入库样本",
            x=[0] * len(data),
            y=data["供应商"],
            mode="text",
            text=[
                f"已入库{int(sample_counts.get(str(name), 0))}个"
                if int(sample_counts.get(str(name), 0) or 0)
                else ""
                for name in data["供应商"]
            ],
            textposition="middle right",
            textfont=dict(color="#16A34A", size=11),
            hoverinfo="skip",
        ))
    fig.update_layout(
        title=dict(text=f"{year}年 供应商应付分布", y=0.97),
        xaxis_title="应付H发生额（万元，公司代码货币）",
        clickmode="event+select",
        height=max(380, min(920, len(data) * 30 + 130)),
        margin=dict(t=80, b=40, l=180),
    )
    return fig


def ap_accrual_monthly_chart(monthly_df: pd.DataFrame, year: int) -> go.Figure:
    """应付账款暂估月度贷方增加/借方减少双柱，叠加净额折线。"""
    if monthly_df.empty:
        return go.Figure().update_layout(title="暂无应付账款暂估数据")

    month_labels = [f"{int(m)}月" for m in monthly_df["月份"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="暂估贷方增加",
        x=month_labels,
        y=monthly_df["暂估贷方增加"] / 1e4,
        marker_color="#7F6000",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["暂估贷方增加"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="暂估借方减少",
        x=month_labels,
        y=monthly_df["暂估借方减少"] / 1e4,
        marker_color="#B7A16A",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["暂估借方减少"]],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="暂估净额",
        x=month_labels,
        y=monthly_df["暂估净额"] / 1e4,
        mode="lines+markers",
        line=dict(color="#2F5496", width=3),
        marker=dict(size=7),
        text=[f"{v/1e4:,.0f}万" for v in monthly_df["暂估净额"]],
        textposition="top center",
    ))
    fig.add_hline(y=0, line_width=1, line_color="#666")
    fig.update_layout(
        title=dict(text=f"{year}年 应付账款暂估贷方增加 / 借方减少月度对比", y=0.97),
        yaxis_title="金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        clickmode="event+select",
        height=430,
        margin=dict(t=85, b=45),
    )
    return fig


def other_receivable_monthly_chart(monthly_df: pd.DataFrame, year: int) -> go.Figure:
    """其他应收款月度 S/H 双柱，叠加净额折线。"""
    if monthly_df.empty:
        return go.Figure().update_layout(title="暂无其他应收款数据")

    month_labels = [f"{int(m)}月" for m in monthly_df["月份"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="其他应收S发生额",
        x=month_labels,
        y=monthly_df["其他应收S发生额"] / 1e4,
        marker_color="#2F5496",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["其他应收S发生额"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="其他应收H发生额",
        x=month_labels,
        y=monthly_df["其他应收H发生额"] / 1e4,
        marker_color="#ED7D31",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["其他应收H发生额"]],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="其他应收净额",
        x=month_labels,
        y=monthly_df["其他应收净额"] / 1e4,
        mode="lines+markers",
        line=dict(color="#2E7D32", width=3),
        marker=dict(size=7),
        text=[f"{v/1e4:,.0f}万" for v in monthly_df["其他应收净额"]],
        textposition="top center",
    ))
    fig.add_hline(y=0, line_width=1, line_color="#666")
    fig.update_layout(
        title=dict(text=f"{year}年 其他应收款 S / H 月度对比", y=0.97),
        yaxis_title="金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        clickmode="event+select",
        height=430,
        margin=dict(t=85, b=45),
    )
    return fig


def other_payable_monthly_chart(monthly_df: pd.DataFrame, year: int) -> go.Figure:
    """其他应付款月度预提/核销双柱，叠加净值折线。"""
    if monthly_df.empty:
        return go.Figure().update_layout(title="暂无其他应付款数据")

    month_labels = [f"{int(m)}月" for m in monthly_df["月份"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="其他应付预提H",
        x=month_labels,
        y=monthly_df["其他应付预提H"] / 1e4,
        marker_color="#9E480E",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["其他应付预提H"]],
        textposition="outside",
    ))
    fig.add_trace(go.Bar(
        name="其他应付核销S",
        x=month_labels,
        y=monthly_df["其他应付核销S"] / 1e4,
        marker_color="#B7A16A",
        opacity=0.86,
        text=[f"{v/1e4:,.0f}万" if v else "" for v in monthly_df["其他应付核销S"]],
        textposition="outside",
    ))
    fig.add_trace(go.Scatter(
        name="其他应付净值",
        x=month_labels,
        y=monthly_df["其他应付净值"] / 1e4,
        mode="lines+markers",
        line=dict(color="#2F5496", width=3),
        marker=dict(size=7),
        text=[f"{v/1e4:,.0f}万" for v in monthly_df["其他应付净值"]],
        textposition="top center",
    ))
    fig.add_hline(y=0, line_width=1, line_color="#666")
    fig.update_layout(
        title=dict(text=f"{year}年 其他应付款预提 / 核销月度对比", y=0.97),
        yaxis_title="金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        clickmode="event+select",
        height=430,
        margin=dict(t=85, b=45),
    )
    return fig


def ap_accrual_supplier_share_chart(share_df: pd.DataFrame, title: str) -> go.Figure:
    """应付账款暂估点击后的供应商贷方增加/借方减少双柱对比。"""
    if share_df.empty:
        return go.Figure().update_layout(title="暂无供应商暂估数据")

    data = share_df.iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="暂估贷方增加",
        x=data["暂估贷方增加"] / 1e4,
        y=data["供应商"],
        orientation="h",
        marker_color="#7F6000",
        text=[f"{v/1e4:,.0f}万" if v else "" for v in data["暂估贷方增加"]],
        textposition="outside",
        customdata=data[["贷方占比"]],
        hovertemplate="供应商=%{y}<br>贷方增加=%{x:,.0f}万<br>贷方占比=%{customdata[0]:.1%}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        name="暂估借方减少",
        x=data["暂估借方减少"] / 1e4,
        y=data["供应商"],
        orientation="h",
        marker_color="#B7A16A",
        text=[f"{v/1e4:,.0f}万" if v else "" for v in data["暂估借方减少"]],
        textposition="outside",
        customdata=data[["借方占比"]],
        hovertemplate="供应商=%{y}<br>借方减少=%{x:,.0f}万<br>借方占比=%{customdata[0]:.1%}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        name="暂估净额",
        x=data["暂估净额"] / 1e4,
        y=data["供应商"],
        mode="markers",
        marker=dict(color="#2F5496", size=9, symbol="diamond"),
        customdata=data[["净额占比"]],
        hovertemplate="供应商=%{y}<br>净额=%{x:,.0f}万<br>净额占比=%{customdata[0]:.1%}<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1, line_color="#666")
    fig.update_layout(
        title=dict(text=title, y=0.97),
        xaxis_title="金额（万元，公司代码货币）",
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.05),
        clickmode="event+select",
        height=max(320, len(data) * 32 + 120),
        margin=dict(t=85, b=40, l=180),
    )
    return fig

# ── 统计画像数据辅助表 ──

def profile_amount_percentile_table(profile: dict) -> "pd.DataFrame":
    amt = profile.get("amount_distribution", {})
    rows = []
    for key, label in [("row_level", "行级金额"), ("voucher_level", "凭证级金额")]:
        data = amt.get(key, {})
        if data:
            rows.append({
                "口径": label,
                "P25": data.get("p25", 0),
                "P50": data.get("p50", 0),
                "P75": data.get("p75", 0),
                "P90": data.get("p90", 0),
                "P95": data.get("p95", 0),
                "P99": data.get("p99", 0),
                "最大值": data.get("max", 0),
                "均值": data.get("mean", 0),
            })
    return pd.DataFrame(rows)


def profile_temporal_table(profile: dict) -> "pd.DataFrame":
    tp = profile.get("temporal_patterns", {})
    monthly_count = tp.get("monthly_count", {})
    monthly_amount = tp.get("monthly_amount", {})
    month_end = tp.get("month_end_concentration", {})
    rows = []
    for month in range(1, 13):
        if month not in monthly_count and month not in monthly_amount:
            continue
        rows.append({
            "月份": f"{month}月",
            "凭证行数": monthly_count.get(month, 0),
            "绝对金额": monthly_amount.get(month, 0),
            "月末5天占比": month_end.get(month),
        })
    return pd.DataFrame(rows)


def profile_benford_table(profile: dict) -> "pd.DataFrame":
    benford = profile.get("benford_first_digit", {})
    observed = benford.get("observed", {})
    expected = benford.get("expected", {})
    deviation = benford.get("deviation", {})
    rows = []
    for digit in range(1, 10):
        obs = observed.get(digit, observed.get(str(digit), 0))
        exp = expected.get(digit, expected.get(str(digit), 0))
        dev = deviation.get(digit, deviation.get(str(digit), (obs - exp) * 100))
        rows.append({
            "首位数字": digit,
            "实际频率": round(obs * 100, 2),
            "理论频率": round(exp * 100, 2),
            "偏差": round(dev, 2),
        })
    return pd.DataFrame(rows)
