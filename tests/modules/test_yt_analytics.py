# ==============================================================================
# 🟣 YouTube Analytics 모듈 단위 테스트 (test_yt_analytics)
# • 채널 통계, 동영상 메트릭, 시청자 댓글, 유료 프로모션 검색 Mocking 검증
# • 외부 API 100% Mocking 격리 (네트워크 0, 비용 0, 1초 내 실행)
# ==============================================================================

from datetime import datetime, timezone
import pytest
import requests
from unittest.mock import patch, MagicMock, Mock

from src.modules.yt_analytics.module import YouTubeAnalyticsModule, YouTubeAnalyticsContextProvider
from src.modules.yt_analytics.tools import (
    get_channel_stats,
    get_video_comments,
    get_video_metrics,
    search_paid_promotion_videos,
)
from src.modules.yt_analytics.guardrails import YouTubeAnalyticsGuardrail
from src.modules.yt_analytics.client import YouTubeAnalyticsClient, ERROR_MESSAGES


NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def youtube_key(monkeypatch):
    monkeypatch.setattr("src.modules.yt_analytics.client.settings.YOUTUBE_API_KEY", "dummy_key")


# ------------------------------------------------------------------------------
# 1. 모듈 메타데이터 & 활성화 검증
# ------------------------------------------------------------------------------
def test_yt_analytics_module_metadata():
    mod = YouTubeAnalyticsModule()
    assert mod.name == "yt_analytics"
    assert "채널 통계" in mod.description or "YouTube" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 4
    tool_names = {t.name for t in tools}
    assert {"get_channel_stats", "get_video_comments", "get_video_metrics", "search_paid_promotion_videos"} <= tool_names

    guardrails = mod.get_guardrails()
    assert len(guardrails) == 1
    assert isinstance(guardrails[0], YouTubeAnalyticsGuardrail)

    ctx = mod.get_context_provider()
    assert isinstance(ctx, YouTubeAnalyticsContextProvider)


@pytest.mark.parametrize(
    "api_key,expected",
    [
        ("dummy_key", True),
        (None, False),
        ("", False),
    ],
)
def test_yt_analytics_module_is_enabled(monkeypatch, api_key, expected):
    monkeypatch.setattr("src.modules.yt_analytics.module.settings.YOUTUBE_API_KEY", api_key)
    assert YouTubeAnalyticsModule().is_enabled() is expected


def test_yt_analytics_context_provider():
    provider = YouTubeAnalyticsContextProvider()
    snippet = provider.get_system_prompt_snippet()
    assert "get_channel_stats" in snippet
    assert "get_video_comments" in snippet
    assert provider.get_dynamic_context("some query") is None


# ------------------------------------------------------------------------------
# 2. 가드레일 인자 검증 & PII 마스킹
# ------------------------------------------------------------------------------
def test_yt_analytics_guardrail_tool_args_validation():
    guard = YouTubeAnalyticsGuardrail()

    # get_video_comments: max_comments (1~50, None 기본값)
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 10}).passed
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 1}).passed
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 50}).passed
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": None}).passed

    assert not guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 51}).passed
    assert not guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 0}).passed
    assert not guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": "abc"}).passed

    # get_channel_stats: channel_id 필수
    assert guard.validate_tool_args("get_channel_stats", {"channel_id": "UC12345"}).passed
    assert not guard.validate_tool_args("get_channel_stats", {"channel_id": ""}).passed
    assert not guard.validate_tool_args("get_channel_stats", {}).passed
    assert guard.validate_tool_args("other_tool", {}).passed


def test_yt_analytics_guardrail_pii_masking():
    guard = YouTubeAnalyticsGuardrail()
    raw_comment = "문의: test@example.com 또는 010-1234-5678"
    sanitized = guard.sanitize_output("get_video_comments", raw_comment)
    assert "[EMAIL_MASKED]" in sanitized and "[PHONE_MASKED]" in sanitized
    assert "test@example.com" not in sanitized and "010-1234-5678" not in sanitized

    # 구조화 딕셔너리 출력 내 댓글 PII 마스킹 및 URL 보존
    structured = {
        "comments": [{"text": "문의: user@example.com 010-1234-5678"}],
        "url": "https://example.com/01012345678",
    }
    sanitized_dict = guard.sanitize_output("get_video_comments", structured)
    assert sanitized_dict["comments"][0]["text"] == "문의: [EMAIL_MASKED] [PHONE_MASKED]"
    assert sanitized_dict["url"] == "https://example.com/01012345678"


# ------------------------------------------------------------------------------
# 3. 도구 기능 검증 (Channel Stats, Metrics, Comments, Paid Promotion)
# ------------------------------------------------------------------------------
@patch("src.modules.yt_analytics.client.requests.get")
def test_get_channel_stats_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "statistics": {
                    "subscriberCount": "100000",
                    "viewCount": "50000000",
                    "videoCount": "320",
                }
            }
        ]
    }
    res = get_channel_stats.invoke({"channel_id": "UC12345"})
    assert "100,000" in res or "100000" in res
    assert "UC12345" in res

    # 빈 결과 및 에러 처리
    mock_get.return_value.json.return_value = {"items": []}
    assert "찾을 수 없습니다" in get_channel_stats.invoke({"channel_id": "nonexistent"})

    mock_get.side_effect = RuntimeError("API error")
    assert "오류: API error" in get_channel_stats.invoke({"channel_id": "UC12345"})


