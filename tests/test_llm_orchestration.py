"""components.llm_orchestration 纯函数单元测试。

覆盖推荐逻辑的无状态部分：缓存键、payload 记录裁剪、条件归一化、模块归属判定、
建议目标文本与回查逻辑文本。编排器（_render_candidate_recommendations_for_module 等）
仍在 app.py，由 AppTest 间接覆盖。
"""

from __future__ import annotations

import pandas as pd
import pytest

from components.llm_orchestration import (
    normalise_recommendation_condition,
    recommendation_condition_text,
    recommendation_matches_module,
    recommendation_target_text,
    records_for_payload,
    unified_llm_key,
)

pytestmark = pytest.mark.unit


class TestUnifiedLlmKey:
    def test_sorts_years_and_joins(self):
        assert unified_llm_key([2022, 2020, 2021], "收入") == "unified::2020,2021,2022::收入"

    def test_empty_years(self):
        assert unified_llm_key([], "总计") == "unified::::总计"


class TestRecordsForPayload:
    def test_empty_df_returns_empty_list(self):
        assert records_for_payload(pd.DataFrame()) == []

    def test_truncates_to_limit(self):
        df = pd.DataFrame({"a": range(100)})
        assert len(records_for_payload(df, limit=10)) == 10

    def test_datetime_columns_formatted(self):
        df = pd.DataFrame({"过账日期": pd.to_datetime(["2023-01-15", "2023-02-20"])})
        out = records_for_payload(df)
        assert out[0]["过账日期"] == "2023-01-15"
        assert out[1]["过账日期"] == "2023-02-20"


class TestNormaliseRecommendationCondition:
    def test_none_returns_empty_dict(self):
        assert normalise_recommendation_condition(None) == {}

    def test_metric_chinese_mapped_to_english(self):
        assert normalise_recommendation_condition({"metric": "净收入"})["metric"] == "revenue"
        assert normalise_recommendation_condition({"metric": "成本"})["metric"] == "cost"

    def test_unknown_metric_kept_stripped(self):
        assert normalise_recommendation_condition({"metric": " foo "})["metric"] == "foo"

    def test_direction_mapped(self):
        assert normalise_recommendation_condition({"direction": "收入S异常"})["direction"] == "income_s"

    def test_months_list_cleaned_to_int(self):
        out = normalise_recommendation_condition({"months": ["1月", "3月", "bad"]})
        assert out["months"] == [1, 3]

    def test_single_month_expands_to_months(self):
        out = normalise_recommendation_condition({"month": "12月"})
        assert out["month"] == 12 and out["months"] == [12]

    def test_text_fields_stripped(self):
        out = normalise_recommendation_condition({"customer": "  ACME  ", "voucher_id": " V1 "})
        assert out["customer"] == "ACME" and out["voucher_id"] == "V1"

    def test_does_not_mutate_input(self):
        original = {"metric": "净收入"}
        normalise_recommendation_condition(original)
        assert original == {"metric": "净收入"}


class TestRecommendationMatchesModule:
    def test_income_cost_by_kind(self):
        rec = {"condition": {"kind": "customer_revenue"}}
        assert recommendation_matches_module(rec, "收入成本") is True

    def test_expense_by_source_module(self):
        rec = {"source_module": "费用分析"}
        assert recommendation_matches_module(rec, "费用") is True

    def test_no_match_returns_false(self):
        rec = {"source_module": "收入成本", "condition": {"kind": "monthly_income_cost"}}
        assert recommendation_matches_module(rec, "费用") is False

    def test_unknown_module_filter_returns_true(self):
        assert recommendation_matches_module({}, "随便") is True


class TestRecommendationTargetText:
    def test_monthly_income_cost(self):
        rec = {"condition": {"kind": "monthly_income_cost", "year": 2023, "month": 5, "metric": "gross"}}
        assert recommendation_target_text(rec) == "2023年5月 毛利"

    def test_customer_revenue(self):
        rec = {"condition": {"kind": "customer_revenue", "year": 2023, "customer": "ACME"}}
        assert recommendation_target_text(rec) == "2023年 客户 ACME 收入"

    def test_unknown_kind_falls_back_to_title(self):
        rec = {"condition": {"kind": "???"}, "title": "自定义建议"}
        assert recommendation_target_text(rec) == "自定义建议"

    def test_missing_title_default(self):
        assert recommendation_target_text({}) == "未命名建议"


class TestRecommendationConditionText:
    def test_monthly_income_cost_normalises_metric(self):
        # 传入中文 metric，应被 normalise 成毛利标签
        text = recommendation_condition_text(
            {"kind": "monthly_income_cost", "year": 2023, "months": ["5月"], "metric": "毛利"},
            "收入成本",
        )
        assert "2023" in text and "5月" in text and "毛利" in text

    def test_cross_year_finding(self):
        text = recommendation_condition_text(
            {"kind": "cross_year_finding", "category": "悬空预提", "years": [2022, 2023]},
            "跨年交叉稽核",
        )
        assert "悬空预提" in text and "2022" in text and "2023" in text

    def test_unmatched_returns_generic(self):
        assert recommendation_condition_text({"kind": "???"}, "收入成本") == "按模型给出的筛选条件回查对应分录。"

    def test_adjustment_voucher(self):
        text = recommendation_condition_text(
            {"kind": "adjustment_voucher", "year": 2023, "voucher_id": "V100"}, "调账冲销"
        )
        assert "V100" in text and "2023" in text
