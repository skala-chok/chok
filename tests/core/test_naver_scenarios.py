from unittest.mock import MagicMock

from src.core.scenario_registry import ScenarioRegistry
from src.scenarios.naver_trend_analysis.scenario import (
    KeywordAudienceSegmentationParams, KeywordAudienceSegmentationScenario,
    NewProductKeywordTrendParams, NewProductKeywordTrendScenario,
    TargetAudienceValidationParams, TargetAudienceValidationScenario,
)


def _tool(result: str) -> MagicMock:
    tool = MagicMock()
    tool.invoke.return_value = result
    return tool


def test_new_product_keyword_trend_calls_three_tools_and_detects_direction():
    scenario = NewProductKeywordTrendScenario()
    category = _tool("[패션의류]\n  - 2026-01-01: 90\n  - 2026-03-01: 85")
    overall = _tool("[니트]\n  - 2026-01-01: 80\n  - 2026-03-01: 60")
    keyword = _tool(
        "[니트]\n  - 2026-01-01: 90\n  - 2026-03-01: 40\n"
        "[코트]\n  - 2026-01-01: 30\n  - 2026-03-01: 90"
    )
    tools = {
        "get_shopping_category_trend": category,
        "get_shopping_trends": overall,
        "get_shopping_keyword_trend": keyword,
    }
    params = NewProductKeywordTrendParams(
        category_name="패션의류", category_code="50000000",
        keywords="니트,코트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert category.invoke.call_count == overall.invoke.call_count == keyword.invoke.call_count == 1
    assert "니트: 하락 (90.0 → 40.0)" in result
    assert "코트: 상승 (30.0 → 90.0)" in result
    assert "절대 검색량이 아닙니다" in result


def test_target_audience_validation_detects_mismatch():
    scenario = TargetAudienceValidationScenario()
    gender_text = "[50000000]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 30"
    age_text = "[50000000]\n  - 2026-01-01 (40): 100\n  - 2026-01-01 (20): 20"
    tools = {
        "get_shopping_category_gender_trend": _tool(gender_text),
        "get_shopping_category_age_trend": _tool(age_text),
        "get_shopping_keyword_gender_trend": _tool(gender_text),
        "get_shopping_keyword_age_trend": _tool(age_text),
    }
    params = TargetAudienceValidationParams(
        category_name="패션의류", category_code="50000000", keyword="니트",
        target_gender="m", target_age="20", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert "불일치" in result
    assert "'f'(ratio 100.0)" in result


def test_target_audience_validation_confirms_match():
    scenario = TargetAudienceValidationScenario()
    gender_text = "[50000000]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 30"
    age_text = "[50000000]\n  - 2026-01-01 (40): 100\n  - 2026-01-01 (20): 20"
    tools = {
        "get_shopping_category_gender_trend": _tool(gender_text),
        "get_shopping_category_age_trend": _tool(age_text),
        "get_shopping_keyword_gender_trend": _tool(gender_text),
        "get_shopping_keyword_age_trend": _tool(age_text),
    }
    params = TargetAudienceValidationParams(
        category_name="패션의류", category_code="50000000", keyword="니트",
        target_gender="f", target_age="40", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert "일치" in result
    assert "불일치" not in result


def test_keyword_audience_segmentation_calls_two_tools_and_is_discovered():
    scenario = KeywordAudienceSegmentationScenario()
    gender = _tool("[니트]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 20")
    age = _tool("[니트]\n  - 2026-01-01 (40): 100\n  - 2026-01-01 (20): 10")
    tools = {"get_shopping_keyword_gender_trend": gender, "get_shopping_keyword_age_trend": age}
    params = KeywordAudienceSegmentationParams(
        category_code="50000000", keyword="니트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert gender.invoke.call_count == age.invoke.call_count == 1
    assert "가장 관심도 높은 성별: f" in result
    assert "가장 관심도 높은 연령대: 40대" in result

    registry = ScenarioRegistry()
    registry.discover_scenarios()
    assert {
        "naver_new_product_keyword_trend",
        "naver_target_audience_validation",
        "naver_keyword_audience_segmentation",
    } <= set(item.name for item in registry.get_all_scenarios())
