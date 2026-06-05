"""LLM 抽样建议的逻辑、文本渲染与取数工具。

两层内容：
1. 无状态纯函数：缓存键构造、payload 记录裁剪、模型回传条件归一化、模块归属判定，
   以及"建议抽样什么 / 当前回查逻辑"的中文文本。可直接单元测试。
2. 推荐 → 明细取数（detail_for_recommendation / backfill_recommendation_condition /
   normalise_label）：读 st.session_state.year_map，并接收共享的 @st.cache_data 视图
   缓存 build_audit_cache（仍在 app.py，因分析页签复用）作为注入参数。由 AppTest
   基线（test_app_interaction）覆盖。

3. payload 构造 + UI 编排器（group 6 step 3）：build_year_audit_analysis_payload /
   income_cost_focus_payload / build_income_cost_focus_payload(@st.cache_data) /
   audit_source_summary，以及 render_candidate_recommendations_for_module（含嵌套的
   建议入库与 LLM 并发生成闭包）+ render_unified_generation_controls。这些函数依赖若干
   app 私有 helper（含两个 @st.cache_data 视图缓存，因分析页签复用必须留在 app.py），
   用 frozen dataclass RecommendationDeps 打包注入。generate_overview_analysis /
   generate_module_recommendations 走模块限定调用（ala.xxx），使测试对源模块
   modules.audit_llm_analysis 的 patch 在迁移后仍生效。

app.py 通过 alias 保留原调用名（_unified_llm_key / _detail_for_recommendation 等）；
其中 _unified_llm_key 按原 helper key 注入给统计概况子页签，_detail_for_recommendation
由 functools.partial 预绑定 build_audit_cache，调用点签名与行为零变化。编排器入口
（_render_candidate_recommendations_for_module / _render_unified_generation_controls）
同样由 app.py 用 functools.partial 预绑定 RecommendationDeps，注入 helper key 与签名不变。
"""

from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
import streamlit as st

from modules import audit_llm_analysis as ala
from modules import candidate_pool as cp
from modules.audit_llm_analysis import (
    build_audit_analysis_payload,
    build_multi_year_audit_analysis_payload,
)
from modules.formatting import format_money
from modules.profiler import (
    build_financial_summary,
    financials_to_summary_text,
    profiles_to_summary_text,
)
from modules.visual_analysis import (
    DEFAULT_ADJUSTMENT_KEYWORDS,
    build_ap_accrual_entry_top10_from_work,
    build_cost_focus_entries_from_work,
    build_cost_material_account_summary_from_work,
    build_customer_revenue_entry_top10_from_work,
    build_customer_top10_from_work,
    build_expense_entry_top10_from_work,
    build_income_cost_abnormal_entry_top10_from_work,
    build_income_cost_category_options_from_work,
    build_monthly_revenue_cost_entry_top10_from_work,
    build_monthly_revenue_cost_view_from_work,
    build_other_payable_entry_top10_from_work,
    build_other_receivable_entry_top10_from_work,
    build_revenue_customer_material_summary_from_work,
    build_revenue_customer_monthly_focus_from_work_map,
    build_revenue_focus_entries_from_work,
    build_supplier_payable_entry_top10_from_work,
    build_supplier_top10_from_work,
)

from components.candidate_actions import detail_metrics


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
            customer_match = re.search(r"客户([A-Za-z0-9_\-\s一-鿿（）()]+?)收入", text)
            if customer_match:
                condition["kind"] = "customer_revenue"
                condition["customer"] = customer_match.group(1).strip()
        if not condition.get("year"):
            year_match = re.search(r"(20\d{2})年", text)
            if year_match:
                condition["year"] = int(year_match.group(1))
        if not condition.get("kind") and "毛利" in text:
            months = [int(m) for m in re.findall(r"(\d{1,2})月", text)]
            if months:
                condition["kind"] = "monthly_income_cost"
                condition["metric"] = "gross"
                condition["month"] = months[0]
                condition["months"] = months
        if not condition.get("kind") and "供应商" in text:
            supplier_match = re.search(r"供应商([A-Za-z0-9_\-\s一-鿿（）()]+?)(应付|暂估|收入|成本)", text)
            if supplier_match:
                condition["kind"] = "supplier_payable"
                condition["supplier"] = supplier_match.group(1).strip()
    elif module_filter == "费用":
        if not condition.get("kind"):
            expense_match = re.search(r"费用类别\s*([A-Za-z0-9_\-\s一-鿿（）()]+)", text)
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


