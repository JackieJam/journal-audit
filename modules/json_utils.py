"""
统一 JSON 解析工具：处理 LLM 返回的 JSON（含 markdown 代码块、正则兜底提取）。
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> str:
    """去掉 markdown 代码块包裹，返回纯 JSON 字符串。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = next((i + 1 for i, l in enumerate(lines) if l.startswith("```")), 1)
        end = next((i for i, l in enumerate(lines[start:], start) if l.startswith("```")), len(lines))
        text = "\n".join(lines[start:end]).strip()
    return text


def parse_json_dict(text: str) -> dict[str, Any]:
    """解析 LLM 返回的 JSON 对象，自动处理 markdown 代码块 + 正则兜底。

    Raises:
        ValueError: JSON 无法解析时抛出。
    """
    text = extract_json(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"LLM 返回内容无法解析为 JSON 对象：{text[:200]}")
    if not isinstance(data, dict):
        raise ValueError("LLM 返回内容不是 JSON 对象")
    return data


def parse_json_list(text: str) -> list[dict[str, Any]]:
    """解析 LLM 返回的 JSON 数组，自动处理 markdown 代码块 + 正则兜底。

    Raises:
        ValueError: JSON 无法解析时抛出。
    """
    text = extract_json(text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"LLM 返回内容无法解析为 JSON 数组：{text[:200]}")
    if not isinstance(data, list):
        raise ValueError("LLM 返回内容不是 JSON 数组")
    return data
