"""
审计可视化 LLM 初步解析。
仅使用聚合后的可视化数据，不向模型发送 API Key、环境变量或完整明细账。
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import pandas as pd
from openai import APIConnectionError, APITimeoutError, OpenAI

from modules.json_utils import parse_json_dict
from modules.llm_quota import record_llm_call


SYSTEM_PROMPT = """你是一名企业内部审计经理，正在基于序时账审计可视化结果做初步分析。
最终目标是帮助审计师在提交的全部序时账年份中，快速定位需要穿透到凭证、合同、对账单或期后回款/付款证据的风险点。
你的任务是阅读单年度或多年度的收入成本、暂估往来、其他往来、调账冲销等聚合指标，形成面向审计师的初步解析。

要求：
1. 不要把聚合指标直接复述成流水账，要指出审计含义和优先核查方向。
2. 结论必须基于输入数据，不要编造不存在的客户、供应商、月份或金额。
3. 区分“观察到的异常信号”和“仍需凭证/合同/对账单验证的假设”。
4. 如果输入包含多个年份，必须覆盖所有年份，并指出跨年变化、异常集中年份和口径不可比限制。
5. 如果某一年不是完整 12 个月，不得直接把它与完整年度做全年规模结论；应说明只能做期间口径比较或提示需补齐数据。
6. 每条重要观察尽量落到“年份 + 月份/客户/供应商/科目方向 + 建议穿透位置”。
7. 仅输出 JSON，不要输出 Markdown 或额外说明。"""


OUTPUT_SCHEMA = """
{
  "executive_summary": "3-5句话概述本次分析范围内的经营与账务异常信号",
  "key_observations": [
    {
      "area": "收入成本/暂估往来/调账冲销/其他",
      "severity": "高/中/低",
      "observation": "观察到的现象",
      "audit_meaning": "统计或审计上的含义",
      "suggested_procedure": "建议下一步核查动作"
    }
  ],
  "cross_year_observations": [
    {
      "comparison_period": "2023-2024/2024-2025/全部年份",
      "severity": "高/中/低",
      "observation": "跨年变化或趋势",
      "audit_meaning": "审计上的含义",
      "suggested_procedure": "建议下一步核查动作"
    }
  ],
  "drilldown_focus": [
    {
      "view": "收入成本/暂估往来/调账冲销",
      "target": "应优先点击或查看的年份、月份、客户、供应商或凭证范围",
      "reason": "为什么要穿透这个位置"
    }
  ],
  "priority_focus": ["优先关注事项1", "优先关注事项2", "优先关注事项3"],
  "data_limitations": ["基于聚合数据的限制或需要补充的证据"]
}
"""


LLM_REQUEST_TIMEOUT_SECONDS = 90.0
_LLM_MAX_RETRIES = 3
_LLM_RETRY_BACKOFF_BASE = 1.5

JSON_REPAIR_SYSTEM_PROMPT = """你是一个 JSON 修复器。
你的唯一任务是把输入内容修复为严格合法的 JSON。

