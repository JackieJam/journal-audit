"""LLM 抽样建议的逻辑、文本渲染与取数工具。

两层内容：
1. 无状态纯函数：缓存键构造、payload 记录裁剪、模型回传条件归一化、模块归属判定，
   以及"建议抽样什么 / 当前回查逻辑"的中文文本。可直接单元测试。
2. 推荐 → 明细取数（detail_for_recommendation / backfill_recommendation_condition /
   normalise_label）：读 st.session_state.year_map，并接收共享的 @st.cache_data 视图
   缓存 build_audit_cache（仍在 app.py，因分析页签复用）作为注入参数。由 AppTest
   基线（test_app_interaction）覆盖。

注：真正的 UI 编排器（_render_candidate_recommendations_for_module 及其 payload 构造、
LLM 并发调用、kb 持久化与配额跟踪）仍在 app.py，待专门一轮再抽。

app.py 通过 alias 保留原调用名（_unified_llm_key / _detail_for_recommendation 等）；
其中 _unified_llm_key 按原 helper key 注入给统计概况子页签，_detail_for_recommendation
由 functools.partial 预绑定 build_audit_cache，调用点签名与行为零变化。
"""

from __future__ import annotations

import re
from typing import Any, Callable

import pandas as pd
import streamlit as st

from modules.visual_analysis import (
    build_ap_accrual_entry_top10_from_work,
    build_cost_focus_entries_from_work,
    build_customer_revenue_entry_top10_from_work,
    build_expense_entry_top10_from_work,
    build_income_cost_abnormal_entry_top10_from_work,
    build_monthly_revenue_cost_entry_top10_from_work,
    build_other_payable_entry_top10_from_work,
    build_other_receivable_entry_top10_from_work,
    build_revenue_focus_entries_from_work,
    build_supplier_payable_entry_top10_from_work,
)


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


