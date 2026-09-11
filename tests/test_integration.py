import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

from src.config import settings
from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner
from src.core.scenario_registry import ScenarioRegistry


class ToolCallingFakeChat(FakeMessagesListChatModel):
    """Fake chat model that supports bind_tools for tool calling testing."""
    def bind_tools(self, tools, **kwargs):
        return self


def test_full_registry_discovery():
    """모든 5개 모듈(yt_search, yt_analytics, naver_search, naver_shopping, instagram)이 자동 탐색되는지 검증."""
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")

    all_registered = [m.name for m in registry._modules.values()]
    assert "yt_search" in all_registered
    assert "yt_analytics" in all_registered
    assert "naver_search" in all_registered
    assert "naver_shopping" in all_registered
    assert "instagram" in all_registered
    assert len(registry._modules) == 5


def test_agent_runner_initialization_with_all_modules(monkeypatch):
    """모든 API 키가 주어졌을 때 5개 모듈이 모두 활성화되고 총 24개 도구가 등록되는지 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", "mock_ig_token")
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", "mock_ig_user")

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    enabled = registry.get_enabled_modules()
    assert len(enabled) == 5

    runner = AgentRunner(registry=registry, llm=MagicMock())
    # yt_search(6) + yt_analytics(4) + naver_search(2) + naver_shopping(8) + instagram(4) = 24 tools
    assert len(runner.tools) == 24

    tool_names = {t.name for t in runner.tools}
    expected_tools = {
        "search_youtube_videos",
        "get_video_transcript",
        "find_youtube_channel",
        "get_channel_videos",
        "get_competitor_recent_uploads",
        "search_paid_promotion_videos",
        "get_channel_stats",
        "get_video_metrics",
        "get_video_comments",
        "search_naver_blog",
        "search_naver_news",
        "find_naver_category_code",
        "get_shopping_trends",
        "get_shopping_category_trend",
        "get_shopping_category_gender_trend",
        "get_shopping_category_age_trend",
        "get_shopping_keyword_trend",
        "get_shopping_keyword_gender_trend",
        "get_shopping_keyword_age_trend",
        "search_hashtag_id",
        "get_hashtag_recent_media",
        "get_hashtag_top_media",
        "get_competitor_profile",
    }
    assert tool_names == expected_tools

    # System prompt snippets from all modules
    assert "YouTube 동영상 검색 및 자막 추출 가이드" in runner.system_prompt_text
    assert "YouTube 채널 통계 및 시청자 댓글 분석 가이드" in runner.system_prompt_text
    assert "네이버 블로그 및 뉴스 검색 가이드" in runner.system_prompt_text
    assert "네이버 쇼핑 데이터랩 트렌드 분석 가이드" in runner.system_prompt_text
    assert "인스타그램 Graph API 연동 모듈" in runner.system_prompt_text


def test_graceful_degradation_with_partial_keys(monkeypatch):
    """일부 API 키만 설정되었을 때 가용 모듈만 안전하게 활성화되는지 검증 (Graceful Degradation)."""
    # 1. Only YouTube API key provided
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", None)
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", None)

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    enabled = registry.get_enabled_modules()
    assert len(enabled) == 2
    assert {m.name for m in enabled} == {"yt_search", "yt_analytics"}

    runner_yt = AgentRunner(registry=registry, llm=MagicMock())
    assert len(runner_yt.tools) == 10

    # 2. Only Naver API credentials provided
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_sec")
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", None)
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", None)

    registry_naver = ModuleRegistry()
    registry_naver.discover_modules("src.modules")
    enabled_naver = registry_naver.get_enabled_modules()
    assert len(enabled_naver) == 2
    assert {m.name for m in enabled_naver} == {"naver_search", "naver_shopping"}

    runner_naver = AgentRunner(registry=registry_naver, llm=MagicMock())
    # naver_search(2) + naver_shopping(8) = 10 tools
    assert len(runner_naver.tools) == 10

    # 3. Only Instagram API credentials provided
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", "mock_token")
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", "mock_uid")

    registry_ig = ModuleRegistry()
    registry_ig.discover_modules("src.modules")
    enabled_ig = registry_ig.get_enabled_modules()
    assert len(enabled_ig) == 1
    assert {m.name for m in enabled_ig} == {"instagram"}

    runner_ig = AgentRunner(registry=registry_ig, llm=MagicMock())
    assert len(runner_ig.tools) == 4

    # 4. No API keys provided
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", None)
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", None)
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", None)
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", None)

    registry_empty = ModuleRegistry()
    registry_empty.discover_modules("src.modules")
    assert len(registry_empty.get_enabled_modules()) == 0

    runner_empty = AgentRunner(registry=registry_empty, llm=MagicMock())
    assert len(runner_empty.tools) == 0


def test_agent_runner_input_guardrail_blocking(monkeypatch):
    """모든 모듈이 활성화된 상태에서 입력 가드레일이 비정상 입력을 정상 차단하는지 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    runner = AgentRunner(registry=registry, llm=MagicMock())

    # 공백 또는 빈 문자열 입력 시 가드레일에 의해 차단
    response_empty = runner.run("")
    assert "가드레일 정책에 의해 차단되었습니다" in response_empty

    response_whitespace = runner.run("   ")
    assert "가드레일 정책에 의해 차단되었습니다" in response_whitespace


