# ==============================================================================
# 🟣 [Step 6 - 보라점] 단위 테스트 & 품질 검증 계층
# • 역할: 외부 API를 100% Mocking하여 네트워크 연결이나 API 키 없이도 1초 내에 통과하는 단위 테스트를 작성합니다.
# • 검증 항목: 모듈 메타데이터, 도구 정상/예외 응답, 가드레일 통과/차단/정제, 컨텍스트 스니펫
# • 실행 명령: pytest tests/modules/test_naver_search.py -v
# ==============================================================================

import pytest
import requests
from unittest.mock import patch, MagicMock
from src.modules.naver_search.module import NaverSearchModule
from src.modules.naver_search.tools import search_naver_blog, search_naver_news
from src.modules.naver_search.guardrails import NaverSearchGuardrail
from src.modules.naver_search.context import NaverSearchContextProvider
from src.modules.naver_search.client import NaverSearchClient


def test_naver_search_module_metadata():
    mod = NaverSearchModule()
    assert mod.name == "naver_search"
    assert "네이버" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 2
    tool_names = [t.name for t in tools]
    assert "search_naver_blog" in tool_names
    assert "search_naver_news" in tool_names

    guardrails = mod.get_guardrails()
    assert len(guardrails) == 1
    assert isinstance(guardrails[0], NaverSearchGuardrail)

    ctx = mod.get_context_provider()
    assert isinstance(ctx, NaverSearchContextProvider)


def test_naver_search_module_is_enabled(monkeypatch):
    mod = NaverSearchModule()

    # Both set
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_ID", "dummy_id")
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_SECRET", "dummy_secret")
    assert mod.is_enabled() is True

    # Only ID set
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_ID", "dummy_id")
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_SECRET", None)
    assert mod.is_enabled() is False

    # Only Secret set
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_ID", None)
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_SECRET", "dummy_secret")
    assert mod.is_enabled() is False

    # Neither set
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_ID", None)
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_SECRET", None)
    assert mod.is_enabled() is False

    # Empty strings
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_ID", "")
    monkeypatch.setattr("src.modules.naver_search.module.settings.NAVER_CLIENT_SECRET", "")
    assert mod.is_enabled() is False


def test_naver_search_context_provider():
    provider = NaverSearchContextProvider()
    snippet = provider.get_system_prompt_snippet()
    assert "search_naver_news" in snippet
    assert "search_naver_blog" in snippet
    assert provider.get_dynamic_context("some query") is None


def test_naver_search_guardrail_input_validation():
    guard = NaverSearchGuardrail()

    # Empty query rejection
    res_empty = guard.validate_input("")
    assert res_empty.passed is False
    assert "검색 쿼리가 비어 있습니다" in res_empty.error_message

    res_whitespace = guard.validate_input("   ")
    assert res_whitespace.passed is False

    # Valid query
    res_valid = guard.validate_input("인공지능 트렌드")
    assert res_valid.passed is True


def test_naver_search_guardrail_tool_args_validation():
    guard = NaverSearchGuardrail()

    for tool_name in ["search_naver_blog", "search_naver_news"]:
        # display validation (1 to 10)
        assert guard.validate_tool_args(tool_name, {"query": "test", "display": 5}).passed is True
        assert guard.validate_tool_args(tool_name, {"query": "test", "display": 1}).passed is True
        assert guard.validate_tool_args(tool_name, {"query": "test", "display": 10}).passed is True
        assert guard.validate_tool_args(tool_name, {"query": "test"}).passed is True

        res_too_large = guard.validate_tool_args(tool_name, {"query": "test", "display": 11})
        assert res_too_large.passed is False
        assert "display" in res_too_large.error_message

        res_too_small = guard.validate_tool_args(tool_name, {"query": "test", "display": 0})
        assert res_too_small.passed is False
        assert "display" in res_too_small.error_message

        # sort validation ('sim' or 'date')
        assert guard.validate_tool_args(tool_name, {"query": "test", "sort": "sim"}).passed is True
        assert guard.validate_tool_args(tool_name, {"query": "test", "sort": "date"}).passed is True

        res_invalid_sort = guard.validate_tool_args(tool_name, {"query": "test", "sort": "invalid"})
        assert res_invalid_sort.passed is False
        assert "sort" in res_invalid_sort.error_message

    # Other tools should pass
    assert guard.validate_tool_args("other_tool", {"display": 100}).passed is True


def test_naver_search_html_sanitization():
    guard = NaverSearchGuardrail()
    raw = "기사 제목 <b>AI 신기술</b> 발표 &quot;대박&quot; &amp; 성공"
    cleaned = guard.sanitize_output("search_naver_news", raw)
    assert "<b>" not in cleaned
    assert "</b>" not in cleaned
    assert "&quot;" not in cleaned
    assert "&amp;" not in cleaned
    assert cleaned == '기사 제목 AI 신기술 발표 "대박" & 성공'

    # Non-string output
    dict_output = {"data": "test"}
    assert guard.sanitize_output("search_naver_news", dict_output) == dict_output