# ── 推荐 → 明细数据路径（group 6 step 2）──
# detail_for_recommendation 直接读 st.session_state.year_map，并接收共享的
# @st.cache_data 视图缓存 build_audit_cache（仍在 app.py，因分析页签复用），
# 由 app.py functools.partial 预绑定，调用点签名不变。
def detail_for_recommendation(
    condition: dict[str, Any],
    category: str,
    *,
    build_audit_cache: Callable[..., dict[str, pd.DataFrame]],
) -> pd.DataFrame:
    condition = normalise_recommendation_condition(condition)
    kind = str(condition.get("kind", ""))
    year = condition.get("year")
    if year is None:
        return pd.DataFrame()
    try:
        year = int(year)
    except (TypeError, ValueError):
        return pd.DataFrame()
    if year not in st.session_state.year_map:
        return pd.DataFrame()
    work = build_audit_cache(st.session_state.year_map[year])["work"]
    month = condition.get("month")
    try:
        month = int(month) if month not in (None, "") else None
    except (TypeError, ValueError):
        month = None

    if kind == "revenue_customer_month":
        return build_revenue_focus_entries_from_work(
            work,
            customer=condition.get("customer") or None,
            material_group=condition.get("material_group") or None,
            month=month,
            category=category,
        )
    if kind == "monthly_income_cost":
        months = condition.get("months") or ([month] if month is not None else [])
        if not months:
            return pd.DataFrame()
        metric = str(condition.get("metric") or "revenue")
        frames = [
            build_monthly_revenue_cost_entry_top10_from_work(
                work,
                month=int(m),
                metric=metric,
                category=category,
            )
            for m in months
        ]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if kind == "income_cost_abnormal":
        months = condition.get("months") or ([month] if month is not None else [])
        if not months:
            return pd.DataFrame()
        direction = str(condition.get("direction") or "")
        frames = [
            build_income_cost_abnormal_entry_top10_from_work(
                work,
                month=int(m),
                direction=direction,
                category=category,
            )
            for m in months
        ]
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if kind == "customer_revenue":
        customer = str(condition.get("customer") or "")
        detail = build_customer_revenue_entry_top10_from_work(work, customer=customer)
        if not detail.empty:
            return detail
        customer_norm = normalise_label(customer)
        if not customer_norm:
            return pd.DataFrame()
        detail = work[
            work["_acct4"].isin(["6001", "6051"])
            & (work["_customer_display"].astype(str).map(normalise_label) == customer_norm)
        ].copy()
        if detail.empty:
            return pd.DataFrame()
        detail["收入影响"] = detail["_amount_raw"]
        return detail.sort_values("_amount_abs", ascending=False).pipe(lambda d: d[[c for c in [
            "凭证编号", "过账日期", "行项目", "凭证类型", "总账科目", "_account_name", "借/贷标识",
            "公司代码货币价值", "凭证货币价值", "收入影响", "用户名", "_customer_display", "_vendor_display",
            "_material_group_display", "_material_display", "_cost_center_display", "_header_text", "_line_text",
            "_reversal_text"
        ] if c in d.columns]]).rename(columns={
            "_account_name": "科目名称", "_customer_display": "客户", "_vendor_display": "供应商",
            "_material_group_display": "物料组", "_material_display": "物料", "_cost_center_display": "成本中心",
            "_header_text": "凭证抬头摘要", "_line_text": "摘要", "_reversal_text": "反记账/冲销标识",
        })
    if kind == "revenue_customer_material":
        return build_revenue_focus_entries_from_work(
            work,
            customer=condition.get("customer") or None,
            material_group=condition.get("material_group") or None,
            month=month,
            category=category,
        )
    if kind == "cost_material_account":
        return build_cost_focus_entries_from_work(
            work,
            material_group=condition.get("material_group") or None,
            cost_account=condition.get("cost_account") or None,
            month=month,
            category=category,
        )
    if kind == "supplier_payable":
        supplier = str(condition.get("supplier") or "")
        detail = build_supplier_payable_entry_top10_from_work(work, supplier=supplier)
        if not detail.empty:
            return detail
        supplier_norm = normalise_label(supplier)
        if not supplier_norm:
            return pd.DataFrame()
        detail = work[
            (work["_acct4"] == "2202")
            & (work["_vendor_display"].astype(str).map(normalise_label) == supplier_norm)
        ].copy()
        if detail.empty:
            return pd.DataFrame()
        detail["应付发生额"] = detail["_amount_raw"].where(detail["_dc"] == "S", -detail["_amount_raw"])
        detail = detail.sort_values("_amount_abs", ascending=False)
        return detail[[
            c for c in [
                "凭证编号", "过账日期", "行项目", "凭证类型", "总账科目", "_account_name", "借/贷标识",
                "公司代码货币价值", "凭证货币价值", "应付发生额", "用户名", "_customer_display", "_vendor_display",
                "_material_group_display", "_material_display", "_cost_center_display", "_header_text", "_line_text",
                "_reversal_text"
            ] if c in detail.columns
        ]].rename(columns={
            "_account_name": "科目名称", "_customer_display": "客户", "_vendor_display": "供应商",
            "_material_group_display": "物料组", "_material_display": "物料", "_cost_center_display": "成本中心",
            "_header_text": "凭证抬头摘要", "_line_text": "摘要", "_reversal_text": "反记账/冲销标识",
        })
    if kind == "expense_category":
        expense_category = str(condition.get("expense_category") or "")
        if not expense_category:
            return pd.DataFrame()
        return build_expense_entry_top10_from_work(work, expense_category)
    if kind == "ap_accrual_month":
        if month is None:
            return pd.DataFrame()
        direction = str(condition.get("direction") or "net")
        return build_ap_accrual_entry_top10_from_work(work, month=month, direction=direction)
    if kind == "ap_accrual_supplier":
        if month is None:
            return pd.DataFrame()
        return build_ap_accrual_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
            supplier=str(condition.get("supplier") or ""),
        )
    if kind == "other_receivable_month":
        if month is None:
            return pd.DataFrame()
        return build_other_receivable_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
        )
    if kind == "other_payable_month":
        if month is None:
            return pd.DataFrame()
        return build_other_payable_entry_top10_from_work(
            work,
            month=month,
            direction=str(condition.get("direction") or "net"),
        )
    if kind == "adjustment_voucher":
        voucher_id = str(condition.get("voucher_id") or "")
        if not voucher_id:
            return pd.DataFrame()
        return work.loc[work["凭证编号"].astype(str) == voucher_id].copy()

    if kind == "cross_year_finding":
        years_list = condition.get("years") or [year]
        cat = str(condition.get("category") or "")
        cat_lower = cat.lower()
        # 匹配跨年稽核发现中的关键词
        keyword_map = {
            "预提": ["预提", "计提", "accrual"],
            "收入": ["收入", "revenue"],
            "突增": ["突增", "surge", "spike"],
            "年末": ["年末", "year.end", "december"],
            "冲回": ["冲回", "冲销", "reversal"],
        }
        keywords = []
        for kw_group, kws in keyword_map.items():
            if any(k in cat_lower for k in kws):
                keywords.extend(kws)
        if not keywords:
            keywords = [cat]
        frames = []
        for y in years_list:
            try:
                y = int(y)
            except (TypeError, ValueError):
                continue
            if y in st.session_state.year_map:
                y_work = build_audit_cache(st.session_state.year_map[y])["work"]
                mask = pd.Series(False, index=y_work.index)
                for kw in keywords:
                    if "文本" in y_work.columns:
                        mask |= y_work["文本"].astype(str).str.contains(kw, case=False, na=False)
                if mask.any():
                    frames.append(y_work[mask].copy())
        if frames:
            return pd.concat(frames, ignore_index=True)
        # fallback: 返回对应年份的数据
        for y in years_list:
            try:
                y = int(y)
            except (TypeError, ValueError):
                continue
            if y in st.session_state.year_map:
                return build_audit_cache(st.session_state.year_map[y])["work"].head(50).copy()
        return pd.DataFrame()

    if kind == "profile_signal":
        signal = str(condition.get("signal") or condition.get("category") or "")
        signal_lower = signal.lower()
        # 匹配统计画像信号关键词
        if any(k in signal_lower for k in ["假日", "周末", "weekend", "holiday"]):
            mask = (work["_dow"] >= 5) if "_dow" in work.columns else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["月末", "month.end", "period.end", "年底", "年末"]):
            mask = (work["_is_month_end"]) if "_is_month_end" in work.columns else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["用户", "user", "concentration", "集中"]):
            top_users = work["用户名"].value_counts().head(5).index.tolist() if "用户名" in work.columns else []
            mask = work["用户名"].isin(top_users) if top_users else pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["大额", "large", "整数", "round"]):
            amt_threshold = 1e6
            if "_amount_abs" in work.columns:
                mask = work["_amount_abs"] >= amt_threshold
            else:
                mask = pd.Series(False, index=work.index)
        elif any(k in signal_lower for k in ["冲销", "reversal", "反记账", "调账"]):
            mask = work["_reversal_text"].astype(str).str.strip() != "" if "_reversal_text" in work.columns else pd.Series(False, index=work.index)
        else:
            # 默认返回当前年份金额最大的凭证
            if "_amount_abs" in work.columns:
                return work.nlargest(min(50, len(work)), "_amount_abs").copy()
            return work.head(50).copy()
        if mask.any():
            return work[mask].head(100).copy()
        return work.head(50).copy()

    return pd.DataFrame()