要求：
1. 不改变原始业务含义，只修复 JSON 语法。
2. 保持原有字段名、字段层级和数组结构。
3. 删除多余说明、Markdown、注释、尾逗号，补全缺失逗号或引号转义。
4. 仅输出修复后的 JSON 对象，不要输出任何解释。"""


def build_audit_analysis_payload(
    *,
    year: int,
    category: str,
    monthly_view: pd.DataFrame,
    customer_top: pd.DataFrame,
    supplier_top: pd.DataFrame,
    ap_accrual_monthly: pd.DataFrame,
    other_receivable_monthly: pd.DataFrame,
    other_payable_monthly: pd.DataFrame,
    adjustment_summary: pd.DataFrame | None = None,
    source_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """把审计可视化聚合数据压缩成适合 LLM 的 JSON payload。"""
    monthly = monthly_view.copy()
    ap = ap_accrual_monthly.copy()
    other_receivable = other_receivable_monthly.copy()
    other_payable = other_payable_monthly.copy()
    adjustment_summary = adjustment_summary if adjustment_summary is not None else pd.DataFrame()

    totals = {
        "净收入": _num(monthly.get("净收入", pd.Series(dtype=float)).sum()),
        "净成本影响": _num(monthly.get("净成本影响", pd.Series(dtype=float)).sum()),
        "毛利": _num(monthly.get("毛利", pd.Series(dtype=float)).sum()),
        "收入H影响": _num(monthly.get("收入H影响", pd.Series(dtype=float)).sum()),
        "收入S影响": _num(monthly.get("收入S影响", pd.Series(dtype=float)).sum()),
        "成本S影响": _num(monthly.get("成本S影响", pd.Series(dtype=float)).sum()),
        "成本H影响": _num(monthly.get("成本H影响", pd.Series(dtype=float)).sum()),
    }
    revenue = totals["净收入"]
    totals["毛利率"] = _num(totals["毛利"] / revenue) if revenue else 0
    totals["异常方向金额"] = _num(abs(totals["收入S影响"]) + abs(totals["成本H影响"]))

    payload = {
        "year": year,
        "income_cost_category": category,
        "unit": "原币金额；展示时通常折算为万元",
        "source_summary": source_summary or {},
        "totals": totals,
        "monthly_income_cost_months_with_activity": _active_months(
            monthly,
            value_cols=["净收入", "净成本影响", "毛利", "收入S影响", "成本H影响"],
        ),
        "monthly_income_cost_top": _top_months(
            monthly,
            value_cols=["净收入", "净成本影响", "毛利", "收入S影响", "成本H影响"],
        ),
        "customer_top": _records(customer_top, limit=10),
        "supplier_top": _records(supplier_top, limit=10),
        "ap_accrual_monthly_top": _top_months(
            ap,
            value_cols=["暂估贷方增加", "暂估借方减少", "暂估净额"],
        ),
        "other_receivable_monthly_top": _top_months(
            other_receivable,
            value_cols=["其他应收S发生额", "其他应收H发生额", "其他应收净额"],
        ),
        "other_payable_monthly_top": _top_months(
            other_payable,
            value_cols=["其他应付预提H", "其他应付核销S", "其他应付净值"],
        ),
        "adjustment_summary_top": _records(adjustment_summary, limit=12),
    }
    payload["signature"] = audit_analysis_signature(payload)
    return payload


def build_multi_year_audit_analysis_payload(
    *,
    year_payloads: list[dict[str, Any]],
    category: str,
) -> dict[str, Any]:
    """把多个年度的审计可视化聚合数据组合成跨年解析 payload。"""
    cleaned_payloads = [
        {k: v for k, v in payload.items() if k != "signature"}
        for payload in sorted(year_payloads, key=_year_sort_key)
    ]
    yearly_summaries = [_year_summary(payload) for payload in cleaned_payloads]
    years = [item["year"] for item in yearly_summaries if item.get("year") is not None]

    payload = {
        "analysis_scope": "all_uploaded_years",
        "years": years,
        "income_cost_category": category,
        "unit": "原币金额；展示时通常折算为万元",
        "yearly_summaries": yearly_summaries,
        "cross_year_summary": {
            "year_count": len(years),
            "data_coverage": [
                {
                    "year": item.get("year"),
                    "date_range": item.get("source_summary", {}).get("date_range"),
                    "months_covered": item.get("source_summary", {}).get("months_covered", []),
                    "is_partial_year": item.get("source_summary", {}).get("is_partial_year", False),
                }
                for item in yearly_summaries
            ],
            "partial_years": [
                item.get("year")
                for item in yearly_summaries
                if item.get("source_summary", {}).get("is_partial_year", False)
            ],
            "category_coverage": [
                {
                    "year": item.get("year"),
                    "category_available": item.get("category_available", True),
                    "used_category": item.get("category"),
                }
                for item in yearly_summaries
            ],
            "year_over_year_changes": _year_over_year_changes(yearly_summaries),
        },
        "yearly_payloads": cleaned_payloads,
    }
    payload["signature"] = audit_analysis_signature(payload)
    return payload


def audit_analysis_signature(payload: dict[str, Any]) -> str:
    """为聚合输入生成稳定签名，用于判断缓存解析是否仍匹配当前视图。"""
    copy_payload = {k: v for k, v in payload.items() if k != "signature"}
    copy_payload = _json_safe(copy_payload)
    raw = json.dumps(copy_payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def analyze_audit_visuals(
    payload: dict[str, Any],
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> dict[str, Any]:
    """调用 LLM 生成审计可视化初步解析。"""
    if not api_key:
        raise ValueError("缺少 API Key")

    user_prompt = f"""## 审计可视化聚合数据
{json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str)}