# ── group 6 step 3：payload 构造 + UI 编排器 ──
@dataclass(frozen=True)
class RecommendationDeps:
    """app.py 注入给推荐编排器的私有 helper 包。

    build_audit_cache / build_adjustment_cache 是 @st.cache_data 视图缓存，分析页签
    复用，必须留在 app.py；其余为 LLM 配置、自动保存、费用/跨年汇总表 helper。
    """

    build_audit_cache: Callable[..., dict[str, pd.DataFrame]]
    build_adjustment_cache: Callable[..., tuple[pd.DataFrame, pd.DataFrame]]
    can_use_llm: Callable[[], bool]
    llm_model: Callable[[], str]
    llm_base_url: Callable[[], str]
    autosave_current_project_state: Callable[..., None]
    expense_summary_table: Callable[[dict], pd.DataFrame]
    cross_year_expense_table: Callable[[dict[int, dict]], pd.DataFrame]


def audit_source_summary(df_year: pd.DataFrame) -> dict:
    posting_dates = pd.to_datetime(df_year["过账日期"], errors="coerce").dropna()
    months = sorted(posting_dates.dt.month.unique().tolist()) if not posting_dates.empty else []
    start_date = posting_dates.min().date().isoformat() if not posting_dates.empty else None
    end_date = posting_dates.max().date().isoformat() if not posting_dates.empty else None
    voucher_count = int(df_year["凭证编号"].nunique()) if "凭证编号" in df_year.columns else 0
    return {
        "row_count": int(len(df_year)),
        "voucher_count": voucher_count,
        "date_range": f"{start_date} ~ {end_date}" if start_date and end_date else "",
        "months_covered": [int(month) for month in months],
        "is_partial_year": len(months) < 12,
    }


def build_year_audit_analysis_payload(
    year: int,
    df_year: pd.DataFrame,
    category: str,
    *,
    deps: RecommendationDeps,
) -> dict:
    year_cache = deps.build_audit_cache(df_year)
    year_work = year_cache["work"]
    year_category_options = build_income_cost_category_options_from_work(year_work)
    category_available = category == "总计" or category in year_category_options
    year_monthly_view = (
        year_cache["monthly"]
        if category == "总计"
        else build_monthly_revenue_cost_view_from_work(year_work, category=category)
    )
    adjustment_summary, _ = deps.build_adjustment_cache(df_year, tuple(DEFAULT_ADJUSTMENT_KEYWORDS))
    payload = build_audit_analysis_payload(
        year=year,
        category=category,
        monthly_view=year_monthly_view,
        customer_top=year_cache["customers"],
        supplier_top=year_cache["suppliers"],
        ap_accrual_monthly=year_cache["ap_accrual"],
        other_receivable_monthly=year_cache["other_receivable"],
        other_payable_monthly=year_cache["other_payable"],
        adjustment_summary=adjustment_summary,
        source_summary=audit_source_summary(df_year),
    )
    payload["category_available"] = category_available
    payload["available_income_cost_categories"] = year_category_options
    return payload


def income_cost_focus_payload(category: str, *, deps: RecommendationDeps) -> dict[str, Any]:
    return build_income_cost_focus_payload(st.session_state.year_map, category, deps)


