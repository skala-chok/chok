# ==============================================================================
# 🟣 [Step 6 - 보라점] 단위 테스트 & 품질 검증 계층
# • 역할: 네이버 쇼핑 데이터랩/인사이트 API 응답을 Mocking하여 1초 내에 통과하는 단위 테스트를 작성합니다.
# • 실행 명령: pytest tests/modules/test_naver_shopping.py -v
# ==============================================================================

import pytest
from unittest.mock import patch, MagicMock
from src.modules.naver_shopping.module import NaverShoppingModule
from src.modules.naver_shopping.tools import (
    get_shopping_trends,
    get_shopping_category_trend,
    get_shopping_category_gender_trend,
    get_shopping_category_age_trend,
    get_shopping_keyword_trend,
    get_shopping_keyword_gender_trend,
    get_shopping_keyword_age_trend,
)
from src.modules.naver_shopping.guardrails import NaverShoppingGuardrail
from src.modules.naver_shopping.context import NaverShoppingContextProvider
from src.modules.naver_shopping.client import NaverShoppingClient
from src.core.guardrails import wrap_tool_with_guardrails


def test_naver_shopping_module_metadata():
    mod = NaverShoppingModule()
    assert mod.name == "naver_shopping"
    assert "쇼핑" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 7
    tool_names = [t.name for t in tools]
    assert "get_shopping_trends" in tool_names
    assert "get_shopping_category_trend" in tool_names
    assert "get_shopping_category_gender_trend" in tool_names
    assert "get_shopping_category_age_trend" in tool_names
    assert "get_shopping_keyword_trend" in tool_names
    assert "get_shopping_keyword_gender_trend" in tool_names
    assert "get_shopping_keyword_age_trend" in tool_names

    guardrails = mod.get_guardrails()
    assert len(guardrails) == 1
    assert isinstance(guardrails[0], NaverShoppingGuardrail)

    ctx = mod.get_context_provider()
    assert isinstance(ctx, NaverShoppingContextProvider)


def test_naver_shopping_module_is_enabled(monkeypatch):
    mod = NaverShoppingModule()

    # Both set
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_ID", "dummy_id")
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_SECRET", "dummy_secret")
    assert mod.is_enabled() is True

    # Only ID set
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_ID", "dummy_id")
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_SECRET", None)
    assert mod.is_enabled() is False

    # Only Secret set
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_ID", None)
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_SECRET", "dummy_secret")
    assert mod.is_enabled() is False

    # Neither set
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_ID", None)
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_SECRET", None)
    assert mod.is_enabled() is False

    # Empty strings
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_ID", "")
    monkeypatch.setattr("src.modules.naver_shopping.module.settings.NAVER_CLIENT_SECRET", "")
    assert mod.is_enabled() is False


def test_naver_shopping_context_provider():
    provider = NaverShoppingContextProvider()
    snippet = provider.get_system_prompt_snippet()
    assert "get_shopping_trends" in snippet
    assert "get_shopping_category_trend" in snippet
    assert "get_shopping_keyword_trend" in snippet
    assert provider.get_dynamic_context("some query") is None


def test_shopping_guardrail_input_validation():
    guard = NaverShoppingGuardrail()

    # Empty query rejection
    res_empty = guard.validate_input("")
    assert res_empty.passed is False
    assert "검색 쿼리가 비어 있습니다" in res_empty.error_message

    res_whitespace = guard.validate_input("   ")
    assert res_whitespace.passed is False

    # Valid query
    res_valid = guard.validate_input("맥북 프로 M3")
    assert res_valid.passed is True


def test_shopping_guardrail_date_validation():
    guard = NaverShoppingGuardrail()

    # 잘못된 날짜 포맷 차단
    res = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026/01/01",
        "end_date": "2026-02-01"
    })
    assert res.passed is False
    assert "YYYY-MM-DD" in res.error_message

    # start_date > end_date 차단
    res_order = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026-03-01",
        "end_date": "2026-02-01"
    })
    assert res_order.passed is False
    assert "start_date" in res_order.error_message

    # 올바른 날짜 통과
    valid = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert valid.passed is True


def test_shopping_guardrail_html_sanitization():
    guard = NaverShoppingGuardrail()
    raw = "상품명: <b>Apple</b> 맥북 프로 &quot;16인치&quot; &amp; 가방"
    cleaned = guard.sanitize_output("get_shopping_trends", raw)
    assert "<b>" not in cleaned
    assert "</b>" not in cleaned
    assert "&quot;" not in cleaned
    assert "&amp;" not in cleaned
    assert cleaned == '상품명: Apple 맥북 프로 "16인치" & 가방'

    # Non-string output
    dict_output = {"data": "test"}
    assert guard.sanitize_output("get_shopping_trends", dict_output) == dict_output