## 输出格式
{OUTPUT_SCHEMA}

请基于以上聚合数据输出初步审计解析。"""

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=3)
    raw = _request_json_text(
        client=client,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=3200,
        force_json_object=True,
        operation="audit_visual_analysis",
    )
    parsed = _parse_json_response(raw)
    parsed["input_signature"] = payload.get("signature") or audit_analysis_signature(payload)
    parsed["analysis_scope"] = payload.get("analysis_scope", "single_year")
    parsed["year"] = payload.get("year")
    parsed["years"] = payload.get("years") or ([payload.get("year")] if payload.get("year") else [])
    parsed["income_cost_category"] = payload.get("income_cost_category")
    return parsed


CANDIDATE_RECOMMENDATION_SCHEMA = """
{
  "executive_summary": "简要说明收入成本、费用、暂估往来和调账冲销中的主要波动风险",
  "recommendations": [
    {
      "title": "建议卡片标题",
      "source_module": "收入成本/费用/暂估往来/调账冲销",
      "source_view": "月度收入成本/异常方向/客户收入/供应商应付/费用类别/暂估月度/暂估供应商/其他应收/其他应付/调账凭证",
      "risk_level": "高/中/低",
      "reason": "为什么建议纳入疑点库",
      "tags": ["收入波动", "客户", "供应商", "月度"],
      "condition": {
        "kind": "monthly_income_cost/income_cost_abnormal/customer_revenue/supplier_payable/expense_category/ap_accrual_month/ap_accrual_supplier/other_receivable_month/other_payable_month/adjustment_voucher",
        "year": 2024,
        "month": 12,
        "metric": "revenue/cost/gross，仅 kind=monthly_income_cost 时使用",
        "direction": "income_s/cost_h，仅 kind=income_cost_abnormal 时使用",
        "customer": "必须使用输入中出现的客户原文，可为空",
        "supplier": "必须使用输入中出现的供应商原文，可为空",
        "expense_category": "费用类别原文，可为空",
        "voucher_id": "调账凭证编号，可为空"
      },
      "audit_procedure": "建议核查动作"
    }
  ]
}
"""


UNIFIED_ANALYSIS_SCHEMA = """
{
  "overview_analysis": {
    "executive_summary": "3-5句话概述本次分析范围内的经营与账务异常信号",
    "financial_snapshot": [
      {
        "metric": "收入/成本/毛利/费用/研发费用率等指标名",
        "value": "数值或简短描述",
        "observation": "该指标的审计观察"
      }
    ],
    "key_risks": ["风险点1", "风险点2", "风险点3"],
    "data_limitations": ["基于聚合数据的限制或需要补充的证据"]
  },
  "module_recommendations": {
    "收入成本": [],
    "费用": [],
    "暂估往来": [],
    "调账冲销": [],
    "跨年交叉稽核": [],
    "统计画像": []
  }
}
"""


MODULE_RECOMMENDATION_SCHEMA = """
{
  "module_name": "收入成本/费用/暂估往来/调账冲销/跨年交叉稽核/统计画像",
  "recommendations": [
    {
      "title": "建议卡片标题",
      "source_module": "收入成本/费用/暂估往来/调账冲销/跨年交叉稽核/统计画像",
      "source_view": "模块内具体来源视图",
      "risk_level": "高/中/低",
      "reason": "为什么建议纳入疑点库",
      "tags": ["标签1", "标签2"],
      "condition": {
        "kind": "系统用于回查明细的类型",
        "year": 2024
      },
      "audit_procedure": "建议核查动作"
    }
  ]
}
"""

MODULE_CONDITION_GUIDE = {
    "收入成本": """