def normalise_label(value: str) -> str:
    return str(value or "").strip().replace(" ", "").replace("\n", "").replace("\t", "")


def backfill_recommendation_condition(
    rec: dict[str, Any],
    category: str,
    module_filter: str,
) -> dict[str, Any]:
    condition = normalise_recommendation_condition(rec.get("condition") or {})
    title = str(rec.get("title") or "")
    reason = str(rec.get("reason") or "")
    text = f"{title}\n{reason}"

    if module_filter == "收入成本":
        if not condition.get("kind"):
            customer_match = re.search(r"客户([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+?)收入", text)
            if customer_match:
                condition["kind"] = "customer_revenue"
                condition["customer"] = customer_match.group(1).strip()
        if not condition.get("year"):
            year_match = re.search(r"(20\\d{2})年", text)
            if year_match:
                condition["year"] = int(year_match.group(1))
        if not condition.get("kind") and "毛利" in text:
            months = [int(m) for m in re.findall(r"(\\d{1,2})月", text)]
            if months:
                condition["kind"] = "monthly_income_cost"
                condition["metric"] = "gross"
                condition["month"] = months[0]
                condition["months"] = months
        if not condition.get("kind") and "供应商" in text:
            supplier_match = re.search(r"供应商([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+?)(应付|暂估|收入|成本)", text)
            if supplier_match:
                condition["kind"] = "supplier_payable"
                condition["supplier"] = supplier_match.group(1).strip()
    elif module_filter == "费用":
        if not condition.get("kind"):
            expense_match = re.search(r"费用类别\\s*([A-Za-z0-9_\\-\\s\\u4e00-\\u9fff（）()]+)", text)
            if expense_match:
                condition["kind"] = "expense_category"
                condition["expense_category"] = expense_match.group(1).strip()

    elif module_filter == "跨年交叉稽核":
        if not condition.get("kind"):
            condition["kind"] = "cross_year_finding"
        if not condition.get("category"):
            condition["category"] = title
        if not condition.get("years"):
            years_found = sorted(set(int(y) for y in re.findall(r"(20\d{2})", text)))
            condition["years"] = years_found if years_found else list(st.session_state.year_map.keys())
    elif module_filter == "统计画像":
        if not condition.get("kind"):
            condition["kind"] = "profile_signal"
        if not condition.get("signal"):
            condition["signal"] = title
        if not condition.get("year") and st.session_state.year_map:
            condition["year"] = max(st.session_state.year_map.keys())
    return normalise_recommendation_condition(condition)
