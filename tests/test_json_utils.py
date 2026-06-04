"""LLM JSON 解析的回归测试。

LLM 常把 JSON 包在 markdown 代码块里、或夹带解释文字。这层解析的兜底能力
决定 LLM 规则校准/核实结果能否落地，解析失败必须显式抛错而非静默返回空。
"""

from __future__ import annotations

import pytest

from modules.json_utils import extract_json, parse_json_dict, parse_json_list

pytestmark = pytest.mark.unit


def test_extract_json_strips_code_fence() -> None:
    text = "```json\n{\"a\": 1}\n```"
    assert extract_json(text) == '{"a": 1}'


def test_parse_json_dict_plain() -> None:
    assert parse_json_dict('{"x": 1, "y": 2}') == {"x": 1, "y": 2}


def test_parse_json_dict_with_code_fence() -> None:
    assert parse_json_dict("```json\n{\"x\": 1}\n```") == {"x": 1}


def test_parse_json_dict_regex_fallback_with_surrounding_text() -> None:
    # 模型在 JSON 前后夹带说明文字
    text = "这是结果：{\"score\": 0.9} 以上。"
    assert parse_json_dict(text) == {"score": 0.9}


def test_parse_json_dict_raises_on_garbage() -> None:
    with pytest.raises(ValueError):
        parse_json_dict("完全不是 JSON")


def test_parse_json_dict_rejects_list() -> None:
    with pytest.raises(ValueError):
        parse_json_dict("[1, 2, 3]")


def test_parse_json_list_with_fence_and_text() -> None:
    text = "结果如下\n```\n[{\"id\": 1}, {\"id\": 2}]\n```"
    assert parse_json_list(text) == [{"id": 1}, {"id": 2}]


def test_parse_json_list_rejects_dict() -> None:
    with pytest.raises(ValueError):
        parse_json_list('{"a": 1}')
