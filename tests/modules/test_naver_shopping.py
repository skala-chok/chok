import pytest
from unittest.mock import patch, MagicMock
from src.modules.naver_shopping.module import NaverShoppingModule
from src.modules.naver_shopping.tools import search_naver_shopping, get_shopping_trends
from src.modules.naver_shopping.guardrails import NaverShoppingGuardrail
from src.modules.naver_shopping.context import NaverShoppingContextProvider
from src.modules.naver_shopping.client import NaverShoppingClient
from src.core.guardrails import wrap_tool_with_guardrails


def test_naver_shopping_module_metadata():
    mod = NaverShoppingModule()
    assert mod.name == "naver_shopping"
    assert "쇼핑" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 2
    tool_names = [t.name for t in tools]
    assert "search_naver_shopping" in tool_names
    assert "get_shopping_trends" in tool_names

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
    assert "search_naver_shopping" in snippet
    assert "get_shopping_trends" in snippet
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

    # 올바른 날짜 통과
    valid = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert valid.passed is True


def test_shopping_guardrail_display_and_sort_validation():
    guard = NaverShoppingGuardrail()

    # display validation (1 to 10)
    assert guard.validate_tool_args("search_naver_shopping", {"query": "test", "display": 5}).passed is True
    assert guard.validate_tool_args("search_naver_shopping", {"query": "test", "display": 1}).passed is True
    assert guard.validate_tool_args("search_naver_shopping", {"query": "test", "display": 10}).passed is True
    assert guard.validate_tool_args("search_naver_shopping", {"query": "test"}).passed is True

    res_too_large = guard.validate_tool_args("search_naver_shopping", {"query": "test", "display": 11})
    assert res_too_large.passed is False
    assert "display" in res_too_large.error_message

    res_too_small = guard.validate_tool_args("search_naver_shopping", {"query": "test", "display": 0})
    assert res_too_small.passed is False
    assert "display" in res_too_small.error_message

    # sort validation ('sim', 'date', 'asc', 'dsc')
    for s in ["sim", "date", "asc", "dsc"]:
        assert guard.validate_tool_args("search_naver_shopping", {"query": "test", "sort": s}).passed is True

    res_invalid_sort = guard.validate_tool_args("search_naver_shopping", {"query": "test", "sort": "invalid"})
    assert res_invalid_sort.passed is False
    assert "sort" in res_invalid_sort.error_message

    # Other tools should pass
    assert guard.validate_tool_args("other_tool", {"display": 100}).passed is True


def test_shopping_guardrail_html_sanitization():
    guard = NaverShoppingGuardrail()
    raw = "상품명: <b>Apple</b> 맥북 프로 &quot;16인치&quot; &amp; 가방"
    cleaned = guard.sanitize_output("search_naver_shopping", raw)
    assert "<b>" not in cleaned
    assert "</b>" not in cleaned
    assert "&quot;" not in cleaned
    assert "&amp;" not in cleaned
    assert cleaned == '상품명: Apple 맥북 프로 "16인치" & 가방'

    # Non-string output
    dict_output = {"data": "test"}
    assert guard.sanitize_output("search_naver_shopping", dict_output) == dict_output


@patch("src.modules.naver_shopping.client.requests.get")
def test_search_naver_shopping_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "맥북 프로 M3",
                "link": "https://shopping.naver.com/1",
                "lprice": "2390000",
                "mallName": "네이버공식몰"
            }
        ]
    }
    res = search_naver_shopping.invoke({"query": "맥북 프로", "display": 1})
    assert "맥북 프로 M3" in res
    assert "2,390,000" in res or "2390000" in res
    assert "네이버공식몰" in res
    assert "https://shopping.naver.com/1" in res


@patch("src.modules.naver_shopping.client.requests.get")
def test_search_naver_shopping_price_formatting(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "<b>아이폰</b> 16 프로",
                "link": "https://shopping.naver.com/iphone",
                "lprice": "1550000",
                "mallName": "애플스토어"
            },
            {
                "title": "갤럭시 S24",
                "link": "https://shopping.naver.com/galaxy",
                "lprice": "1150000",
                "mallName": "삼성공식몰"
            }
        ]
    }
    res = search_naver_shopping.invoke({"query": "스마트폰", "display": 2})
    assert "아이폰 16 프로" in res
    assert "<b>" not in res
    assert "1,550,000원" in res
    assert "1,150,000원" in res


@patch("src.modules.naver_shopping.client.requests.get")
def test_search_naver_shopping_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    res = search_naver_shopping.invoke({"query": "결과없는상품검색어", "display": 5})
    assert "네이버 쇼핑 검색 결과가 없습니다" in res


@patch("src.modules.naver_shopping.client.requests.get")
def test_search_naver_shopping_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("Connection timeout")
    res = search_naver_shopping.invoke({"query": "노트북", "display": 1})
    assert "네이버 쇼핑 검색 실패: Connection timeout" in res


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


@patch("src.modules.naver_shopping.client.requests.get")
def test_client_search_shop_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_ID", "test_id")
    monkeypatch.setattr("src.modules.naver_shopping.client.settings.NAVER_CLIENT_SECRET", "test_secret")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = NaverShoppingClient()
    res = client.search_shop("노트북", display=3, sort="dsc")

    mock_get.assert_called_once_with(
        "https://openapi.naver.com/v1/search/shop.json",
        headers={
            "X-Naver-Client-Id": "test_id",
            "X-Naver-Client-Secret": "test_secret",
            "Content-Type": "application/json",
        },
        params={"query": "노트북", "display": 3, "sort": "dsc"},
        timeout=5,
    )
    assert res == {"items": []}


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
        "https://openapi.naver.com/v1/datalab/search",
        headers={
            "X-Naver-Client-Id": "test_id",
            "X-Naver-Client-Secret": "test_secret",
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


def test_naver_shopping_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("naver_shopping")
    assert mod is not None
    assert isinstance(mod, NaverShoppingModule)


def test_guardrailed_tool_integration():
    guard = NaverShoppingGuardrail()
    wrapped_search = wrap_tool_with_guardrails(search_naver_shopping, [guard])

    # Guardrail blocks display > 10
    block_res = wrapped_search.invoke({"query": "노트북", "display": 15})
    assert "가드레일 검증 실패" in block_res
    assert "display" in block_res

    wrapped_trend = wrap_tool_with_guardrails(get_shopping_trends, [guard])
    block_trend = wrapped_trend.invoke({
        "keywords": "노트북",
        "start_date": "invalid_date",
        "end_date": "2026-01-01"
    })
    assert "가드레일 검증 실패" in block_trend
    assert "YYYY-MM-DD" in block_trend