@patch("src.modules.naver_shopping.client.requests.post")
def test_get_shopping_trends_mock(mock_get_datalab):
    mock_get_datalab.return_value.status_code = 200
    mock_get_datalab.return_value.json.return_value = {
        "startDate": "2026-01-01",
        "endDate": "2026-02-01",
        "timeUnit": "month",
        "results": [
            {
                "title": "노트북",
                "keywords": ["노트북"],
                "data": [
                    {"period": "2026-01-01", "ratio": 80.5},
                    {"period": "2026-02-01", "ratio": 95.2}
                ]
            },
            {
                "title": "태블릿",
                "keywords": ["태블릿"],
                "data": [
                    {"period": "2026-01-01", "ratio": 50.0},
                    {"period": "2026-02-01", "ratio": 62.3}
                ]
            }
        ]
    }
    res = get_shopping_trends.invoke({
        "keywords": "노트북, 태블릿",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert "노트북" in res
    assert "95.2%" in res
    assert "태블릿" in res
    assert "62.3%" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_get_shopping_trends_no_results(mock_get_datalab):
    mock_get_datalab.return_value.status_code = 200
    mock_get_datalab.return_value.json.return_value = {"results": []}
    res = get_shopping_trends.invoke({
        "keywords": "희귀키워드",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert "트렌드 조회 결과가 없습니다" in res


def test_get_shopping_trends_empty_keywords():
    res = get_shopping_trends.invoke({
        "keywords": "   ,  ",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert "키워드가 제공되지 않았습니다" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_get_shopping_trends_error_handling(mock_get_datalab):
    mock_get_datalab.side_effect = RuntimeError("API server error")
    res = get_shopping_trends.invoke({
        "keywords": "노트북",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert "트렌드 분석 조회 실패: API server error" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_client_get_datalab_trend_params(mock_post, monkeypatch):
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_ID", "test_id")
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_SECRET", "test_secret")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_post.return_value = mock_resp

    client = NaverShoppingClient()
    res = client.get_datalab_trend(["노트북", "태블릿"], "2026-01-01", "2026-02-01")

    mock_post.assert_called_once_with(
        "https://naverapihub.apigw.ntruss.com/search-trend/v1/search",
        headers={
            "X-NCP-APIGW-API-KEY-ID": "test_id",
            "X-NCP-APIGW-API-KEY": "test_secret",
            "Content-Type": "application/json",
        },
        json={
            "startDate": "2026-01-01",
            "endDate": "2026-02-01",
            "timeUnit": "month",
            "keywordGroups": [
                {"groupName": "노트북", "keywords": ["노트북"]},
                {"groupName": "태블릿", "keywords": ["태블릿"]},
            ],
        },
        timeout=5,
    )
    assert res == {"results": []}


@patch("src.modules.naver_shopping.client.requests.post")
def test_client_get_category_trend_params(mock_post, monkeypatch):
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_ID", "test_id")
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_SECRET", "test_secret")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_post.return_value = mock_resp

    client = NaverShoppingClient()
    client.get_category_trend(
        {"패션의류": "50000000", "화장품/미용": "50000002"}, "2026-01-01", "2026-05-31", gender="f", ages=["20", "30"]
    )

    mock_post.assert_called_once_with(
        "https://naverapihub.apigw.ntruss.com/shopping/v1/categories",
        headers={
            "X-NCP-APIGW-API-KEY-ID": "test_id",
            "X-NCP-APIGW-API-KEY": "test_secret",
            "Content-Type": "application/json",
        },
        json={
            "startDate": "2026-01-01",
            "endDate": "2026-05-31",
            "timeUnit": "month",
            "category": [
                {"name": "패션의류", "param": ["50000000"]},
                {"name": "화장품/미용", "param": ["50000002"]},
            ],
            "gender": "f",
            "ages": ["20", "30"],
        },
        timeout=5,
    )


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_category_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "패션의류", "data": [{"period": "2026-01-01", "ratio": 100}]}]
    }
    res = get_shopping_category_trend.invoke(
        {"categories": "패션의류:50000000", "start_date": "2026-01-01", "end_date": "2026-01-31"}
    )
    assert "패션의류" in res
    assert "100" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_category_gender_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "50000000", "data": [{"period": "2026-01-01", "group": "f", "ratio": 92.4}]}]
    }
    res = get_shopping_category_gender_trend.invoke(
        {"category_code": "50000000", "start_date": "2026-01-01", "end_date": "2026-01-31"}
    )
    assert "(f)" in res
    assert "92.4" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_category_age_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "50000000", "data": [{"period": "2026-01-01", "group": "30", "ratio": 44.1}]}]
    }
    res = get_shopping_category_age_trend.invoke(
        {"category_code": "50000000", "start_date": "2026-01-01", "end_date": "2026-01-31"}
    )
    assert "(30)" in res
    assert "44.1" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_keyword_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "니트", "data": [{"period": "2026-01-01", "ratio": 79.4}]}]
    }
    res = get_shopping_keyword_trend.invoke(
        {
            "category_code": "50000000",
            "keywords": "니트:니트,코트:코트",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
        }
    )
    assert "니트" in res
    assert "79.4" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_keyword_gender_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "니트", "data": [{"period": "2026-01-01", "group": "f", "ratio": 100}]}]
    }
    res = get_shopping_keyword_gender_trend.invoke(
        {"category_code": "50000000", "keyword": "니트", "start_date": "2026-01-01", "end_date": "2026-01-31"}
    )
    assert "(f)" in res