- 允许的 source_view：月度收入成本 / 异常方向 / 客户收入 / 供应商应付
- 允许的 kind：monthly_income_cost / income_cost_abnormal / customer_revenue / supplier_payable
- 如果建议的是某客户收入集中或波动，必须设置：
  kind=customer_revenue, year=对应年份, customer=输入中已有的客户原文
- 如果建议的是某供应商应付集中或波动，必须设置：
  kind=supplier_payable, year=对应年份, supplier=输入中已有的供应商原文
- 如果建议的是某几个月毛利/收入/成本异常，可以设置：
  kind=monthly_income_cost, metric=revenue/cost/gross, month=首个月份, months=[所有月份]
- 如果建议的是收入S或成本H异常方向，可以设置：
  kind=income_cost_abnormal, direction=income_s/cost_h, month=首个月份, months=[所有月份]
""",
    "费用": """
- 允许的 source_view：费用类别
- 允许的 kind：expense_category
- 必须设置：year=对应年份, expense_category=输入中已有的费用类别原文
""",
    "暂估往来": """
- 允许的 source_view：暂估月度 / 暂估供应商 / 其他应收 / 其他应付
- 允许的 kind：ap_accrual_month / ap_accrual_supplier / other_receivable_month / other_payable_month
- 月度类建议必须设置：year, month
- 供应商类建议必须设置：supplier=输入中已有的供应商原文
- direction 仅允许：credit / debit / net / accrual / writeoff
""",
    "调账冲销": """
- 允许的 source_view：调账凭证
- 允许的 kind：adjustment_voucher
- 必须设置：year, voucher_id=输入中已有的凭证编号原文
""",
    "跨年交叉稽核": """
- 允许的 source_view：跨年异常类型名
- 允许的 kind：cross_year_finding
- 必须设置：category=输入中的异常分类原文
- 如果输入提供了 voucher_ids，也一并放入 condition.voucher_ids
""",
    "统计画像": """
- 允许的 source_view：统计画像
- 允许的 kind：profile_signal
- 如果无法形成可直接回查的建议，recommendations 返回 []
""",
}


def generate_overview_analysis(
    payload: dict[str, Any],
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> dict[str, Any]:
    """只生成财务概况解析。"""
    if not api_key:
        raise ValueError("缺少 API Key")

    prompt = f"""## 审计聚合数据
{json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str)}

## 输出格式
{json.dumps(json.loads(UNIFIED_ANALYSIS_SCHEMA)["overview_analysis"], ensure_ascii=False, indent=2)}

要求：
1. 只输出 overview_analysis 这一个 JSON 对象。
2. 不要输出 module_recommendations。
3. 仅输出 JSON，不要输出 Markdown 或额外说明。"""

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=3)
    raw = _request_json_text(
        client=client,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=2200,
        force_json_object=True,
        operation="overview_analysis",
    )
    parsed = _parse_json_response_with_repair(raw, client=client, model=model)
    parsed["input_signature"] = payload.get("signature") or audit_analysis_signature(payload)
    return parsed


def generate_module_recommendations(
    *,
    module_name: str,
    payload: dict[str, Any],
    api_key: str,
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> dict[str, Any]:
    """按单个模块生成抽样建议。"""
    if not api_key:
        raise ValueError("缺少 API Key")

    prompt = f"""## 模块名称
{module_name}

## 审计聚合数据
{json.dumps(_json_safe(payload), ensure_ascii=False, indent=2, default=str)}

## 输出格式
{MODULE_RECOMMENDATION_SCHEMA}

## 本模块 condition 约束
{MODULE_CONDITION_GUIDE.get(module_name, "")}

