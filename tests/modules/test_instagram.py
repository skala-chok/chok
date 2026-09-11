# ==============================================================================
# 🟣 [Step 6 - 보라점] Instagram 모듈 단위 테스트 & 하네스 검증
# • 외부 API 100% Mocking (비용 제로, 인터넷 통신 제로, 1초 내 실행)
# • [Rule 1-1] OpenAPI 통신 장애 시 [Fallback Mock] 데이터 반환 검증
# ==============================================================================

import pytest
import requests
from unittest.mock import patch, MagicMock
from src.modules.instagram.module import InstagramModule
from src.modules.instagram.tools import (
    search_hashtag_id,
    get_hashtag_recent_media,
    get_hashtag_top_media,
    get_competitor_profile,
)
from src.modules.instagram.guardrails import InstagramGuardrail
from src.modules.instagram.context import InstagramContextProvider
from src.modules.instagram.client import InstagramApiClient


class TestInstagramModuleMetadata:
    def test_module_metadata(self):
        mod = InstagramModule()
        assert mod.name == "instagram"
        assert "인스타그램" in mod.description
        tools = mod.get_tools()
        assert len(tools) == 4
        tool_names = [t.name for t in tools]
        assert "search_hashtag_id" in tool_names
        assert "get_hashtag_recent_media" in tool_names
        assert "get_hashtag_top_media" in tool_names
        assert "get_competitor_profile" in tool_names

        guardrails = mod.get_guardrails()
        assert len(guardrails) == 1
        assert isinstance(guardrails[0], InstagramGuardrail)

        ctx = mod.get_context_provider()
        assert isinstance(ctx, InstagramContextProvider)
        assert "search_hashtag_id" in ctx.get_system_prompt_snippet()

    def test_module_is_enabled(self, monkeypatch):
        mod = InstagramModule()

        # Both set
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_ACCESS_TOKEN", "token_123")
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_USER_ID", "user_123")
        assert mod.is_enabled() is True

        # Only token set
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_ACCESS_TOKEN", "token_123")
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_USER_ID", None)
        assert mod.is_enabled() is False

        # Neither set
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_ACCESS_TOKEN", None)
        monkeypatch.setattr("src.modules.instagram.module.settings.INSTAGRAM_USER_ID", None)
        assert mod.is_enabled() is False


class TestInstagramClientMock:
    """정상 Mock 응답 및 파라미터 규격 검증."""

    @patch("requests.get")
    def test_search_hashtag_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"id": "17843857450077043", "name": "성남맛집"}]
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_tok", user_id="178414000", api_version="v21.0")
        res = client.search_hashtag("성남맛집")

        assert res["data"][0]["id"] == "17843857450077043"
        mock_get.assert_called_once()
        assert mock_get.call_args[1]["params"]["q"] == "성남맛집"

    @patch("requests.get")
    def test_get_hashtag_top_media_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "m_top_1",
                    "caption": "인기 게시물 #성남맛집",
                    "like_count": 300,
                    "comments_count": 25,
                    "media_type": "IMAGE",
                    "permalink": "https://insta.com/p/1",
                    "timestamp": "2026-09-01T12:00:00+0000",
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_tok", user_id="178414000", api_version="v21.0")
        res = client.get_hashtag_top_media("17843857450077043")

        assert len(res["data"]) == 1
        assert res["data"][0]["like_count"] == 300

    @patch("requests.get")
    def test_get_business_discovery_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "business_discovery": {
                "username": "nike",
                "name": "Nike Official",
                "biography": "Just Do It",
                "website": "https://nike.com",
                "followers_count": 100000,
                "follows_count": 50,
                "media_count": 500,
                "media": {
                    "data": [
                        {
                            "id": "nike_m1",
                            "caption": "New drop #nike",
                            "like_count": 5000,
                            "comments_count": 120,
                            "timestamp": "2026-09-10T10:00:00+0000",
                            "permalink": "https://insta.com/p/nike1",
                        }
                    ]
                },
            }
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_tok", user_id="178414000", api_version="v21.0")
        res = client.get_business_discovery("nike")

        assert res["business_discovery"]["username"] == "nike"
        assert res["business_discovery"]["followers_count"] == 100000


