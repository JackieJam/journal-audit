"""
LLM 规则校准模块：把统计画像 + 跨年发现 + 经验库推荐规则喂给 DeepSeek，
输出 rules_config dict（含 rationale，供人工确认后执行）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI

from modules.json_utils import parse_json_dict
from modules.llm_quota import record_llm_call


SYSTEM_PROMPT = """你是一名有20年经验的企业内部审计专家，专注于序时账（总账明细账）的异常识别。
你的任务是：根据提供的公司账务统计画像，生成一套针对该公司的定制化审计抽样规则配置。

要求：
1. 每条规则的阈值必须基于画像中的实际数据推导（不允许凭感觉给通用值）
2. 每条规则必须包含 rationale 字段，说明"为什么选这个阈值"
3. 如果某类风险在该公司画像中没有迹象，将 enabled 设为 false，并在 rationale 中说明原因
4. 充分利用跨年发现，针对性地开启跨年规则
5. 资金池划转(cash_pool)、用户集中度(user_concentration)、冲销反记账(reversal_pattern)是核心风控规则，除非数据明确无相关风险，否则应 enabled
6. 仅输出 JSON，不要有任何其他文字"""

RULE_SCHEMA_HINT = """
输出格式（严格 JSON）：
{
  "splitting": {
    "enabled": true/false,
    "max_single_amount": <数字>,
    "min_total": <数字>,
    "window_days": <数字>,
    "min_txn_count": <数字>,
    "burst_multiplier": <数字，当日笔数超过日均几倍才触发，如3.0>,
    "rationale": "<为什么这样设>"
  },
  "large_amount": {
    "enabled": true/false,
    "round_number_threshold": <数字>,
    "repeat_threshold": <数字>,
    "repeat_window_days": <数字>,
    "repeat_min_count": <数字>,
    "holiday_min_amount": <数字，节假日过账金额门槛>,
    "rationale": "<为什么这样设>"
  },
  "manual_entry": {
    "enabled": true/false,
    "pnl_amount_threshold": <数字>,
    "month_end_days": <数字>,
    "rationale": "<为什么这样设>"
  },
  "accrual_anomaly": {
    "enabled": true/false,
    "match_window_days": <数字>,
    "amount_tolerance": <小数>,
    "min_amount": <数字，低于该金额不进入悬空计提样本>,
    "frequent_count": <数字>,
    "rationale": "<为什么这样设>"
  },
  "yearend_surge": {
    "enabled": true/false,
    "multiplier": <数字>,
    "months": [12],
    "rationale": "<为什么这样设>"
  },
  "financing_trade": {
    "enabled": true/false,
    "income_account_prefixes": ["6001", "6051"],
    "cost_account_prefixes": ["6401", "6402"],
    "min_revenue_amount": <数字，进入收入-成本配对的最低收入金额>,
    "low_margin_threshold": <小数，如0.05代表组合毛利率低于5%触发>,
    "max_loss_rate": <小数，如0.5代表组合亏损率超过50%时视为匹配噪声>,
    "min_match_score": <小数，收入凭证与成本凭证的最低匹配得分>,
    "max_candidate_groups": <数字，最多输出多少组疑点组合>,
    "max_related_vouchers": <数字，每组最多关联多少张成本凭证>,
    "window_days": <数字>,
    "keywords": ["<关键词1>", "<关键词2>"],
    "rationale": "<为什么这样设>"
  },
  "cross_year_accrual": {
    "enabled": true/false,
    "coverage_threshold": <小数，如0.8代表冲回率低于80%触发>,
    "match_window_days": <数字>,
    "rationale": "<为什么这样设>"
  },
  "cross_year_revenue": {
    "enabled": true/false,
    "dec_multiplier": <数字>,
    "rationale": "<为什么这样设>"
  },
  "cash_pool": {
    "enabled": true/false,
    "keywords": ["资金池", "同名划转", "上划", "下拨"],
    "large_threshold": <数字>,
    "rationale": "<为什么这样设>"
  },
  "user_concentration": {
    "enabled": true/false,
    "concentration_threshold": <小数，如0.25>,
    "rationale": "<为什么这样设>"
  },
  "reversal_pattern": {
    "enabled": true/false,
    "frequent_count": <数字>,
    "large_threshold": <数字>,
    "rationale": "<为什么这样设>"
  },
  "sensitive_fees": {
    "enabled": true/false,
    "categories": {
      "咨询费": {"keywords": ["咨询", "顾问"], "exclude": [], "threshold": <数字>},
      "代理费": {"keywords": ["代理", "代办"], "exclude": ["货运代理", "报关", "快递"], "threshold": <数字>},
      "中介费": {"keywords": ["中介", "经纪"], "exclude": [], "threshold": <数字>},
      "捐赠赞助": {"keywords": ["捐赠", "赞助"], "exclude": [], "threshold": <数字>},
      "罚款赔偿": {"keywords": ["罚款", "罚金", "滞纳金", "违约金"], "exclude": [], "threshold": <数字>},
      "招待费": {"keywords": ["招待", "接待"], "exclude": [], "threshold": <数字>},
      "旅游团建": {"keywords": ["旅游", "团建", "考察"], "exclude": ["出差", "差旅"], "threshold": <数字>}
    },
    "baseline_multiplier": <数字，如3.0>,
    "rationale": "<为什么这样设>"
  },
  "whitelist_keywords": ["<正常业务关键词，过滤用>"],
  "whitelist_voucher_types": ["<系统自动凭证类型>"],
  "max_sample_size": <数字，建议30-100>
}
"""


_LLM_MAX_RETRIES = 3
_LLM_RETRY_BACKOFF_BASE = 1.5
_LLM_TIMEOUT_SECONDS = 120.0


def generate_rules_config(
    profiles_text: str,
    cross_year_text: str,
    library_rules: list[dict],
    api_key: str,
    candidate_pool_text: str = "",
    model: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com",
) -> dict[str, Any]:
    """
    调用 LLM 生成 rules_config。
    返回 dict，可直接存为 rules_config.json 或放入 session_state。
    """
    library_text = _format_library_rules(library_rules)

    user_prompt = f"""## 公司账务统计画像
{profiles_text}

