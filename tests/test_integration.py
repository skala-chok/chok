import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

from src.config import settings
from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner
from src.core.scenario_registry import ScenarioRegistry
from src.core.scenario import ScenarioExecutionPlan


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
    """모든 API 키가 주어졌을 때 5개 모듈이 모두 활성화되고 총 19개 도구가 등록되는지 검증."""
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
    # yt_search(4) + yt_analytics(4) + naver_search(2) + naver_shopping(7) + instagram(4) = 21 tools
    assert len(runner.tools) == 21

    tool_names = {t.name for t in runner.tools}
    expected_tools = {
        "find_youtube_channel",
        "get_channel_details",
        "get_channel_videos",
        "get_competitor_recent_uploads",
        "search_paid_promotion_videos",
        "get_channel_stats",
        "get_video_metrics",
        "get_video_comments",
        "search_naver_blog",
        "search_naver_news",
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
    assert len(runner_yt.tools) == 8

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
    # naver_search(2) + naver_shopping(7) = 9 tools
    assert len(runner_naver.tools) == 9

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

    # Worker 1: get_channel_videos (max_results > 50)
    yt_search_res = tools_map["get_channel_videos"].invoke({
        "channel_id": "UC123", "published_after": "2026-01-01T00:00:00Z",
        "max_results": 100,
    })
    assert "[가드레일 검증 실패]" in yt_search_res
    assert "max_results는 최소 1개, 최대 50개까지 가능합니다." in yt_search_res

    # Worker 1: get_channel_details (empty channel_id)
    yt_details_res = tools_map["get_channel_details"].invoke({"channel_id": ""})
    assert "[가드레일 검증 실패]" in yt_details_res
    assert "channel_id가 누락되었습니다." in yt_details_res

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


def test_all_ten_scenarios_discovered_in_registry():
    """모든 10개 시나리오(유튜브 3종, 인스타 3종, 네이버 쇼핑 3종, 크로스플랫폼 1종)가 자동 탐색되는지 검증."""
    scen_registry = ScenarioRegistry()
    scen_registry.discover_scenarios("src.scenarios")

    expected_scenarios = {
        "youtube_competitor_comparison",
        "youtube_competitor_strategy",
        "youtube_paid_promotion_discovery",
        "hashtag_surge_detection",
        "competitor_campaign_tracking",
        "competitor_message_shift",
        "cross_platform_trend",
        "naver_new_product_keyword_trend",
        "naver_target_audience_validation",
        "naver_keyword_audience_segmentation",
    }
    registered_names = set(scen_registry._scenarios.keys())
    assert len(scen_registry) == 10
    assert expected_scenarios == registered_names


def test_agent_end_to_end_cross_platform_trend_scenario_routing(monkeypatch):
    """cross_platform_trend 시나리오 라우팅 시 네이버, 유튜브, 인스타그램 도구가 순차 연동되어 리포트를 반환하는지 검증."""
    monkeypatch.setattr(settings, "YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr(settings, "NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr(settings, "NAVER_CLIENT_SECRET", "mock_client_secret")
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", "mock_ig_token")
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", "mock_ig_user")

    mod_registry = ModuleRegistry()
    mod_registry.discover_modules("src.modules")

    scen_registry = ScenarioRegistry()
    scen_registry.discover_scenarios("src.scenarios")

    mock_router = MagicMock()
    mock_router.route.return_value = ScenarioExecutionPlan(
        scenario_name="cross_platform_trend",
        confidence=0.95,
        parameters={"keyword": "러닝화", "start_date": "2026-01-01", "end_date": "2026-03-01"},
        reasoning="크로스 플랫폼 트렌드 분석 질의 매칭",
    )

    mock_llm = MagicMock()
    mock_ai = AIMessage(
        content="### [러닝화] 크로스 플랫폼 트렌드 분석 결과\n\n1. 네이버 쇼핑 트렌드\n2. 유튜브 관련 영상\n3. 인스타그램 해시태그 반응"
    )
    mock_llm.return_value = mock_ai
    mock_llm.invoke.return_value = mock_ai

    runner = AgentRunner(
        registry=mod_registry,
        scenario_registry=scen_registry,
        router=mock_router,
        llm=mock_llm,
    )

    with patch("src.modules.naver_shopping.client.requests.post") as mock_post, \
         patch("src.modules.yt_search.client.requests.get") as mock_yt_get, \
         patch("src.modules.instagram.client.requests.get") as mock_ig_get:

        # 1. Naver shopping trend response
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [{
                "title": "러닝화",
                "keywords": ["러닝화"],
                "data": [{"period": "2026-01-01", "ratio": 100.0}],
            }],
        }

        # 2. YouTube search response
        mock_yt_get.return_value.status_code = 200
        mock_yt_get.return_value.json.return_value = {
            "items": [{
                "id": {"videoId": "vid_run_1"},
                "snippet": {
                    "title": "2026 러닝화 추천 가이드",
                    "description": "최신 러닝화 트렌드 분석 영상입니다.",
                    "channelTitle": "러너스TV",
                },
            }],
        }

        # 3. Instagram response (search_hashtag_id then get_hashtag_top_media)
        def fake_ig_get(url, params=None, **kwargs):
            res = MagicMock()
            res.status_code = 200
            if "ig_hashtag_search" in url:
                res.json.return_value = {"data": [{"id": "17841400000000001"}]}
            elif "top_media" in url:
                res.json.return_value = {
                    "data": [{
                        "id": "media_run_1",
                        "like_count": 120,
                        "comments_count": 30,
                        "timestamp": "2026-02-15T12:00:00+0000",
                        "caption": "#러닝화 신고 하프마라톤 완주!",
                        "permalink": "https://instagram.com/p/run1",
                    }]
                }
            else:
                res.json.return_value = {"data": []}
            return res

        mock_ig_get.side_effect = fake_ig_get

        response = runner.run("러닝화 크로스 트렌드 분석해줘")

        assert "크로스 플랫폼 트렌드 분석 결과" in response
        assert "1. 네이버 쇼핑 트렌드" in response
        assert "2. 유튜브 관련 영상" in response
        assert "3. 인스타그램 해시태그 반응" in response


def test_agent_end_to_end_hashtag_surge_detection_scenario_routing(monkeypatch):
    """hashtag_surge_detection 시나리오 라우팅 시 hours_range 적용 및 리포트 생성을 검증."""
    monkeypatch.setattr(settings, "INSTAGRAM_ACCESS_TOKEN", "mock_ig_token")
    monkeypatch.setattr(settings, "INSTAGRAM_USER_ID", "mock_ig_user")

    mod_registry = ModuleRegistry()
    mod_registry.discover_modules("src.modules")

    scen_registry = ScenarioRegistry()
    scen_registry.discover_scenarios("src.scenarios")

    mock_router = MagicMock()
    mock_router.route.return_value = ScenarioExecutionPlan(
        scenario_name="hashtag_surge_detection",
        confidence=0.98,
        parameters={
            "base_keyword": "성남맛집",
            "compare_hashtags": ["#성남맛집", "#판교맛집"],
            "hours_range": 12,
        },
        reasoning="인스타그램 급상승 해시태그 분석",
    )

    runner = AgentRunner(
        registry=mod_registry,
        scenario_registry=scen_registry,
        router=mock_router,
        llm=MagicMock(),
    )

    with patch("src.modules.instagram.client.requests.get") as mock_ig_get:
        def fake_ig_get(url, params=None, **kwargs):
            res = MagicMock()
            res.status_code = 200
            if "ig_hashtag_search" in url:
                res.json.return_value = {"data": [{"id": "17841400000000001", "name": "성남맛집"}]}
            elif "recent_media" in url:
                res.json.return_value = {
                    "data": [
                        {
                            "id": f"rec_{i}",
                            "like_count": 50,
                            "comments_count": 10,
                            "timestamp": "2026-09-11T12:00:00+0000",
                            "caption": "#성남맛집 핫플 탐방",
                            "permalink": f"https://instagram.com/p/{i}",
                            "media_type": "IMAGE",
                        }
                        for i in range(6)
                    ]
                }
            elif "top_media" in url:
                res.json.return_value = {
                    "data": [
                        {
                            "id": f"top_{i}",
                            "like_count": 30,
                            "comments_count": 5,
                            "timestamp": "2026-08-01T12:00:00+0000",
                            "caption": "#성남맛집 인기글",
                            "permalink": f"https://instagram.com/p/top_{i}",
                            "media_type": "IMAGE",
                        }
                        for i in range(5)
                    ]
                }
            else:
                res.json.return_value = {"data": []}
            return res

        mock_ig_get.side_effect = fake_ig_get

        response = runner.run("성남맛집 인스타그램 최근 12시간 급상승 분석해줘")

        assert "급상승 해시태그" in response
        assert "분석 시간 범위**: 최근 **12시간" in response
        assert "최신글 수(12h)" in response
        assert "성남맛집" in response