@st.cache_data(show_spinner=False)
def build_income_cost_focus_payload(
    year_map: dict[int, pd.DataFrame],
    category: str,
    _deps: RecommendationDeps,
    cache_version: int = 1,
) -> dict[str, Any]:
    # _deps 以下划线开头，st.cache_data 不参与哈希（其内含不可哈希的 Callable，且运行期恒定）。
    _ = cache_version
    yearly_rows = []
    work_map = {}
    for year, df_year in sorted(year_map.items()):
        cache = _deps.build_audit_cache(df_year)
        work = cache["work"]
        work_map[int(year)] = work
        monthly = (
            cache["monthly"]
            if category == "总计"
            else build_monthly_revenue_cost_view_from_work(work, category=category)
        )
        customer_summary = build_customer_top10_from_work(work, top_n=15)
        supplier_payable_summary = build_supplier_top10_from_work(work, top_n=15)
        revenue_summary = build_revenue_customer_material_summary_from_work(work, category=category, top_n=12)
        cost_summary = build_cost_material_account_summary_from_work(work, category=category, top_n=12)
        expense_summary = _deps.expense_summary_table(build_financial_summary(df_year, year))
        adjustment_summary, adjustment_detail = _deps.build_adjustment_cache(df_year, tuple(DEFAULT_ADJUSTMENT_KEYWORDS))
        yearly_rows.append({
            "year": year,
            "source_summary": audit_source_summary(df_year),
            "monthly_income_cost": records_for_payload(monthly, limit=12),
            "customer_revenue_top": records_for_payload(customer_summary, limit=15),
            "supplier_payable_top": records_for_payload(supplier_payable_summary, limit=15),
            "revenue_customer_material_top": records_for_payload(revenue_summary, limit=12),
            "cost_material_account_top": records_for_payload(cost_summary, limit=12),
            "expense_category_top": records_for_payload(expense_summary, limit=12),
            "ap_accrual_monthly_top": records_for_payload(cache["ap_accrual"], limit=12),
            "other_receivable_monthly_top": records_for_payload(cache["other_receivable"], limit=12),
            "other_payable_monthly_top": records_for_payload(cache["other_payable"], limit=12),
            "adjustment_summary_top": records_for_payload(adjustment_summary, limit=12),
            "adjustment_voucher_top": records_for_payload(adjustment_detail, limit=20),
        })

    customer_monthly = build_revenue_customer_monthly_focus_from_work_map(
        work_map,
        category=category,
        top_customers=12,
    )
    cross_year_expense = _deps.cross_year_expense_table(
        {int(year): build_financial_summary(df_year, int(year)) for year, df_year in sorted(year_map.items())}
    )
    payload = {
        "analysis_scope": "income_cost_candidate_recommendation",
        "income_cost_category": category,
        "unit": "原币金额；前端通常折算为万元展示",
        "years": sorted(year_map.keys()),
        "yearly_rows": yearly_rows,
        "revenue_customer_monthly_volatility_top": records_for_payload(customer_monthly, limit=24),
        "cross_year_expense_compare_top": records_for_payload(cross_year_expense, limit=60),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    payload["signature"] = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return payload


def render_unified_generation_controls(category: str, *, deps: RecommendationDeps) -> None:
    render_candidate_recommendations_for_module(
        category, module_filter="收入成本", deps=deps, show_controls=True, cards_only=False
    )


def render_candidate_recommendations_for_module(
    category: str,
    module_filter: str,
    *,
    deps: RecommendationDeps,
    show_controls: bool = False,
    cards_only: bool = True,
) -> None:
    years = sorted(st.session_state.get("year_map", {}).keys())
    unified_key = unified_llm_key(years, category)
    unified_cached = st.session_state.audit_llm_analysis.get(unified_key)

    if not deps.can_use_llm():
        st.info("未配置 API Key。手动加入疑点库仍可正常使用。")
        return

    def _add_recommendations(selected: list[tuple[int, dict[str, Any], bool]]) -> tuple[int, int]:
        added = 0
        skipped = 0
        pool = st.session_state.get("candidate_pool", [])
        for idx, rec, direct_final in selected:
            condition = backfill_recommendation_condition(rec, category, module_filter)
            detail = detail_for_recommendation(condition, category, build_audit_cache=deps.build_audit_cache)
            if detail.empty:
                skipped += 1
                continue
            title = rec.get("title") or f"模型建议 {idx + 1}"
            group = cp.build_candidate_group(
                title=title,
                source_module=rec.get("source_module", "收入成本"),
                source_view=rec.get("source_view", "模型建议"),
                detail=detail,
                tags=["模型建议"] + [str(tag) for tag in rec.get("tags", [])],
                reason=rec.get("reason", ""),
                selector=condition,
                status=cp.MANUAL_FINAL_STATUS if direct_final else cp.DEFAULT_STATUS,
                created_by="llm",
                recommendation=rec,
            )
            pool = cp.add_candidate_group(pool, group)
            added += 1
        st.session_state.candidate_pool = pool
        if added:
            st.session_state.rule_results = []
            st.session_state.llm_judgments = {}
            st.session_state.report_stats = {}
            st.session_state.report_path = None
            deps.autosave_current_project_state()
        return added, skipped

    def _generate_recommendations(auto_add_all: bool = False) -> None:
        progress = st.progress(0)
        status = st.empty()
        status.text("正在整理财务概况与筛样输入数据...")
        with st.spinner("大模型正在执行智能分析…"):
            recommendation_payload = income_cost_focus_payload(category, deps=deps)
            progress.progress(25)
            status.text("正在汇总财务概况输入...")
            analysis_year_payloads = [
                build_year_audit_analysis_payload(year, df_year, category, deps=deps)
                for year, df_year in sorted(st.session_state.year_map.items())
            ]
            overview_payload = build_multi_year_audit_analysis_payload(
                year_payloads=analysis_year_payloads,
                category=category,
            )
            unified_payload = {
                "overview_payload": overview_payload,
                "recommendation_payload": recommendation_payload,
            }
            progress.progress(55)
            status.text("正在生成智能分析...")
            overview_result = ala.generate_overview_analysis(
                payload=overview_payload,
                api_key=st.session_state.get("_api_key", ""),
                model=deps.llm_model(),
                base_url=deps.llm_base_url(),
            )
            module_payloads: dict[str, dict[str, Any]] = {
                "收入成本": recommendation_payload,
                "费用": {
                    "analysis_scope": "expense_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "expense_category_top": row.get("expense_category_top", []),
                            "cross_year_expense_compare_top": recommendation_payload.get("cross_year_expense_compare_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "暂估往来": {
                    "analysis_scope": "working_capital_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "ap_accrual_monthly_top": row.get("ap_accrual_monthly_top", []),
                            "other_receivable_monthly_top": row.get("other_receivable_monthly_top", []),
                            "other_payable_monthly_top": row.get("other_payable_monthly_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "调账冲销": {
                    "analysis_scope": "adjustment_candidate_recommendation",
                    "years": recommendation_payload.get("years", []),
                    "yearly_rows": [
                        {
                            "year": row.get("year"),
                            "source_summary": row.get("source_summary"),
                            "adjustment_summary_top": row.get("adjustment_summary_top", []),
                            "adjustment_voucher_top": row.get("adjustment_voucher_top", []),
                        }
                        for row in recommendation_payload.get("yearly_rows", [])
                    ],
                },
                "跨年交叉稽核": {
                    "analysis_scope": "cross_year_candidate_recommendation",
                    "findings": [
                        {
                            "category": f.category,
                            "description": f.description,
                            "years_involved": f.years_involved,
                            "voucher_ids": f.voucher_ids,
                            "amount": f.amount,
                            "severity": f.severity,
                            "evidence": f.evidence,
                        }
                        for f in st.session_state.get("cross_year_findings", [])
                    ],
                },
                "统计画像": {
                    "analysis_scope": "profile_candidate_recommendation",
                    "profiles_text": profiles_to_summary_text(st.session_state.profiles),
                    "financials_text": financials_to_summary_text(st.session_state.financials),
                },
            }
            module_recommendations: dict[str, list[dict[str, Any]]] = {}
            module_names = ["收入成本", "费用", "暂估往来", "调账冲销", "跨年交叉稽核", "统计画像"]
            status.text("正在并行生成各模块建议...")
            future_to_module = {}
            with ThreadPoolExecutor(max_workers=3) as executor:
                for module_name in module_names:
                    future = executor.submit(
                        ala.generate_module_recommendations,
                        module_name=module_name,
                        payload=module_payloads[module_name],
                        api_key=st.session_state.get("_api_key", ""),
                        model=deps.llm_model(),
                        base_url=deps.llm_base_url(),
                    )
                    future_to_module[future] = module_name

                completed = 0
                for future in as_completed(future_to_module):
                    module_name = future_to_module[future]
                    completed += 1
                    status.text(f"正在汇总模块建议：{module_name} 已完成（{completed}/{len(module_names)}）")
                    progress.progress(55 + int(completed / len(module_names) * 30))
                    try:
                        module_result = future.result()
                        module_recommendations[module_name] = list(module_result.get("recommendations", []))
                    except Exception as module_error:
                        module_recommendations[module_name] = []
                        st.warning(f"{module_name} 模块建议生成失败，已跳过：{module_error}")

            result = {
                "overview_analysis": overview_result,
                "module_recommendations": module_recommendations,
                "input_signature": hashlib.sha1(json.dumps(unified_payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16],
                "analysis_scope": "unified_overview_and_recommendation",
            }
            progress.progress(90)
            status.text("正在回填结果并分发到各模块...")
            st.session_state.audit_llm_analysis[unified_key] = result
            if auto_add_all:
                recommendations = list(module_recommendations.get(module_filter, []))
                added, skipped = _add_recommendations([(idx, rec, False) for idx, rec in enumerate(recommendations)])
                if added:
                    st.success(f"已生成并加入 {added} 条模型建议。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                else:
                    st.warning("模型已返回建议，但没有匹配到可加入疑点库的明细分录。")
            deps.autosave_current_project_state()
            status.text("大模型结果已生成")
            progress.progress(100)
            st.rerun(scope="app")

    if show_controls:
        generate_col, auto_add_col = st.columns(2)
        btn_label = "智能分析" if not unified_cached else "刷新智能分析"
        with generate_col:
            if st.button(btn_label, disabled=not deps.can_use_llm(), type="primary", width="stretch"):
                try:
                    _generate_recommendations(auto_add_all=False)
                except Exception as e:
                    st.error(f"生成模型建议失败：{e}")
        with auto_add_col:
            add_disabled = not unified_cached or not deps.can_use_llm()
            if st.button("一键加入疑点库", disabled=add_disabled, width="stretch", key=f"gen_add_all_llm_{unified_key}"):
                try:
                    recommendations = list(
                        (unified_cached or {}).get("module_recommendations", {}).get(module_filter, [])
                    )
                    if not recommendations:
                        st.warning("当前没有可加入的模型建议，请先执行智能分析。")
                    else:
                        added, skipped = _add_recommendations(
                            [(idx, rec, False) for idx, rec in enumerate(recommendations)]
                        )
                        deps.autosave_current_project_state()
                        if added:
                            st.success(f"已加入 {added} 条模型建议到疑点库。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                            st.rerun(scope="app")
                        else:
                            st.warning("模型建议没有匹配到可加入疑点库的明细分录。")
                except Exception as e:
                    st.error(f"加入疑点库失败：{e}")

    if not unified_cached:
        if not show_controls:
            st.info("请先在收入成本页签生成智能分析，再回到这里查看本模块结果。")
        return

    if not cards_only:
        return
    recommendations = list(((unified_cached.get("module_recommendations") or {}).get(module_filter, [])))
    filtered_recommendations = [
        rec for rec in recommendations
        if isinstance(rec, dict) and recommendation_matches_module(rec, module_filter)
    ]
    if not filtered_recommendations:
        st.caption("模型未返回可操作建议。")
        return

    all_col = st.columns(1)[0]
    with all_col:
        if st.button("一键全部加入疑点库", width="stretch", key=f"add_all_llm_rec_{unified_key}_{module_filter}"):
            added, skipped = _add_recommendations([(idx, rec, False) for idx, rec in enumerate(filtered_recommendations)])
            if added:
                st.success(f"已加入 {added} 条模型建议。{f'跳过 {skipped} 条无匹配明细建议。' if skipped else ''}")
                st.rerun(scope="app")
            else:
                st.warning("没有可加入的模型建议；建议条件没有匹配到明细分录。")

    # 当前疑点库中已有的凭证号集合
    pool_vids: set[str] = set()
    for g in st.session_state.get("candidate_pool", []) or []:
        for vid in g.get("voucher_ids", []):
            pool_vids.add(str(vid))

    for idx, rec in enumerate(filtered_recommendations, start=1):
        condition = backfill_recommendation_condition(rec, category, module_filter)
        detail = detail_for_recommendation(condition, category, build_audit_cache=deps.build_audit_cache)
        stats = detail_metrics(detail)
        detail_vids = set(detail["凭证编号"].astype(str).tolist()) if not detail.empty and "凭证编号" in detail.columns else set()
        in_pool = detail_vids & pool_vids
        pool_badge = f"✅ 已入库 {len(in_pool)}/{len(detail_vids)} 个" if in_pool else "⬜ 未入库"

        risk = rec.get("risk_level", "中")
        title = rec.get("title") or f"模型建议 {idx}"
        with st.container(border=True):
            st.markdown(f"**建议 {idx:02d} | [{risk}] {title}**  `{pool_badge}`")
            st.markdown(f"**建议抽样什么**：{recommendation_target_text(rec)}")
            st.markdown(f"**为什么建议这个**：{rec.get('reason', '') or '模型未提供说明'}")
            st.caption(f"当前回查逻辑：{recommendation_condition_text(condition, module_filter)}")
            st.caption(f"匹配结果：{stats['vouchers']:,} 个凭证 / {stats['rows']:,} 行 / 金额绝对值合计 {format_money(stats['amount'])}")
            if detail.empty:
                st.caption("当前建议未匹配到明细。")
            else:
                tags = "、".join(str(tag) for tag in rec.get("tags", []))
                if tags:
                    st.caption(f"标签：{tags}")
                audit_procedure = str(rec.get("audit_procedure", "")).strip()
                if audit_procedure:
                    st.caption(f"建议核查动作：{audit_procedure}")
                action_col1, action_col2 = st.columns(2)
                with action_col1:
                    if st.button(
                        "加入疑点库",
                        width="stretch",
                        key=f"llm_rec_add_{unified_key}_{module_filter}_{idx}",
                        type="primary",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, False)])
                        if added:
                            st.success("已加入疑点库。")
                            st.rerun(scope="app")
                        else:
                            st.warning("当前建议没有匹配到可加入疑点库的明细分录。")
                with action_col2:
                    if st.button(
                        "直入最终样本",
                        width="stretch",
                        key=f"llm_rec_final_add_{unified_key}_{module_filter}_{idx}",
                    ):
                        added, skipped = _add_recommendations([(idx, rec, True)])
                        if added:
                            st.success("已直入最终样本。")
                            st.rerun(scope="app")
                        else:
                            st.warning("当前建议没有匹配到可直入最终样本的明细分录。")
