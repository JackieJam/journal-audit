"""components.llm_orchestration 纯函数单元测试。

覆盖推荐逻辑的无状态部分：缓存键、payload 记录裁剪、条件归一化、模块归属判定、
建议目标文本与回查逻辑文本。编排器（_render_candidate_recommendations_for_module 等）
仍在 app.py，由 AppTest 间接覆盖。
"""

from __future__ import annotations

import pandas as pd
import pytest

from components.llm_orchestration import (
    backfill_recommendation_condition,
    normalise_label,
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


class TestNormaliseLabel:
    def test_strips_whitespace_and_inner_spaces(self):
        assert normalise_label("  A B\tC\n ") == "ABC"

    def test_none_returns_empty(self):
        assert normalise_label(None) == ""

    def test_non_str_coerced(self):
        assert normalise_label(123) == "123"


class TestBackfillRecommendationCondition:
    """仅测不触 st.session_state 的分支（收入成本 / 费用）；
    跨年 / 统计画像分支读 year_map，留给 AppTest 基线覆盖。

    历史背景：源码正则曾被过度转义（如 ``r"(\\d{1,2})月"`` 实际匹配字面量 ``\\d``
    而非数字），导致 year/gross/expense/中文客户名 的文本推断从不触发。该潜伏 bug
    已修复为正确的单反斜杠转义，以下断言锁定**修复后**的真实推断行为。"""

    def test_income_cost_passes_through_existing_kind(self):
        rec = {"condition": {"kind": "customer_revenue", "customer": "ACME", "year": 2023}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["kind"] == "customer_revenue" and out["customer"] == "ACME"

    def test_income_cost_infers_customer_from_ascii_text(self):
        # customer 文本推断对 ASCII 客户名生效（字符类含 A-Za-z）。
        rec = {"title": "客户ACME收入异常", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["kind"] == "customer_revenue"
        assert "ACME" in out["customer"]

    def test_income_cost_infers_chinese_customer(self):
        # 修复后：中文客户名（字符类含 一-鿿）能被正确推断。
        rec = {"title": "客户北京远大科技收入异常", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["kind"] == "customer_revenue"
        assert out["customer"] == "北京远大科技"

    def test_income_cost_infers_chinese_supplier(self):
        # 修复后：中文供应商名能被正确推断。
        rec = {"title": "供应商上海宏达暂估异常", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["kind"] == "supplier_payable"
        assert out["supplier"] == "上海宏达"

    def test_gross_inference_now_works(self):
        # 修复后：r"(\d{1,2})月" 正确匹配数字，毛利推断生效。
        rec = {"title": "3月毛利异常波动", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["kind"] == "monthly_income_cost"
        assert out["metric"] == "gross"
        assert 3 in out["months"]

    def test_expense_inference_now_works(self):
        rec = {"title": "费用类别 业务招待费 偏高", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "费用")
        assert out["kind"] == "expense_category"

    def test_year_inference_now_works(self):
        rec = {"title": "2023年收入异常", "reason": "", "condition": {}}
        out = backfill_recommendation_condition(rec, "总计", "收入成本")
        assert out["year"] == 2023
