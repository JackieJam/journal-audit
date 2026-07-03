"""列名映射匹配测试：分层匹配（精确/别名/子串/模糊）+ 冲突消解 + 置信度。

列名匹配错误 = 下游所有按标准列取数的分析全错，且模糊匹配天然有误报风险，
所以必须有回归测试守住：高置信精确命中不退化、模糊命中有但被标记低置信、
一个源列不能被两个标准列同时认领。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from modules.ingestion import (
    ColumnMatch,
    _suggest_mapping,
    suggest_mapping_with_confidence,
)

pytestmark = pytest.mark.unit


def test_exact_match_is_full_confidence() -> None:
    matches = suggest_mapping_with_confidence(["凭证编号", "过账日期"])
    assert matches["凭证编号"].source == "凭证编号"
    assert matches["凭证编号"].score == pytest.approx(1.0)
    assert matches["凭证编号"].method == "exact"


def test_alias_match_high_but_not_full_confidence() -> None:
    # "凭证号" 是 凭证编号 的别名
    matches = suggest_mapping_with_confidence(["凭证号"])
    assert matches["凭证编号"].source == "凭证号"
    assert matches["凭证编号"].method == "alias"
    assert 0.9 <= matches["凭证编号"].score < 1.0


def test_containment_matches_unlisted_variant() -> None:
    # "记账凭证编号" 不在别名里，但包含标准名 → 子串命中
    matches = suggest_mapping_with_confidence(["记账凭证编号"])
    assert "凭证编号" in matches
    assert matches["凭证编号"].source == "记账凭证编号"
    assert matches["凭证编号"].method in ("contains", "fuzzy")
    assert matches["凭证编号"].score < 0.95  # 低于别名，应被 UI 标记确认


def test_fuzzy_matches_typo_variant() -> None:
    # "过帐日期"（帐/账）即便不在别名也应模糊命中过账日期
    matches = suggest_mapping_with_confidence(["过帐日期"])
    assert "过账日期" in matches
    assert matches["过账日期"].source == "过帐日期"


def test_unrelated_column_not_matched() -> None:
    matches = suggest_mapping_with_confidence(["完全无关的随机列ABC"])
    # 不应误认领任何核心标准列
    assert "凭证编号" not in matches
    assert "过账日期" not in matches
    assert "凭证货币价值" not in matches


def test_one_source_column_claimed_by_only_one_standard() -> None:
    # 单独一个 "科目" 既像 总账科目 又像 总账科目：长文本，只能归一个
    matches = suggest_mapping_with_confidence(["科目"])
    claimed = [m.source for m in matches.values()]
    assert claimed.count("科目") <= 1


def test_exact_beats_fuzzy_on_conflict() -> None:
    # 同时给精确的 总账科目 和易混的 总账科目：长文本 的源列，
    # 精确列必须归 总账科目，不被模糊抢走
    matches = suggest_mapping_with_confidence(["总账科目", "总账科目：长文本"])
    assert matches["总账科目"].source == "总账科目"
    assert matches["总账科目"].method == "exact"


def test_backward_compat_suggest_mapping_returns_name_dict() -> None:
    result = _suggest_mapping(["凭证编号", "过账日期", "凭证货币价值"])
    assert result["凭证编号"] == "凭证编号"
    assert result["过账日期"] == "过账日期"
    assert isinstance(result["凭证货币价值"], str)


def test_column_match_is_immutable() -> None:
    m = ColumnMatch(source="x", score=1.0, method="exact")
    with pytest.raises(FrozenInstanceError):
        m.score = 0.5  # type: ignore[misc]


def test_result_is_deterministic() -> None:
    cols = ["凭证号", "过帐日期", "本币金额", "科目编码", "用户"]
    first = suggest_mapping_with_confidence(cols)
    second = suggest_mapping_with_confidence(cols)
    assert {k: v.source for k, v in first.items()} == {k: v.source for k, v in second.items()}