@patch("src.modules.yt_analytics.client.requests.get")
def test_search_paid_promotion_videos(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "id": {"videoId": "v_promo"},
                "snippet": {
                    "title": "무선이어폰 협찬 리뷰",
                    "description": "유료 프로모션 포함",
                    "channelId": "ch1",
                    "channelTitle": "테크채널",
                    "publishedAt": "2026-09-01T12:00:00Z",
                    "thumbnails": {"high": {"url": "https://img.youtube.com/thumb.jpg"}},
                },
            }
        ]
    }
    rows = search_paid_promotion_videos.invoke({"keyword": "무선이어폰", "max_results": 10})
    assert len(rows) == 1
    assert rows[0]["video_id"] == "v_promo"
    assert rows[0]["url"] == "https://www.youtube.com/watch?v=v_promo"
    assert mock_get.call_args.kwargs["params"]["videoPaidProductPlacement"] == "true"

    # 잘못된 날짜 형식 차단
    invalid_date_res = search_paid_promotion_videos.invoke({"keyword": "k", "published_after": "invalid-date"})
    assert invalid_date_res["error_code"] == "invalidArgument"


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_video_metrics_calculation_and_chunking(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "id": "v1",
                "snippet": {"title": "신제품 리뷰", "publishedAt": "2026-09-01T12:00:00Z"},
                "statistics": {"viewCount": "1000", "likeCount": "40", "commentCount": "10"},
                "contentDetails": {"duration": "PT2M"},
            }
        ]
    }
    with patch("src.modules.yt_analytics.tools.datetime") as mock_dt:
        mock_dt.now.return_value = NOW
        metrics = get_video_metrics.invoke({"video_ids": ["v1"]})
    assert len(metrics) == 1
    assert metrics[0]["video_id"] == "v1"
    assert metrics[0]["engagement_rate"] == 5.0
    assert metrics[0]["daily_views"] == 100.0

    # 빈 video_ids 인자
    assert get_video_metrics.invoke({"video_ids": []}) == []

    # 50개 초과 배치 분할 요청 검증 (51개 전달 시 2회 호출)
    ids_51 = [f"vid_{i}" for i in range(51)]
    mock_get.return_value.json.side_effect = [
        {"items": [{"id": f"vid_{i}", "snippet": {"title": "T", "publishedAt": "2026-09-01T00:00:00Z"}, "statistics": {}, "contentDetails": {"duration": "PT1M"}} for i in range(50)]},
        {"items": [{"id": "vid_50", "snippet": {"title": "T", "publishedAt": "2026-09-01T00:00:00Z"}, "statistics": {}, "contentDetails": {"duration": "PT1M"}}]},
    ]
    with patch("src.modules.yt_analytics.tools.datetime") as mock_dt:
        mock_dt.now.return_value = NOW
        batch_res = get_video_metrics.invoke({"video_ids": ids_51})
    assert len(batch_res) == 51
    assert mock_get.call_count >= 2


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_video_comments_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "snippet": {
                    "totalReplyCount": 2,
                    "topLevelComment": {
                        "id": "c1",
                        "snippet": {
                            "authorDisplayName": "작성자A",
                            "textDisplay": "영상 유익하네요!",
                            "likeCount": 5,
                            "publishedAt": "2026-09-01T12:00:00Z",
                            "updatedAt": "2026-09-01T12:00:00Z",
                        },
                    },
                }
            }
        ]
    }
    res = get_video_comments.invoke({"video_id": "vid123", "max_comments": 5, "order": "relevance"})
    assert res["comment_count_returned"] == 1
    assert res["comments"][0]["author"] == "작성자A"
    assert res["comments"][0]["text"] == "영상 유익하네요!"

    # 잘못된 정렬 방식 차단
    assert get_video_comments.invoke({"video_id": "vid123", "order": "invalid"})["error_code"] == "invalidOrder"

    # 빈 결과
    mock_get.return_value.json.return_value = {"items": []}
    empty_res = get_video_comments.invoke({"video_id": "vid_empty"})
    assert empty_res["comments"] == []
    assert "error" not in empty_res


# ------------------------------------------------------------------------------
# 4. 외부 에러 매핑 및 레지스트리 탐색
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "error,expected_code",
    [
        (requests.exceptions.ConnectionError("offline"), "networkError"),
        (requests.exceptions.Timeout("timed out"), "networkError"),
        (requests.exceptions.JSONDecodeError("err", "", 0), "invalidResponse"),
    ],
)
@patch("src.modules.yt_analytics.client.requests.get")
def test_yt_analytics_error_handling_mapping(mock_get, error, expected_code):
    mock_get.side_effect = error
    res = get_video_comments.invoke({"video_id": "vid123"})
    assert res["error_code"] == expected_code


def test_yt_analytics_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("yt_analytics")
    assert mod is not None
    assert isinstance(mod, YouTubeAnalyticsModule)

