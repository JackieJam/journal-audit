"""
序时账审计抽样工具 — LLM 批量核实模块
按规则类型分批调用 Claude API，核实疑点凭证是否构成真实风险
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

from rules import RuleHit, RuleResult


@dataclass(frozen=True)
class LLMJudgment:
    """LLM 对单个凭证的核实结果"""

    voucher_id: float
    confirmed: bool
    risk_level: str  # "高" | "中"
    reason: str
    audit_procedures: str


# ============================================================
# Prompt 模板（按规则类型）
# ============================================================

RULE_CONTEXTS: dict[str, str] = {
    "融资性贸易识别": """融资性贸易的典型特征：
1. 贸易双方实为同一关联方
2. 货款流转但无实物交货记录
3. 收付款时间点高度一致（背靠背）
4. 毛利率极低（<1%）或异常高（>50%）
5. 供应商与客户名称高度相似或重叠""",

    "预提冲销异常": """预提冲销异常的典型特征：
1. 预提后长期未冲销（>3个月），可能是隐藏费用
2. 冲销金额与预提金额不一致，可能是调节利润
3. 月末预提、次月初冲销，可能是调节期间损益
4. 同一科目频繁预提冲销，可能是掩盖资金流向""",

    "化整为零": """化整为零的典型特征：
1. 同一供应商同日多笔小额付款，合计金额较大
2. 金额高度相似，像是刻意拆分以规避审批额度
3. 付款频率异常高，不符合正常业务节奏
4. 收款方为同一主体或关联方""",

    "大额异常流水": """大额异常的典型特征：
1. 大额整数付款（如500万、1000万），可能是虚构交易
2. 同一供应商短期内多次大额往来，可能是资金空转
3. 节假日或非工作时间过账，可能是规避审批
4. 金额与正常业务规模不匹配""",

    "手工凭证": """手工凭证异常的典型特征：
1. 由关键岗位人员直接录入，缺乏审核
2. 涉及损益科目，可能是调节利润
3. 在月末或年末集中录入，可能是突击调整
4. 金额恰好在审批阈值以下""",

    "年末突击确认": """年末突击收入的典型特征：
1. 12月收入远超前11月月均，可能是提前确认收入
2. 成本未同步增长，可能是虚增收入
3. 客户集中度突然提高，可能是关联方交易
4. 合同签订日期集中在年末""",

    "大额重复": """大额重复流水的典型特征：
1. 同一供应商短期内多次大额支付，可能是资金空转
2. 金额相近或相同，可能是重复支付或虚构交易
3. 收付款方向一致，不符合正常贸易往来""",

    "节假日过账": """节假日过账的典型特征：
1. 节假日通常不进行正常业务，过账可能是规避审批
2. 需核实是否有真实的业务背景
3. 可能是系统调整或人工干预""",

    "非工作时间录入": """非工作时间录入的典型特征：
1. 凌晨录入通常不是正常业务时间
2. 可能是为了规避审批流程
3. 需核实录入人员是否有合理的工作安排""",
}


def _build_prompt(rule_name: str, voucher_groups: list[dict]) -> str:
    """构建单次 API 调用的 prompt"""
    context = RULE_CONTEXTS.get(rule_name, "需人工判断是否存在审计风险。")

    vouchers_json = json.dumps(voucher_groups, ensure_ascii=False, indent=2, default=str)

    return f"""你是一名内部审计专家，正在核实以下凭证是否存在{rule_name}风险。

{context}

以下凭证已被规则标记为疑似风险，触发原因附在每条凭证后面。
请逐一判断是否构成真实审计风险。

{vouchers_json}

对每个凭证编号返回一个 JSON 对象（不要返回其他内容）：
[
  {{
    "voucher_id": 凭证编号（数字）,
    "confirmed": true或false,
    "risk_level": "高"或"中",
    "reason": "判断理由（1-2句话，说明为什么确认或排除）",
    "audit_procedures": "建议现场核查步骤（1-2句话）"
  }},
  ...
]

