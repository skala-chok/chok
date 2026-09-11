from unittest.mock import MagicMock

from src.core.scenario_registry import ScenarioRegistry
from src.scenarios.naver_trend_analysis.scenario import (
    KeywordAudienceSegmentationParams, KeywordAudienceSegmentationScenario,
    NewProductKeywordTrendParams, NewProductKeywordTrendScenario,
    TargetAudienceValidationParams, TargetAudienceValidationScenario,
)


from tests.conftest import make_tool_mock as _tool


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
    # 보고서 형식(표/섹션)으로 구성되어야 한다.
    assert "### 2. 분야 전체 클릭 트렌드" in result
    assert "### 5. 추세 판정 및 결론" in result
    assert "| 니트 | 2026-01-01 | 90.0 |" in result
    assert "니트: 하락 (90.0 → 40.0)" in result
    assert "코트: 상승 (30.0 → 90.0)" in result
    assert "**상승 키워드**: 코트" in result
    assert "**하락 키워드**: 니트" in result
    assert "절대 검색량을 의미하지 않습니다." in result
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


def test_target_audience_validation_falls_back_to_keyword_when_category_name_empty():
    """실제 버그 재현: 라우터가 category_name을 빈 문자열로 넘겨도 keyword로 정상 조회되어야 한다."""
    scenario = TargetAudienceValidationScenario()
    gender_text = "[러닝화]\n  - 2026-06-01 (f): 20\n  - 2026-06-01 (m): 100"
    age_text = "[러닝화]\n  - 2026-06-01 (40): 100\n  - 2026-06-01 (20): 10"
    lookup = _lookup_tool("50003854")
    tools = {
        "find_naver_category_code": lookup,
        "get_shopping_category_gender_trend": _tool(gender_text),
        "get_shopping_category_age_trend": _tool(age_text),
        "get_shopping_keyword_gender_trend": _tool(gender_text),
        "get_shopping_keyword_age_trend": _tool(age_text),
    }
    params = TargetAudienceValidationParams(
        category_name="", category_code="", keyword="러닝화",
        target_gender="m", target_age="40", start_date="2026-06-11", end_date="2026-09-11",
    )
    result = scenario.execute(params, tools)

    # find_naver_category_code가 빈 category_name이 아니라 keyword("러닝화")로 호출돼야 한다.
    lookup.invoke.assert_called_once_with({"keyword": "러닝화"})
    assert "가드레일" not in result
    # code_note 안내문에 자동 조회된 코드가 언급돼야 한다 (category_name이 비어 keyword로 대체 조회됨).
    assert "50003854" in result
    assert "### 4. 타겟 일치 여부 판정" in result
    assert "일치" in result


def test_target_audience_validation_early_exit_when_no_search_term_available():
    scenario = TargetAudienceValidationScenario()
    tools = {"find_naver_category_code": _lookup_tool("50000000")}
    params = TargetAudienceValidationParams(
        category_name="", category_code="", keyword="",
        target_gender="m", target_age="20", start_date="2026-06-11", end_date="2026-09-11",
    )
    result = scenario.execute(params, tools)

    assert "비어 있어" in result
    # 검색어가 아예 없으므로 조회 Tool을 시도조차 하지 않아야 한다.
    tools["find_naver_category_code"].invoke.assert_not_called()


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
    # 보고서 형식(표 + 결론 섹션)으로 구성되어야 한다.
    assert "### 2. 성별 분포" in result
    assert "| 니트 | 2026-01-01 | 여성 | 100.0 |" in result
    assert "### 3. 연령대별 분포" in result
    assert "| 니트 | 2026-01-01 | 40대 | 100.0 |" in result
    assert "최고 관심 세그먼트: **여성**" in result
    assert "최고 관심 세그먼트: **40대**" in result
    assert "광고 타겟팅은 **여성** · **40대**를 중심으로" in result

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


def test_scenario_execution_does_not_pollute_global_state():
    """시나리오 실행 시 모듈 전역 LAST_RUN_TOOL_RESULTS를 오염시키지 않는지 검증."""
    from src.scenarios.naver_trend_analysis.scenario import (
        LAST_RUN_TOOL_RESULTS,
        TargetAudienceValidationParams,
        TargetAudienceValidationScenario,
    )

    scenario = TargetAudienceValidationScenario()
    tools = {
        "find_naver_category_code": _lookup_tool("50000000"),
        "get_shopping_category_gender_trend": _tool("[분야]\n  - 2026-01-01 (f): 100"),
        "get_shopping_category_age_trend": _tool("[분야]\n  - 2026-01-01 (20): 100"),
        "get_shopping_keyword_gender_trend": _tool("[키워드]\n  - 2026-01-01 (f): 100"),
        "get_shopping_keyword_age_trend": _tool("[키워드]\n  - 2026-01-01 (20): 100"),
    }
    params = TargetAudienceValidationParams(
        category_name="패션의류",
        keyword="러닝화",
        target_gender="여성",
        target_age="20대",
    )

    scenario.execute(params, tools)

    # 전역 dict에 잔여 상태가 남지 않아야 함 (세션/턴 간 누수 방지)
    assert len(LAST_RUN_TOOL_RESULTS) == 0