## 跨年稽核发现
{cross_year_text}

## 可疑样本群体（如有）
{candidate_pool_text or "当前尚未建立疑点库。"}

## 经验库中的历史有效规则（供参考，可调整参数后复用）
{library_text}

## 输出规则配置
{RULE_SCHEMA_HINT}

请基于以上信息，为该公司生成校准后的规则配置 JSON。"""

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=3)
    last_exc = None
    for attempt in range(_LLM_MAX_RETRIES + 1):
        try:
            record_llm_call("rule_calibration")
            response = client.chat.completions.create(
                model=model,
                max_tokens=3000,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                timeout=_LLM_TIMEOUT_SECONDS,
            )
            raw = response.choices[0].message.content
            return parse_json_dict(raw)
        except (APITimeoutError, APIConnectionError) as exc:
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
            break

    raise RuntimeError(f"规则校准失败：{last_exc}") from last_exc


def _format_library_rules(rules: list[dict]) -> str:
    if not rules:
        return "（经验库暂无历史规则）"

    lines = []
    for r in rules[:10]:  # 最多传10条避免 token 过多
        lines.append(
            f"- [{r.get('name')}] 分类:{r.get('category')} "
            f"历史确认率:{r.get('performance', {}).get('confirmation_rate', 'N/A')} "
            f"参数:{json.dumps(r.get('parameters', {}), ensure_ascii=False)} "
            f"说明:{r.get('rationale', '')}"
        )
    return "\n".join(lines)


def default_rules_config() -> dict[str, Any]:
    """从 config/default_rules.json 加载默认规则配置。"""
    path = Path(__file__).parent.parent / "config" / "default_rules.json"
    return json.loads(path.read_text(encoding="utf-8"))