@patch("src.modules.naver_shopping.client.requests.post")
def test_tool_get_shopping_keyword_age_trend(mock_post):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {
        "results": [{"title": "니트", "data": [{"period": "2026-01-01", "group": "40", "ratio": 100}]}]
    }
    res = get_shopping_keyword_age_trend.invoke(
        {"category_code": "50000000", "keyword": "니트", "start_date": "2026-01-01", "end_date": "2026-01-31"}
    )
    assert "(40)" in res


def test_shopping_insight_guardrail_validation():
    guard = NaverShoppingGuardrail()

    # 2017-08-01 이전 날짜 차단
    res = guard.validate_tool_args(
        "get_shopping_category_trend",
        {"categories": "패션의류:50000000", "start_date": "2017-01-01", "end_date": "2017-02-01"},
    )
    assert res.passed is False
    assert "2017-08-01" in res.error_message

    # category 3개 초과 차단
    res_over = guard.validate_tool_args(
        "get_shopping_category_trend",
        {
            "categories": "a:1,b:2,c:3,d:4",
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
        },
    )
    assert res_over.passed is False
    assert "최대 3개" in res_over.error_message

    # keyword 5개 초과 차단
    res_kw_over = guard.validate_tool_args(
        "get_shopping_keyword_trend",
        {
            "category_code": "50000000",
            "keywords": "a:1,b:2,c:3,d:4,e:5,f:6",
            "start_date": "2026-01-01",
            "end_date": "2026-02-01",
        },
    )
    assert res_kw_over.passed is False
    assert "최대 5개" in res_kw_over.error_message

    # 잘못된 time_unit 차단
    res_time_unit = guard.validate_tool_args(
        "get_shopping_category_gender_trend",
        {"category_code": "50000000", "start_date": "2026-01-01", "end_date": "2026-02-01", "time_unit": "year"},
    )
    assert res_time_unit.passed is False
    assert "time_unit" in res_time_unit.error_message

    # 정상 케이스 통과
    res_ok = guard.validate_tool_args(
        "get_shopping_category_trend",
        {"categories": "패션의류:50000000", "start_date": "2026-01-01", "end_date": "2026-02-01"},
    )
    assert res_ok.passed is True

    # Other tools should pass
    assert guard.validate_tool_args("other_tool", {"anything": 100}).passed is True


def test_naver_shopping_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("naver_shopping")
    assert mod is not None
    assert isinstance(mod, NaverShoppingModule)


def test_guardrailed_tool_integration():
    guard = NaverShoppingGuardrail()
    wrapped_trend = wrap_tool_with_guardrails(get_shopping_trends, [guard])
    block_trend = wrapped_trend.invoke({
        "keywords": "노트북",
        "start_date": "invalid_date",
        "end_date": "2026-01-01"
    })
    assert "가드레일 검증 실패" in block_trend
    assert "YYYY-MM-DD" in block_trend

    wrapped_category = wrap_tool_with_guardrails(get_shopping_category_trend, [guard])
    block_category = wrapped_category.invoke({
        "categories": "a:1,b:2,c:3,d:4",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01",
    })
    assert "가드레일 검증 실패" in block_category
    assert "최대 3개" in block_category
