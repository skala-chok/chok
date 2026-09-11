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


def _lookup_tool(*codes: str) -> MagicMock:
    """find_naver_category_code Tool의 실제 출력 형식을 흉내낸 mock."""
    lines = "\n".join(f"- category_code={c} | 더미 > 경로" for c in codes)
    return _tool(f"검색 결과 카테고리 후보 {len(codes)}건:\n{lines}")


def test_new_product_keyword_trend_calls_tools_and_detects_direction():
    scenario = NewProductKeywordTrendScenario()
    category = _tool("[패션의류]\n  - 2026-01-01: 90\n  - 2026-03-01: 85")
    overall = _tool("[니트]\n  - 2026-01-01: 80\n  - 2026-03-01: 60")
    keyword = _tool(
        "[니트]\n  - 2026-01-01: 90\n  - 2026-03-01: 40\n"
        "[코트]\n  - 2026-01-01: 30\n  - 2026-03-01: 90"
    )
    lookup = _lookup_tool("50000000")
    tools = {
        "find_naver_category_code": lookup,
        "get_shopping_category_trend": category,
        "get_shopping_trends": overall,
        "get_shopping_keyword_trend": keyword,
    }
    params = NewProductKeywordTrendParams(
        category_name="패션의류", category_code="50000000",
        keywords="니트,코트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert lookup.invoke.call_count == 1
    assert category.invoke.call_count == overall.invoke.call_count == keyword.invoke.call_count == 1
    assert "니트: 하락 (90.0 → 40.0)" in result
    assert "코트: 상승 (30.0 → 90.0)" in result
    assert "절대 검색량이 아닙니다" in result
    # 라우터가 준 코드가 실제 후보와 일치하므로 정정 안내는 없어야 한다.
    assert "자동 정정" not in result


def test_new_product_keyword_trend_corrects_hallucinated_code():
    scenario = NewProductKeywordTrendScenario()
    category = _tool("[패션의류]\n  - 2026-01-01: 90\n  - 2026-03-01: 85")
    overall = _tool("[니트]\n  - 2026-01-01: 80\n  - 2026-03-01: 60")
    keyword = _tool("[니트]\n  - 2026-01-01: 90\n  - 2026-03-01: 40")
    # 라우터가 잘못된 코드(50000167)를 줬지만 실제 후보는 50003854뿐인 상황
    lookup = _lookup_tool("50003854")
    tools = {
        "find_naver_category_code": lookup,
        "get_shopping_category_trend": category,
        "get_shopping_trends": overall,
        "get_shopping_keyword_trend": keyword,
    }
    params = NewProductKeywordTrendParams(
        category_name="패션의류", category_code="50000167",
        keywords="니트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert "자동 정정" in result
    assert "50000167" in result and "50003854" in result
    # 실제 Tool 호출에는 정정된 코드가 쓰여야 한다.
    _, kwargs = category.invoke.call_args
    assert "50003854" in category.invoke.call_args[0][0]["categories"]
    assert keyword.invoke.call_args[0][0]["category_code"] == "50003854"


def test_new_product_keyword_trend_empty_code_auto_resolved():
    scenario = NewProductKeywordTrendScenario()
    category = _tool("[패션의류]\n  - 2026-01-01: 90\n  - 2026-03-01: 85")
    overall = _tool("[니트]\n  - 2026-01-01: 80\n  - 2026-03-01: 60")
    keyword = _tool("[니트]\n  - 2026-01-01: 90\n  - 2026-03-01: 40")
    lookup = _lookup_tool("50003854")
    tools = {
        "find_naver_category_code": lookup,
        "get_shopping_category_trend": category,
        "get_shopping_trends": overall,
        "get_shopping_keyword_trend": keyword,
    }
    # category_code 미지정 (빈 문자열 기본값)
    params = NewProductKeywordTrendParams(
        category_name="패션의류",
        keywords="니트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert "자동 조회한 코드" in result
    assert "50003854" in result


def test_target_audience_validation_detects_mismatch():
    scenario = TargetAudienceValidationScenario()
    gender_text = "[50000000]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 30"
    age_text = "[50000000]\n  - 2026-01-01 (40): 100\n  - 2026-01-01 (20): 20"
    tools = {
        "find_naver_category_code": _lookup_tool("50000000"),
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
        "find_naver_category_code": _lookup_tool("50000000"),
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


def test_keyword_audience_segmentation_calls_tools_and_is_discovered():
    scenario = KeywordAudienceSegmentationScenario()
    gender = _tool("[니트]\n  - 2026-01-01 (f): 100\n  - 2026-01-01 (m): 20")
    age = _tool("[니트]\n  - 2026-01-01 (40): 100\n  - 2026-01-01 (20): 10")
    lookup = _lookup_tool("50000000")
    tools = {
        "find_naver_category_code": lookup,
        "get_shopping_keyword_gender_trend": gender,
        "get_shopping_keyword_age_trend": age,
    }
    params = KeywordAudienceSegmentationParams(
        category_code="50000000", keyword="니트", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    assert lookup.invoke.call_count == 1
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


def test_category_code_resolution_falls_back_when_lookup_has_no_candidates():
    scenario = KeywordAudienceSegmentationScenario()
    gender = _tool("[없음]\n  - 2026-01-01 (f): 100")
    age = _tool("[없음]\n  - 2026-01-01 (40): 100")
    no_match = _tool("'xyz'와 일치하는 네이버쇼핑 카테고리를 찾지 못했습니다.")
    tools = {
        "find_naver_category_code": no_match,
        "get_shopping_keyword_gender_trend": gender,
        "get_shopping_keyword_age_trend": age,
    }
    params = KeywordAudienceSegmentationParams(
        category_code="50000000", keyword="xyz", start_date="2026-01-01", end_date="2026-03-01",
    )
    result = scenario.execute(params, tools)

    # 조회 실패 시 given_code를 그대로 쓰되, 신뢰할 수 없다는 경고가 남아야 한다.
    assert "검증하지 못했습니다" in result
    assert "50000000" in result
