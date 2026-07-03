"""LLM 核实解析失败的回归测试。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.llm_verifier import _build_judgments_from_response, _fallback_judgments_for_hits

pytestmark = pytest.mark.unit


def test_build_judgments_from_response_raises_on_unparseable_text() -> None:
    with pytest.raises(ValueError):
        _build_judgments_from_response("模型返回了一段说明，但不是 JSON 数组")


def test_fallback_judgments_keep_hits_for_manual_review() -> None:
    hit = SimpleNamespace(voucher_id="V001", evidence="大额整数金额 1,000,000")

    judgments = _fallback_judgments_for_hits([hit], "LLM 返回解析失败")

    assert len(judgments) == 1
    assert judgments[0].voucher_id == "V001"
    assert judgments[0].confirmed is True
    assert judgments[0].risk_level == "中"
    assert judgments[0].source == "fallback"
    assert "解析失败" in judgments[0].reason