注意：
- 仅返回 confirmed=true 的凭证
- 如果全部排除，返回空数组 []
- 严格按 JSON 格式返回，不要添加其他文字"""


def _extract_voucher_groups(
    df: pd.DataFrame, hits: list[RuleHit]
) -> list[dict]:
    """将规则命中结果转为凭证组（JSON 格式）"""
    groups: list[dict] = []

    for hit in hits:
        voucher_rows = df[df["凭证编号"] == hit.voucher_id]
        rows_data: list[dict] = []

        for _, row in voucher_rows.iterrows():
            rows_data.append({
                "行项目": row.get("行项目"),
                "过账日期": str(row.get("过账日期", ""))[:10],
                "凭证类型": row.get("凭证类型"),
                "文本": row.get("文本"),
                "总账科目": str(int(row["总账科目"])) if isinstance(row.get("总账科目"), float) else row.get("总账科目"),
                "总账科目名称": row.get("总账科目：长文本"),
                "借/贷标识": row.get("借/贷标识"),
                "凭证货币价值": row.get("凭证货币价值"),
                "供应商": row.get("供应商科目：名称 1"),
                "客户": row.get("客户科目：姓名 1"),
                "用户名": row.get("用户名"),
            })

        groups.append({
            "voucher_id": hit.voucher_id,
            "rule_type": hit.rule_type,
            "evidence": hit.evidence,
            "lines": rows_data,
        })

    return groups


def _parse_llm_response(response_text: str) -> list[LLMJudgment]:
    """解析 LLM 返回的 JSON"""
    # 尝试提取 JSON 数组
    text = response_text.strip()

    # 处理可能的 markdown 代码块
    if text.startswith("```"):
        lines = text.split("\n")
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 JSON 数组
        import re
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            return []

    if not isinstance(data, list):
        return []

    judgments: list[LLMJudgment] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not item.get("confirmed", False):
            continue

        judgments.append(
            LLMJudgment(
                voucher_id=float(item["voucher_id"]),
                confirmed=True,
                risk_level=item.get("risk_level", "中"),
                reason=item.get("reason", ""),
                audit_procedures=item.get("audit_procedures", ""),
            )
        )

    return judgments


# ============================================================
# 公开接口
# ============================================================

def verify_with_llm(
    df: pd.DataFrame,
    rule_results: list[RuleResult],
    batch_size: int = 15,
    model: str = "deepseek-chat",
) -> dict[str, list[LLMJudgment]]:
    """
    按规则类型分批调用 LLM 核实疑点凭证。

    返回：{rule_name: [LLMJudgment, ...]}
    """
    from openai import OpenAI

    from config import LLM_BASE_URL, DEEPSEEK_API_KEY

    api_key = os.environ.get("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY)
    if not api_key:
        raise RuntimeError("未设置 DEEPSEEK_API_KEY 环境变量，也未在 config.py 中配置")

    client = OpenAI(api_key=api_key, base_url=LLM_BASE_URL)
    all_judgments: dict[str, list[LLMJudgment]] = {}

    for rule_result in rule_results:
        if not rule_result.hits:
            all_judgments[rule_result.rule_name] = []
            continue

        print(f"  → {rule_result.rule_name}：{rule_result.count} 条疑点，调用 LLM 核实...")

        rule_judgments: list[LLMJudgment] = []

        # 分批调用
        for i in range(0, len(rule_result.hits), batch_size):
            batch = rule_result.hits[i : i + batch_size]
            groups = _extract_voucher_groups(df, batch)
            prompt = _build_prompt(rule_result.rule_name, groups)

            try:
                response = client.chat.completions.create(
                    model=model,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )

                response_text = response.choices[0].message.content
                batch_judgments = _parse_llm_response(response_text)
                rule_judgments.extend(batch_judgments)

                confirmed_count = len(batch_judgments)
                print(f"    批次 {i // batch_size + 1}：发送 {len(batch)} 条，确认 {confirmed_count} 条")

            except Exception as e:
                print(f"    批次 {i // batch_size + 1}：API 调用失败 — {e}")
                # 该批次全部保留（宁多勿漏）
                for hit in batch:
                    rule_judgments.append(
                        LLMJudgment(
                            voucher_id=hit.voucher_id,
                            confirmed=True,
                            risk_level="中",
                            reason=f"LLM 调用失败，疑点保留（{hit.evidence}）",
                            audit_procedures="需人工复核",
                        )
                    )

        all_judgments[rule_result.rule_name] = rule_judgments

    return all_judgments
