"""列名沉淀（学习库）测试。

让工具「越用越聪明」：用户每次确认的列映射沉淀到经验库，下次同名源列直接高置信命中。
学习库的 key 归一化必须与 ingestion._normalize 完全一致，否则学过的别名查不回来——
这条由 test_normalization_matches_ingestion 跨模块锁死。
"""

from __future__ import annotations

import pytest

from modules import knowledge_base as kb
from modules.ingestion import (
    STANDARD_COLUMNS_BY_NAME,
    _normalize,
    suggest_mapping_with_confidence,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolate_home(tmp_path, monkeypatch):
    """隔离 ~/.audit_tool，避免污染真实经验库。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    kb.consume_load_warnings()
    yield
    kb.consume_load_warnings()


# ── 学习库读写 ──────────────────────────────────────────────


def test_recorded_mapping_becomes_learned_alias() -> None:
    kb.record_column_mappings({"凭证编号": "记账凭证号"})
    learned = kb.learned_column_aliases()
    assert learned.get(_normalize("记账凭证号")) == "凭证编号"


def test_trivial_exact_mapping_not_recorded() -> None:
    # 源列名就是标准名，无沉淀价值
    kb.record_column_mappings({"凭证编号": "凭证编号"})
    assert kb.learned_column_aliases() == {}


def test_empty_or_blank_source_ignored() -> None:
    kb.record_column_mappings({"凭证编号": "", "过账日期": "   "})
    assert kb.learned_column_aliases() == {}


def test_whitespace_variants_collapse_to_same_key() -> None:
    kb.record_column_mappings({"凭证编号": "记账凭证号"})
    kb.record_column_mappings({"凭证编号": " 记账凭证号 "})
    learned = kb.learned_column_aliases()
    # 两次写入归一化后是同一个 key，只有一条
    assert list(learned.keys()) == [_normalize("记账凭证号")]


def test_conflict_resolved_by_count() -> None:
    # 同一源列被先后映射到两个标准列，高频者胜出
    kb.record_column_mappings({"过账日期": "业务日期"})
    kb.record_column_mappings({"凭证日期": "业务日期"})
    kb.record_column_mappings({"凭证日期": "业务日期"})
    learned = kb.learned_column_aliases()
    assert learned[_normalize("业务日期")] == "凭证日期"  # 2 次 > 1 次


def test_record_returns_count() -> None:
    n = kb.record_column_mappings({"凭证编号": "记账凭证号", "过账日期": "记账日"})
    assert n == 2


# ── 与匹配器集成 ────────────────────────────────────────────


def test_learned_alias_drives_high_confidence_match() -> None:
    learned = {_normalize("记账凭证号"): "凭证编号"}
    matches = suggest_mapping_with_confidence(["记账凭证号"], learned=learned)
    assert matches["凭证编号"].source == "记账凭证号"
    assert matches["凭证编号"].method == "learned"
    assert matches["凭证编号"].score > 0.95  # 高于别名/模糊


def test_exact_source_name_beats_learned_override() -> None:
    # 即使学习库里有一条错误/冲突的映射，源列名就是标准名时精确命中必须胜出
    learned = {_normalize("凭证编号"): "过账日期"}
    matches = suggest_mapping_with_confidence(["凭证编号"], learned=learned)
    assert matches["凭证编号"].source == "凭证编号"
    assert matches["凭证编号"].method == "exact"
    # 错误的学习项没把 凭证编号 抢去 过账日期
    assert matches.get("过账日期") is None


def test_learned_std_not_in_schema_is_ignored() -> None:
    learned = {_normalize("记账凭证号"): "不存在的标准列"}
    assert "不存在的标准列" not in STANDARD_COLUMNS_BY_NAME
    matches = suggest_mapping_with_confidence(["记账凭证号"], learned=learned)
    # 退回子串/模糊命中，而非采用非法标准列
    assert matches["凭证编号"].method in ("contains", "fuzzy")


# ── 归一化一致性（跨模块锁死）──────────────────────────────


def test_normalization_matches_ingestion() -> None:
    samples = ["记账凭证号", " 过账日期 ", "总账科目：长文本", "Doc No.", "本币金额(元)"]
    for s in samples:
        assert kb._norm_col(s) == _normalize(s)