def test_tool_argument_guardrails_across_all_modules(monkeypatch):
    """등록된 도구 전체에서 도구 인자 가드레일이 유효성 검사를 올바르게 수행하는지 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", "mock_ig_token")
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", "mock_ig_user")

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    runner = AgentRunner(registry=registry, llm=MagicMock())
    tools_map = {t.name: t for t in runner.tools}

    # Worker 1: search_youtube_videos (max_results > 10)
    yt_search_res = tools_map["search_youtube_videos"].invoke({"query": "test", "max_results": 20})
    assert "[가드레일 검증 실패]" in yt_search_res
    assert "max_results는 최소 1개, 최대 10개까지 가능합니다." in yt_search_res

    # Worker 1: get_video_transcript (invalid video_id)
    yt_transcript_res = tools_map["get_video_transcript"].invoke({"video_id": "a"})
    assert "[가드레일 검증 실패]" in yt_transcript_res
    assert "유효하지 않은 YouTube video_id입니다." in yt_transcript_res

    # Worker 2: get_channel_stats (empty channel_id)
    yt_channel_res = tools_map["get_channel_stats"].invoke({"channel_id": ""})
    assert "[가드레일 검증 실패]" in yt_channel_res
    assert "channel_id가 누락되었습니다." in yt_channel_res

    # Worker 2: get_video_comments (max_comments > 50)
    yt_comments_res = tools_map["get_video_comments"].invoke({"video_id": "vid123", "max_comments": 100})
    assert "[가드레일 검증 실패]" in yt_comments_res
    assert "max_comments는 1 이상 50 이하여야 합니다." in yt_comments_res

    # Worker 3: search_naver_blog (display > 10)
    naver_blog_res = tools_map["search_naver_blog"].invoke({"query": "test", "display": 15})
    assert "[가드레일 검증 실패]" in naver_blog_res
    assert "display 파라미터는 1 이상 10 이하여야 합니다." in naver_blog_res

    # Worker 3: search_naver_news (invalid sort)
    naver_news_res = tools_map["search_naver_news"].invoke({"query": "test", "sort": "invalid"})
    assert "[가드레일 검증 실패]" in naver_news_res
    assert "sort 옵션은 'sim' 또는 'date'만 가능합니다." in naver_news_res

    # Worker 4: get_shopping_trends (invalid date format)
    naver_trend_res = tools_map["get_shopping_trends"].invoke({
        "keywords": "노트북",
        "start_date": "2026/01/01",
        "end_date": "2026/01/10"
    })
    assert "[가드레일 검증 실패]" in naver_trend_res
    assert "날짜는 YYYY-MM-DD 형식이어야 합니다." in naver_trend_res

    # Worker 5: search_hashtag_id (empty query)
    ig_res = tools_map["search_hashtag_id"].invoke({"query": "   "})
    assert "[가드레일 검증 실패]" in ig_res
    assert "검색할 해시태그 키워드가 비어 있습니다." in ig_res


def test_agent_end_to_end_naver_search_flow(monkeypatch):
    """Naver 검색 도구 호출 및 결과 정제(Sanitization)를 포함한 End-to-End 에이전트 실행 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")

    ai_tool_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "search_naver_blog",
            "args": {"query": "LangChain 튜토리얼"},
            "id": "call_integration_1",
            "type": "tool_call",
        }]
    )
    ai_final = AIMessage(content="네이버 블로그에서 최신 LangChain 튜토리얼 정보를 찾았습니다.")

    fake_llm = ToolCallingFakeChat(responses=[ai_tool_call, ai_final])

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")

    with patch("src.modules.naver_search.client.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "items": [{
                "title": "<b>LangChain</b> 기초 튜토리얼 &amp; 실습",
                "link": "https://blog.naver.com/sample/1",
                "description": "LangChain 에이전트 구축 가이드입니다.",
            }]
        }

        runner = AgentRunner(registry=registry, llm=fake_llm, scenario_registry=ScenarioRegistry())
        response = runner.run("LangChain 튜토리얼 찾아줘")

        assert response == "네이버 블로그에서 최신 LangChain 튜토리얼 정보를 찾았습니다."
        mock_get.assert_called_once()


def test_agent_end_to_end_youtube_analytics_pii_masking_flow(monkeypatch):
    """YouTube 댓글 수집 도구 호출 시 PII 마스킹 정제가 적용되는 End-to-End 에이전트 실행 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")

    ai_tool_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "get_video_comments",
            "args": {"video_id": "test_video_id", "max_comments": 5},
            "id": "call_integration_2",
            "type": "tool_call",
        }]
    )
    ai_final = AIMessage(content="댓글 분석 완료: 개인정보가 안전하게 보호되었습니다.")

    fake_llm = ToolCallingFakeChat(responses=[ai_tool_call, ai_final])

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")

    with patch("src.modules.yt_analytics.client.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "items": [{
                "snippet": {
                    "topLevelComment": {
                        "id": "comment_test",
                        "snippet": {
                            "authorDisplayName": "HongGilDong",
                            "textDisplay": "연락처는 user@example.com 또는 010-1234-5678 입니다.",
                            "likeCount": 10,
                            "publishedAt": "2026-09-10T12:00:00Z",
                        }
                    }
                }
            }]
        }

        runner = AgentRunner(registry=registry, llm=fake_llm, scenario_registry=ScenarioRegistry())
        response = runner.run("해당 영상 댓글 분석해줘")

        assert response == "댓글 분석 완료: 개인정보가 안전하게 보호되었습니다."
        mock_get.assert_called_once()
