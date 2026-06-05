"""LLM 抽样建议的纯逻辑与文本渲染工具。

承载推荐（recommendation）相关的无状态逻辑：缓存键构造、payload 记录裁剪、
模型回传条件的归一化、模块归属判定，以及"建议抽样什么 / 当前回查逻辑"的中文文本。
均为纯函数，不依赖 st / session / kb / LLM 调用，可直接单元测试。

注：真正驱动这些逻辑的编排器（_render_candidate_recommendations_for_module 及其
payload / detail 构造、LLM 调用）仍在 app.py，因其深度耦合 session_state、共享的
@st.cache_data 视图缓存、知识库持久化与配额跟踪——待专门一轮（需真跑 app 验证）再抽。

app.py 通过 alias 保留原调用名（_unified_llm_key 等）；其中 _unified_llm_key 仍按
原 helper key 注入给统计概况子页签，行为零变化。
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def unified_llm_key(years: list[int], category: str) -> str:
    years_part = ",".join(str(year) for year in sorted(years))
    return f"unified::{years_part}::{category}"


def records_for_payload(df: pd.DataFrame, limit: int = 30) -> list[dict[str, Any]]:
    if df.empty:
        return []
    data = df.head(limit).copy()
    for col in data.columns:
        if pd.api.types.is_datetime64_any_dtype(data[col]):
            data[col] = data[col].dt.strftime("%Y-%m-%d")
    return data.to_dict("records")


def normalise_recommendation_condition(condition: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(condition or {})
    metric_map = {
        "净收入": "revenue",
        "收入": "revenue",
        "revenue": "revenue",
        "净成本": "cost",
        "成本": "cost",
        "cost": "cost",
        "毛利": "gross",
        "gross": "gross",
    }
    direction_map = {
        "收入S": "income_s",
        "收入S异常": "income_s",
        "income_s": "income_s",
        "成本H": "cost_h",
        "成本H异常": "cost_h",
        "cost_h": "cost_h",
        "借方": "debit",
        "贷方": "credit",
        "净额": "net",
        "冲销": "writeoff",
        "预提": "accrual",
    }
    metric = normalized.get("metric")
    if metric is not None:
        normalized["metric"] = metric_map.get(str(metric).strip(), str(metric).strip())
    direction = normalized.get("direction")
    if direction is not None:
        normalized["direction"] = direction_map.get(str(direction).strip(), str(direction).strip())
    month = normalized.get("month")
    months = normalized.get("months")
    if isinstance(months, list):
        cleaned_months = []
        for item in months:
            try:
                cleaned_months.append(int(str(item).replace("月", "").strip()))
            except (TypeError, ValueError):
                continue
        normalized["months"] = cleaned_months
    elif month is not None:
        try:
            normalized["month"] = int(str(month).replace("月", "").strip())
            normalized["months"] = [normalized["month"]]
        except (TypeError, ValueError):
            pass
    for key in ["customer", "supplier", "expense_category", "voucher_id"]:
        if normalized.get(key) is not None:
            normalized[key] = str(normalized.get(key)).strip()
    return normalized


def recommendation_matches_module(rec: dict[str, Any], module_filter: str) -> bool:
    source_module = str(rec.get("source_module", "") or "")
    source_view = str(rec.get("source_view", "") or "")
    condition = rec.get("condition") or {}
    kind = str(condition.get("kind", "") or "")

    if module_filter == "收入成本":
        return (
            "收入成本" in source_module
            or source_view in {"月度收入成本", "异常方向", "客户收入", "供应商应付"}
            or kind in {"monthly_income_cost", "income_cost_abnormal", "customer_revenue", "supplier_payable"}
        )
    if module_filter == "费用":
        return "费用" in source_module or source_view == "费用类别" or kind == "expense_category"
    if module_filter == "暂估往来":
        return (
            "暂估往来" in source_module
            or source_view in {"暂估月度", "暂估供应商", "其他应收", "其他应付"}
            or kind in {"ap_accrual_month", "ap_accrual_supplier", "other_receivable_month", "other_payable_month"}
        )
    if module_filter == "调账冲销":
        return "调账冲销" in source_module or source_view == "调账凭证" or kind == "adjustment_voucher"
    return True


def recommendation_target_text(rec: dict[str, Any]) -> str:
    condition = rec.get("condition") or {}
    kind = str(condition.get("kind", "") or "")
    year = condition.get("year")
    month = condition.get("month")
    if kind == "monthly_income_cost":
        metric_map = {"revenue": "净收入", "cost": "净成本", "gross": "毛利"}
        metric = metric_map.get(str(condition.get("metric") or "revenue"), "月度指标")
        return f"{year}年{month}月 {metric}"
    if kind == "income_cost_abnormal":
        direction = "收入S异常" if str(condition.get("direction")) == "income_s" else "成本H异常"
        return f"{year}年{month}月 {direction}"
    if kind == "customer_revenue":
        return f"{year}年 客户 {condition.get('customer', '')} 收入"
    if kind == "supplier_payable":
        return f"{year}年 供应商 {condition.get('supplier', '')} 应付"
    if kind == "expense_category":
        return f"{year}年 费用类别 {condition.get('expense_category', '')}"
    if kind == "ap_accrual_month":
        return f"{year}年{month}月 暂估往来"
    if kind == "ap_accrual_supplier":
        return f"{year}年{month}月 供应商 {condition.get('supplier', '')} 暂估"
    if kind == "other_receivable_month":
        return f"{year}年{month}月 其他应收"
    if kind == "other_payable_month":
        return f"{year}年{month}月 其他应付"
    if kind == "adjustment_voucher":
        return f"{year}年 调账凭证 {condition.get('voucher_id', '')}"
    return str(rec.get("title") or "未命名建议")


def recommendation_condition_text(condition: dict[str, Any], module_filter: str) -> str:
    condition = normalise_recommendation_condition(condition)
    kind = str(condition.get("kind", "") or "")
    year = condition.get("year")
    month = condition.get("month")
    months = condition.get("months") or ([] if month is None else [month])

    def _months_text(values: list[Any]) -> str:
        cleaned = []
        for item in values:
            try:
                cleaned.append(f"{int(item)}月")
            except (TypeError, ValueError):
                continue
        return "、".join(cleaned) if cleaned else "未指定月份"

    if module_filter == "收入成本":
        if kind == "monthly_income_cost":
            metric_label = {
                "revenue": "净收入",
                "cost": "净成本",
                "gross": "毛利",
            }.get(str(condition.get("metric") or ""), "月度指标")
            return f"按 {year} 年 {_months_text(months)} 的 {metric_label} 相关分录回查。"
        if kind == "income_cost_abnormal":
            direction_label = {
                "income_s": "收入借方异常",
                "cost_h": "成本贷方异常",
            }.get(str(condition.get("direction") or ""), "异常方向")
            return f"按 {year} 年 {_months_text(months)} 的 {direction_label} 分录回查。"
        if kind == "customer_revenue":
            return f"按 {year} 年客户“{condition.get('customer', '')}”的收入分录回查。"
        if kind == "supplier_payable":
            return f"按 {year} 年供应商“{condition.get('supplier', '')}”的应付分录回查。"
    if module_filter == "费用":
        if kind == "expense_category":
            return f"按 {year} 年费用类别“{condition.get('expense_category', '')}”的分录回查。"
    if module_filter == "暂估往来":
        if kind == "ap_accrual_month":
            direction_label = {
                "credit": "暂估贷方增加",
                "debit": "暂估借方减少",
                "net": "暂估净额",
            }.get(str(condition.get("direction") or ""), "暂估分录")
            return f"按 {year} 年 {month} 月的{direction_label}分录回查。"
        if kind == "ap_accrual_supplier":
            direction_label = {
                "credit": "暂估贷方增加",
                "debit": "暂估借方减少",
                "net": "暂估净额",
            }.get(str(condition.get("direction") or ""), "暂估分录")
            return f"按 {year} 年 {month} 月供应商“{condition.get('supplier', '')}”的{direction_label}分录回查。"
        if kind == "other_receivable_month":
            direction_label = {
                "debit": "其他应收借方发生额",
                "credit": "其他应收贷方发生额",
                "net": "其他应收净额",
            }.get(str(condition.get("direction") or ""), "其他应收分录")
            return f"按 {year} 年 {month} 月的{direction_label}回查。"
        if kind == "other_payable_month":
            direction_label = {
                "accrual": "其他应付预提",
                "writeoff": "其他应付核销",
                "net": "其他应付净值",
            }.get(str(condition.get("direction") or ""), "其他应付分录")
            return f"按 {year} 年 {month} 月的{direction_label}回查。"
    if module_filter == "调账冲销":
        if kind == "adjustment_voucher":
            return f"按 {year} 年凭证号“{condition.get('voucher_id', '')}”的整张凭证分录回查。"
    if module_filter == "跨年交叉稽核":
        if kind == "cross_year_finding":
            years = condition.get("years") or []
            year_text = "、".join(str(y) for y in years) if years else "相关年度"
            return f"按跨年异常“{condition.get('category', '')}”涉及的 {year_text} 年凭证回查。"
    if module_filter == "统计画像":
        if kind == "profile_signal":
            return "按统计画像识别出的异常特征对应分录回查。"
    return "按模型给出的筛选条件回查对应分录。"