要求：
1. 只输出 {module_name} 模块的建议。
2. module_name 字段必须等于 {module_name}。
3. 如果该模块没有建议，recommendations 返回 []。
4. 每条建议都必须给出 condition，系统会据此回查全量序时账凭证。
5. customer / supplier / expense_category / voucher_id 必须使用输入中出现的原文，不要概括改写。
6. 多个月份建议优先用 months 数组表达，并保留 month=首个月份。
5. 仅输出 JSON，不要输出 Markdown 或额外说明。"""

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=3)
    raw = _request_json_text(
        client=client,
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        max_tokens=1800,
        force_json_object=True,
        operation=f"module_recommendation::{module_name}",
    )
    parsed = _parse_json_response_with_repair(raw, client=client, model=model)
    parsed["input_signature"] = payload.get("signature") or audit_analysis_signature(payload)
    return parsed


def _request_json_text(
    *,
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    force_json_object: bool = False,
    operation: str = "audit_llm_analysis",
) -> str:
    """调用 LLM 并返回响应文本，对连接/超时错误自动重试。"""
    response = None
    last_exc: Exception | None = None

    request_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "timeout": LLM_REQUEST_TIMEOUT_SECONDS,
    }
    if force_json_object:
        request_kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            record_llm_call(operation)
            response = client.chat.completions.create(**request_kwargs)
            break
        except APITimeoutError as exc:
            last_exc = exc
            if attempt < _LLM_MAX_RETRIES:
                wait = _LLM_RETRY_BACKOFF_BASE ** attempt
                time.sleep(wait)
                continue
            raise TimeoutError(
                f"大模型请求在 {int(LLM_REQUEST_TIMEOUT_SECONDS)} 秒内未返回（已重试 {_LLM_MAX_RETRIES} 次），"
                "请稍后重试，或检查当前模型 / Base URL 是否可用。"
            ) from exc
        except APIConnectionError as exc:
            last_exc = exc
            if attempt < _LLM_MAX_RETRIES:
                wait = _LLM_RETRY_BACKOFF_BASE ** attempt
                time.sleep(wait)
                continue
            raise ConnectionError(
                f"大模型连接失败（已重试 {_LLM_MAX_RETRIES} 次），请检查网络、Base URL 或模型服务状态。"
            ) from exc
        except Exception as exc:
            last_exc = exc
            if force_json_object and "response_format" in str(exc):
                # 移除 response_format 降级重试一次
                fallback_kwargs: dict[str, Any] = {k: v for k, v in request_kwargs.items() if k != "response_format"}
                fallback_kwargs["messages"] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt + "\n\n再次强调：只输出严格合法的 JSON 对象。"},
                ]
                fallback_kwargs["temperature"] = 0.0
                try:
                    response = client.chat.completions.create(**fallback_kwargs)
                    break
                except Exception as fallback_exc:
                    raise RuntimeError(f"大模型调用失败：{fallback_exc}") from fallback_exc
            else:
                raise RuntimeError(f"大模型调用失败：{exc}") from exc

    if response is None:
        if last_exc is not None:
            raise RuntimeError(f"大模型调用失败：{last_exc}") from last_exc
        raise RuntimeError("大模型未返回响应对象，请检查当前模型服务是否可用。")

    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("大模型返回为空，未拿到任何候选结果。请稍后重试。")

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None:
        raise RuntimeError("大模型返回缺少 message 字段，无法解析建议结果。")

    return getattr(message, "content", "") or ""


def _active_months(df: pd.DataFrame, value_cols: list[str]) -> list[int]:
    if df.empty or "月份" not in df.columns:
        return []
    existing_cols = [c for c in value_cols if c in df.columns]
    if not existing_cols:
        return []
    active = df.loc[df[existing_cols].abs().sum(axis=1) > 0, "月份"]
    return [int(month) for month in active.tolist()]


def _top_months(df: pd.DataFrame, value_cols: list[str], limit: int = 6) -> list[dict[str, Any]]:
    if df.empty or "月份" not in df.columns:
        return []
    work = df.copy()
    existing_cols = [c for c in value_cols if c in work.columns]
    if not existing_cols:
        return []
    work["_sort_abs"] = work[existing_cols].abs().max(axis=1)
    cols = ["月份"] + existing_cols
    return _records(work.sort_values("_sort_abs", ascending=False)[cols], limit=limit)


def _records(df: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    if df.empty:
        return []
    cleaned = df.head(limit).copy()
    for col in cleaned.columns:
        if pd.api.types.is_datetime64_any_dtype(cleaned[col]):
            cleaned[col] = cleaned[col].dt.strftime("%Y-%m-%d")
    return [
        {str(k): _clean_value(v) for k, v in row.items()}
        for row in cleaned.to_dict("records")
    ]


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        return round(value, 2)
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(_json_safe(k)): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return [_json_safe(v) for v in value]
    if hasattr(value, "item") and callable(value.item):
        try:
            return _json_safe(value.item())
        except Exception:
            return value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _num(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _year_sort_key(payload: dict[str, Any]) -> int:
    try:
        return int(payload.get("year") or 0)
    except Exception:
        return 0


def _year_summary(payload: dict[str, Any]) -> dict[str, Any]:
    totals = payload.get("totals") or {}
    source_summary = payload.get("source_summary") or {}
    summary_cols = [
        "净收入",
        "净成本影响",
        "毛利",
        "毛利率",
        "异常方向金额",
        "收入S影响",
        "成本H影响",
    ]
    return {
        "year": payload.get("year"),
        "category": payload.get("income_cost_category"),
        "category_available": payload.get("category_available", True),
        "source_summary": source_summary,
        "monthly_income_cost_months_with_activity": payload.get(
            "monthly_income_cost_months_with_activity",
            [],
        ),
        "totals": {col: _num(totals.get(col, 0)) for col in summary_cols},
    }


def _year_over_year_changes(yearly_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    metrics = ["净收入", "净成本影响", "毛利", "毛利率", "异常方向金额"]
    for previous, current in zip(yearly_summaries, yearly_summaries[1:], strict=False):
        metric_changes = {}
        previous_totals = previous.get("totals") or {}
        current_totals = current.get("totals") or {}
        for metric in metrics:
            previous_value = _num(previous_totals.get(metric, 0))
            current_value = _num(current_totals.get(metric, 0))
            metric_changes[metric] = {
                "previous": previous_value,
                "current": current_value,
                "change": _num(current_value - previous_value),
                "change_rate": _change_rate(previous_value, current_value),
            }
        changes.append({
            "period": f"{previous.get('year')}-{current.get('year')}",
            "comparable_as_full_year": not (
                previous.get("source_summary", {}).get("is_partial_year", False)
                or current.get("source_summary", {}).get("is_partial_year", False)
            ),
            "metrics": metric_changes,
        })
    return changes


def _change_rate(previous_value: float, current_value: float) -> float | None:
    if previous_value == 0:
        return None
    return _num((current_value - previous_value) / abs(previous_value))


def _parse_json_response(text: str) -> dict[str, Any]:
    return parse_json_dict(text)


def _parse_json_response_with_repair(
    text: str,
    *,
    client: OpenAI,
    model: str,
) -> dict[str, Any]:
    try:
        return parse_json_dict(text)
    except ValueError as first_error:
        repaired_text = _repair_json_via_llm(
            raw_text=text,
            client=client,
            model=model,
        )
        try:
            return parse_json_dict(repaired_text)
        except ValueError as second_error:
            raise ValueError(
                f"LLM 返回内容解析失败；已尝试自动修复但仍不是合法 JSON。原始错误：{first_error}；修复后错误：{second_error}"
            ) from second_error


def _repair_json_via_llm(
    *,
    raw_text: str,
    client: OpenAI,
    model: str,
) -> str:
    repair_prompt = f"""请把下面内容修复为严格合法的 JSON 对象，只修语法，不改业务含义：

```text
{raw_text}
```"""
    return _request_json_text(
        client=client,
        model=model,
        system_prompt=JSON_REPAIR_SYSTEM_PROMPT,
        user_prompt=repair_prompt,
        max_tokens=3200,
        force_json_object=True,
    )
