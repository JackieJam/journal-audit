"""经验库加载鲁棒性测试（覆盖 P0 修复）。

验证「风险可见」：配置文件损坏时不静默吞错，而是隔离备份 + 登记可见告警。
文件不存在属正常，不应产生告警。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules import knowledge_base as kb

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_warnings():
    kb.consume_load_warnings()  # 清空前序累积
    yield
    kb.consume_load_warnings()


def test_missing_file_is_silent(tmp_path: Path) -> None:
    result = kb._read_json_file(tmp_path / "nope.json", [])
    assert result == []
    assert kb.consume_load_warnings() == []  # 不存在不报警


def test_valid_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text('[{"a": 1}]', encoding="utf-8")
    assert kb._read_json_file(path, []) == [{"a": 1}]
    assert kb.consume_load_warnings() == []


def test_corrupt_file_warns_and_quarantines(tmp_path: Path) -> None:
    path = tmp_path / "rule_library.json"
    path.write_text("{ this is not valid json ]", encoding="utf-8")

    result = kb._read_json_file(path, [])

    assert result == []  # 降级返回默认值
    warnings = kb.consume_load_warnings()
    assert len(warnings) == 1
    assert "rule_library.json" in warnings[0]
    # 损坏文件被隔离备份，原始数据未丢失
    quarantines = list(tmp_path.glob("rule_library.json.corrupt-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_text(encoding="utf-8") == "{ this is not valid json ]"


def test_consume_clears_warnings(tmp_path: Path) -> None:
    path = tmp_path / "llm_profiles.json"
    path.write_text("not json", encoding="utf-8")
    kb._read_json_file(path, [])
    assert kb.consume_load_warnings()        # 第一次取出有内容
    assert kb.consume_load_warnings() == []  # 第二次已清空