def test_naver_search_pii_masking():
    """handoff/03_guidelines.md 2절 - 사후 출력 정제 시 이메일/전화번호 마스킹 검증."""
    guard = NaverSearchGuardrail()

    raw_email = "문의사항은 contact@example.com 으로 보내주세요."
    cleaned_email = guard.sanitize_output("search_naver_blog", raw_email)
    assert "contact@example.com" not in cleaned_email
    assert "[EMAIL_MASKED]" in cleaned_email

    raw_phone = "사장님 연락처는 010-1234-5678 입니다."
    cleaned_phone = guard.sanitize_output("search_naver_news", raw_phone)
    assert "010-1234-5678" not in cleaned_phone
    assert "[PHONE_MASKED]" in cleaned_phone

    raw_both = "<b>맛집</b> 문의: owner@shop.com / 010-9999-8888"
    cleaned_both = guard.sanitize_output("search_naver_blog", raw_both)
    assert "<b>" not in cleaned_both
    assert "[EMAIL_MASKED]" in cleaned_both
    assert "[PHONE_MASKED]" in cleaned_both


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_blog_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "테스트 <b>블로그</b> 포스팅",
                "link": "https://blog.naver.com/test/1",
                "description": "블로그 포스팅 내용 요약"
            }
        ]
    }
    res = search_naver_blog.invoke({"query": "블로그 맛집", "display": 1})
    assert "테스트 <b>블로그</b> 포스팅" in res
    assert "https://blog.naver.com/test/1" in res
    assert "블로그 포스팅 내용 요약" in res


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_blog_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    res = search_naver_blog.invoke({"query": "결과없는검색어", "display": 5})
    assert "네이버 블로그 검색 결과가 없습니다" in res


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_blog_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("Connection timeout")
    res = search_naver_blog.invoke({"query": "맛집", "display": 1})
    assert "네이버 블로그 검색 실패: Connection timeout" in res


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_news_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "테스트 <b>인공지능</b> 뉴스",
                "originallink": "https://example.com/1",
                "link": "https://news.naver.com/1",
                "description": "인공지능의 최신 동향"
            }
        ]
    }
    res = search_naver_news.invoke({"query": "인공지능", "display": 1})
    assert "테스트 <b>인공지능</b> 뉴스" in res
    assert "https://news.naver.com/1" in res
    assert "인공지능의 최신 동향" in res


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_news_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    res = search_naver_news.invoke({"query": "결과없는검색어", "display": 5})
    assert "네이버 뉴스 검색 결과가 없습니다" in res


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_news_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("API server error")
    res = search_naver_news.invoke({"query": "인공지능", "display": 1})
    assert "네이버 뉴스 검색 실패: API server error" in res


@patch("src.modules.naver_search.client.requests.get")
def test_client_search_blog_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.naver_search.client.settings.NAVER_CLIENT_ID", "test_id")
    monkeypatch.setattr("src.modules.naver_search.client.settings.NAVER_CLIENT_SECRET", "test_secret")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = NaverSearchClient()
    res = client.search_blog("맛집", display=3, sort="date")

    mock_get.assert_called_once_with(
        "https://naverapihub.apigw.ntruss.com/search/v1/blog",
        headers={
            "X-NCP-APIGW-API-KEY-ID": "test_id",
            "X-NCP-APIGW-API-KEY": "test_secret",
        },
        params={"query": "맛집", "display": 3, "sort": "date"},
        timeout=5,
    )
    assert res == {"items": []}


@patch("src.modules.naver_search.client.requests.get")
def test_client_search_news_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.naver_search.client.settings.NAVER_CLIENT_ID", "test_id")
    monkeypatch.setattr("src.modules.naver_search.client.settings.NAVER_CLIENT_SECRET", "test_secret")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = NaverSearchClient()
    res = client.search_news("속보", display=4, sort="sim")

    mock_get.assert_called_once_with(
        "https://naverapihub.apigw.ntruss.com/search/v1/news",
        headers={
            "X-NCP-APIGW-API-KEY-ID": "test_id",
            "X-NCP-APIGW-API-KEY": "test_secret",
        },
        params={"query": "속보", "display": 4, "sort": "sim"},
        timeout=5,
    )
    assert res == {"items": []}


@patch("src.modules.naver_search.client.requests.get")
def test_client_search_blog_openapi_failure_fallback(mock_get):
    """handoff/04_testing_harness.md 3.3 - OpenAPI 통신 장애 시 client가 폴백 목 데이터를 반환하는지 검증."""
    mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")

    client = NaverSearchClient()
    result = client.search_blog("AI 트렌드")

    assert "items" in result
    assert len(result["items"]) >= 1
    assert "[Fallback Mock]" in result["items"][0]["title"]


@patch("src.modules.naver_search.client.requests.get")
def test_client_search_news_openapi_failure_fallback(mock_get):
    """handoff/04_testing_harness.md 3.3 - OpenAPI 통신 장애 시 client가 폴백 목 데이터를 반환하는지 검증."""
    mock_get.side_effect = requests.exceptions.Timeout("Read timed out")

    client = NaverSearchClient()
    result = client.search_news("AI 트렌드")

    assert "items" in result
    assert len(result["items"]) >= 1
    assert "[Fallback Mock]" in result["items"][0]["title"]


@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_blog_openapi_failure_fallback_via_tool(mock_get):
    """폴백 목 데이터가 Tool 계층까지 정상적으로 전파되는지 검증 (크래시 없이 응답)."""
    mock_get.side_effect = requests.exceptions.ConnectionError("Network unreachable")
    res = search_naver_blog.invoke({"query": "AI 트렌드", "display": 1})
    assert "[Fallback Mock]" in res


def test_naver_search_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("naver_search")
    assert mod is not None
    assert isinstance(mod, NaverSearchModule)
