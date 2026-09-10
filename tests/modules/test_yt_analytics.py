import pytest
from unittest.mock import patch, MagicMock
from src.modules.yt_analytics.module import YouTubeAnalyticsModule
from src.modules.yt_analytics.tools import get_channel_stats, get_video_comments
from src.modules.yt_analytics.guardrails import YouTubeAnalyticsGuardrail
from src.modules.yt_analytics.context import YouTubeAnalyticsContextProvider
from src.modules.yt_analytics.client import YouTubeAnalyticsClient


def test_yt_analytics_module_metadata():
    mod = YouTubeAnalyticsModule()
    assert mod.name == "yt_analytics"
    assert "채널 통계" in mod.description or "YouTube" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 2
    tool_names = [t.name for t in tools]
    assert "get_channel_stats" in tool_names
    assert "get_video_comments" in tool_names

    guardrails = mod.get_guardrails()
    assert len(guardrails) == 1
    assert isinstance(guardrails[0], YouTubeAnalyticsGuardrail)

    ctx = mod.get_context_provider()
    assert isinstance(ctx, YouTubeAnalyticsContextProvider)


def test_yt_analytics_module_is_enabled(monkeypatch):
    mod = YouTubeAnalyticsModule()

    monkeypatch.setattr("src.modules.yt_analytics.module.settings.YOUTUBE_API_KEY", "dummy_key")
    assert mod.is_enabled() is True

    monkeypatch.setattr("src.modules.yt_analytics.module.settings.YOUTUBE_API_KEY", None)
    assert mod.is_enabled() is False

    monkeypatch.setattr("src.modules.yt_analytics.module.settings.YOUTUBE_API_KEY", "")
    assert mod.is_enabled() is False


def test_yt_analytics_context_provider():
    provider = YouTubeAnalyticsContextProvider()
    snippet = provider.get_system_prompt_snippet()
    assert "get_channel_stats" in snippet
    assert "get_video_comments" in snippet
    assert provider.get_dynamic_context("some query") is None


def test_yt_analytics_guardrail_tool_args_validation():
    guard = YouTubeAnalyticsGuardrail()

    # get_video_comments: max_comments validation (1 to 50)
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 10}).passed is True
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 1}).passed is True
    assert guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 50}).passed is True

    res_too_large = guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 51})
    assert res_too_large.passed is False
    assert "50" in res_too_large.error_message

    res_too_small = guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": 0})
    assert res_too_small.passed is False
    assert "1 이상" in res_too_small.error_message

    # max_comments None check (defaults to 10 without TypeError)
    res_none = guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": None})
    assert res_none.passed is True

    # max_comments non-integer rejection
    res_invalid = guard.validate_tool_args("get_video_comments", {"video_id": "vid1", "max_comments": "abc"})
    assert res_invalid.passed is False
    assert "정수형이어야 합니다" in res_invalid.error_message

    # get_channel_stats: channel_id validation
    assert guard.validate_tool_args("get_channel_stats", {"channel_id": "UC12345"}).passed is True

    res_empty_cid = guard.validate_tool_args("get_channel_stats", {"channel_id": ""})
    assert res_empty_cid.passed is False
    assert "channel_id" in res_empty_cid.error_message

    res_missing_cid = guard.validate_tool_args("get_channel_stats", {})
    assert res_missing_cid.passed is False
    assert "channel_id" in res_missing_cid.error_message

    # Other tools pass
    assert guard.validate_tool_args("other_tool", {}).passed is True


def test_yt_analytics_guardrail_pii_masking():
    guard = YouTubeAnalyticsGuardrail()
    raw_comment = "문의사항은 test@example.com 또는 010-1234-5678로 연락주세요."
    sanitized = guard.sanitize_output("get_video_comments", raw_comment)
    assert "[EMAIL_MASKED]" in sanitized
    assert "[PHONE_MASKED]" in sanitized
    assert "test@example.com" not in sanitized
    assert "010-1234-5678" not in sanitized

    # Non-string output check
    dict_output = {"data": 123}
    assert guard.sanitize_output("get_video_comments", dict_output) == dict_output


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
    assert "50,000,000" in res or "50000000" in res
    assert "320" in res
    assert "UC12345" in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_channel_stats_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    res = get_channel_stats.invoke({"channel_id": "nonexistent_channel"})
    assert "찾을 수 없습니다" in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_channel_stats_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("API error")
    res = get_channel_stats.invoke({"channel_id": "UC12345"})
    assert "채널 통계 조회 중 오류: API error" in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_video_comments_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "authorDisplayName": "홍길동",
                            "textDisplay": "정말 유익한 영상입니다!",
                        }
                    }
                }
            },
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "authorDisplayName": "김철수",
                            "textDisplay": "설명이 깔끔하네요.",
                        }
                    }
                }
            },
        ]
    }
    res = get_video_comments.invoke({"video_id": "vid123", "max_comments": 2})
    assert "홍길동: 정말 유익한 영상입니다!" in res
    assert "김철수: 설명이 깔끔하네요." in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_video_comments_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    res = get_video_comments.invoke({"video_id": "vid_empty", "max_comments": 10})
    assert "댓글이 없거나 조회할 수 없습니다" in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_get_video_comments_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("Network error")
    res = get_video_comments.invoke({"video_id": "vid123"})
    assert "댓글 수집 실패: Network error" in res


@patch("src.modules.yt_analytics.client.requests.get")
def test_client_get_channel_info_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.yt_analytics.client.settings.YOUTUBE_API_KEY", "analytics_key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = YouTubeAnalyticsClient()
    res = client.get_channel_info("UC_test")

    mock_get.assert_called_once_with(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "statistics,snippet",
            "id": "UC_test",
            "key": "analytics_key",
        },
        timeout=5,
    )
    assert res == {"items": []}


@patch("src.modules.yt_analytics.client.requests.get")
def test_client_get_comments_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.yt_analytics.client.settings.YOUTUBE_API_KEY", "analytics_key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = YouTubeAnalyticsClient()
    res = client.get_comments("vid_test", max_comments=15)

    mock_get.assert_called_once_with(
        "https://www.googleapis.com/youtube/v3/commentThreads",
        params={
            "part": "snippet",
            "videoId": "vid_test",
            "maxResults": 15,
            "key": "analytics_key",
        },
        timeout=5,
    )
    assert res == {"items": []}


def test_yt_analytics_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("yt_analytics")
    assert mod is not None
    assert isinstance(mod, YouTubeAnalyticsModule)