class TestInstagramOpenApiFallbackHarness:
    """🚨 [Rule 1-1] OpenAPI 장애 시 [Fallback Mock] 반환 필수 검증 하네스 테스트."""

    @patch("requests.get")
    def test_search_hashtag_fallback_on_network_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection timeout")

        client = InstagramApiClient()
        res = client.search_hashtag("성남맛집")

        assert "_fallback" in res
        assert res["_fallback"] is True
        assert len(res["data"]) >= 1
        assert "fallback_ht_성남맛집" in res["data"][0]["id"]
        assert "[Fallback Mock]" in res["_fallback_notice"]

    @patch("requests.get")
    def test_get_hashtag_top_media_fallback_on_500(self, mock_get):
        mock_get.side_effect = requests.exceptions.HTTPError("500 Internal Server Error")

        client = InstagramApiClient()
        res = client.get_hashtag_top_media("ht_12345")

        assert res["_fallback"] is True
        assert len(res["data"]) >= 1
        assert "[Fallback Mock]" in res["data"][0]["caption"]

    @patch("requests.get")
    def test_get_hashtag_recent_media_fallback_on_timeout(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Read timeout")

        client = InstagramApiClient()
        res = client.get_hashtag_recent_media("ht_12345")

        assert res["_fallback"] is True
        assert len(res["data"]) >= 1
        assert "[Fallback Mock]" in res["data"][0]["caption"]

    @patch("requests.get")
    def test_get_business_discovery_fallback_on_quota_exceeded(self, mock_get):
        mock_get.side_effect = requests.exceptions.RequestException("Rate limit exceeded")

        client = InstagramApiClient()
        res = client.get_business_discovery("재슐랭가이드")

        assert res["_fallback"] is True
        bd = res["business_discovery"]
        assert bd["username"] == "재슐랭가이드"
        assert "[Fallback Mock]" in bd["biography"]
        assert len(bd["media"]["data"]) >= 1
        assert "[Fallback Mock]" in bd["media"]["data"][0]["caption"]


class TestInstagramGuardrails:
    def test_validate_search_hashtag_id(self):
        gr = InstagramGuardrail()
        # Non-empty valid
        assert gr.validate_tool_args("search_hashtag_id", {"query": "성남맛집"}).passed is True
        assert gr.validate_tool_args("search_hashtag_id", {"query": "#성남 맛집"}).passed is True

        # Empty / whitespace only
        assert gr.validate_tool_args("search_hashtag_id", {"query": ""}).passed is False
        assert gr.validate_tool_args("search_hashtag_id", {"query": "   "}).passed is False
        assert gr.validate_tool_args("search_hashtag_id", {"query": "#"}).passed is False

    def test_validate_media_queries(self):
        gr = InstagramGuardrail()
        assert gr.validate_tool_args("get_hashtag_recent_media", {"hashtag_id": "12345"}).passed is True
        assert gr.validate_tool_args("get_hashtag_recent_media", {"hashtag_id": ""}).passed is False
        assert gr.validate_tool_args("get_hashtag_top_media", {"hashtag_id": "12345"}).passed is True
        assert gr.validate_tool_args("get_hashtag_top_media", {"hashtag_id": ""}).passed is False

    def test_validate_competitor_profile(self):
        gr = InstagramGuardrail()
        assert gr.validate_tool_args("get_competitor_profile", {"username": "nike"}).passed is True
        assert gr.validate_tool_args("get_competitor_profile", {"username": "@nike"}).passed is True
        assert gr.validate_tool_args("get_competitor_profile", {"username": ""}).passed is False
        assert gr.validate_tool_args("get_competitor_profile", {"username": "nike official"}).passed is False

    def test_sanitize_output(self):
        gr = InstagramGuardrail()
        raw = "Error calling https://graph.facebook.com?access_token=EAAG123456789abc with token EAAGsecret"
        sanitized = gr.sanitize_output("search_hashtag_id", raw)
        assert "EAAG123456789abc" not in sanitized
        assert "[PROTECTED_TOKEN]" in sanitized


class TestInstagramTools:
    @patch.object(InstagramApiClient, "search_hashtag")
    def test_search_hashtag_id_tool_normalization(self, mock_search):
        mock_search.return_value = {"data": [{"id": "ht_999", "name": "성남맛집"}]}

        res = search_hashtag_id.invoke({"query": "#성남 맛집"})
        # 통과 기준: 공백과 # 제거 정규화 결과를 사용자에게 명시
        assert "[정규화 안내]" in res
        assert "q=성남맛집" in res
        assert "ht_999" in res
        assert "쿼터" in res

    @patch.object(InstagramApiClient, "get_hashtag_recent_media")
    def test_get_hashtag_recent_media_tool_disclaimers(self, mock_recent):
        mock_recent.return_value = {
            "data": [
                {
                    "id": "m1",
                    "caption": "신규 오픈 #성남맛집",
                    "like_count": 20,
                    "comments_count": 3,
                    "media_type": "IMAGE",
                    "permalink": "https://insta.com/p/m1",
                    "timestamp": "2026-09-11T09:00:00+0000",
                }
            ]
        }

        res = get_hashtag_recent_media.invoke({"hashtag_id": "ht_999"})
        assert "최근 24시간" in res
        assert "시계열 추이" in res
        assert "작성자 정보" in res

    @patch.object(InstagramApiClient, "get_business_discovery")
    def test_get_competitor_profile_tool_view_count_disclaimer(self, mock_bd):
        mock_bd.return_value = {
            "business_discovery": {
                "username": "nike",
                "name": "Nike",
                "biography": "Official",
                "website": "https://nike.com",
                "followers_count": 50000,
                "follows_count": 100,
                "media_count": 200,
                "media": {"data": []},
            }
        }

        res = get_competitor_profile.invoke({"username": "@nike"})
        # 통과 기준: 조회수는 제공되지 않는 지표임을 명시
        assert "조회수" in res
        assert "참여율" in res
