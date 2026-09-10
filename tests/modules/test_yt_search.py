import pytest
from unittest.mock import patch, MagicMock
from src.modules.yt_search.module import YouTubeSearchModule
from src.modules.yt_search.tools import search_youtube_videos, get_video_transcript
from src.modules.yt_search.guardrails import YouTubeSearchGuardrail
from src.modules.yt_search.context import YouTubeSearchContextProvider
from src.modules.yt_search.client import YouTubeSearchClient


def test_yt_search_module_metadata():
    mod = YouTubeSearchModule()
    assert mod.name == "yt_search"
    assert "YouTube" in mod.description
    tools = mod.get_tools()
    assert len(tools) == 2
    tool_names = [t.name for t in tools]
    assert "search_youtube_videos" in tool_names
    assert "get_video_transcript" in tool_names

    guardrails = mod.get_guardrails()
    assert len(guardrails) == 1
    assert isinstance(guardrails[0], YouTubeSearchGuardrail)

    ctx = mod.get_context_provider()
    assert isinstance(ctx, YouTubeSearchContextProvider)


def test_yt_search_module_is_enabled(monkeypatch):
    mod = YouTubeSearchModule()

    monkeypatch.setattr("src.modules.yt_search.module.settings.YOUTUBE_API_KEY", "dummy_key")
    assert mod.is_enabled() is True

    monkeypatch.setattr("src.modules.yt_search.module.settings.YOUTUBE_API_KEY", None)
    assert mod.is_enabled() is False

    monkeypatch.setattr("src.modules.yt_search.module.settings.YOUTUBE_API_KEY", "")
    assert mod.is_enabled() is False


def test_yt_search_context_provider():
    provider = YouTubeSearchContextProvider()
    snippet = provider.get_system_prompt_snippet()
    assert "search_youtube_videos" in snippet
    assert "get_video_transcript" in snippet
    assert provider.get_dynamic_context("some query") is None


def test_yt_search_guardrail_input_validation():
    guard = YouTubeSearchGuardrail()

    # Empty query rejection
    res_empty = guard.validate_input("")
    assert res_empty.passed is False
    assert "검색 쿼리가 비어 있습니다" in res_empty.error_message

    res_whitespace = guard.validate_input("   ")
    assert res_whitespace.passed is False

    # Valid query
    res_valid = guard.validate_input("파이썬 튜토리얼")
    assert res_valid.passed is True


def test_yt_search_guardrail_tool_args_validation():
    guard = YouTubeSearchGuardrail()

    # max_results exceeds 10
    res = guard.validate_tool_args("search_youtube_videos", {"max_results": 20})
    assert res.passed is False
    assert "최대 10개" in res.error_message

    # max_results less than 1
    res_zero = guard.validate_tool_args("search_youtube_videos", {"max_results": 0})
    assert res_zero.passed is False
    assert "최소 1개" in res_zero.error_message

    # max_results valid
    assert guard.validate_tool_args("search_youtube_videos", {"max_results": 5}).passed is True
    assert guard.validate_tool_args("search_youtube_videos", {}).passed is True

    # video_id validation for get_video_transcript
    res_invalid_vid = guard.validate_tool_args("get_video_transcript", {"video_id": ""})
    assert res_invalid_vid.passed is False
    assert "유효하지 않은 YouTube video_id" in res_invalid_vid.error_message

    res_short_vid = guard.validate_tool_args("get_video_transcript", {"video_id": "ab"})
    assert res_short_vid.passed is False

    res_valid_vid = guard.validate_tool_args("get_video_transcript", {"video_id": "dQw4w9WgXcQ"})
    assert res_valid_vid.passed is True

    # Other tools pass
    assert guard.validate_tool_args("other_tool", {}).passed is True


def test_yt_search_guardrail_sanitize_output():
    guard = YouTubeSearchGuardrail()
    output = "Some raw output"
    assert guard.sanitize_output("search_youtube_videos", output) == output


@patch("src.modules.yt_search.client.requests.get")
def test_search_youtube_videos_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "id": {"videoId": "test_vid_1"},
                "snippet": {
                    "title": "테스트 유튜브 영상",
                    "description": "영상 설명입니다.",
                    "channelTitle": "테스트 채널"
                }
            }
        ]
    }
    result = search_youtube_videos.invoke({"query": "파이썬 강의", "max_results": 1})
    assert "test_vid_1" in result
    assert "테스트 유튜브 영상" in result
    assert "테스트 채널" in result
    assert "영상 설명입니다." in result


@patch("src.modules.yt_search.client.requests.get")
def test_search_youtube_videos_no_items(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"items": []}
    result = search_youtube_videos.invoke({"query": "결과없는검색어", "max_results": 5})
    assert "유튜브 검색 결과가 없습니다" in result


@patch("src.modules.yt_search.client.requests.get")
def test_search_youtube_videos_error_handling(mock_get):
    mock_get.side_effect = RuntimeError("Network failure")
    result = search_youtube_videos.invoke({"query": "파이썬 강의", "max_results": 1})
    assert "유튜브 검색 중 오류 발생: Network failure" in result


def test_get_video_transcript_mock():
    result = get_video_transcript.invoke({"video_id": "test_vid_123"})
    assert "test_vid_123" in result
    assert "자막 추출 완료" in result


def test_get_video_transcript_error_handling():
    with patch("src.modules.yt_search.tools.client.get_transcript", side_effect=Exception("Transcript unavailable")):
        result = get_video_transcript.invoke({"video_id": "invalid_id"})
        assert "자막 추출 실패: Transcript unavailable" in result


@patch("src.modules.yt_search.client.requests.get")
def test_client_search_videos_params(mock_get, monkeypatch):
    monkeypatch.setattr("src.modules.yt_search.client.settings.YOUTUBE_API_KEY", "my_api_key")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_get.return_value = mock_resp

    client = YouTubeSearchClient()
    res = client.search_videos("테스트", max_results=3)

    mock_get.assert_called_once_with(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "q": "테스트",
            "type": "video",
            "maxResults": 3,
            "key": "my_api_key",
        },
        timeout=5,
    )
    assert res == {"items": []}


def test_yt_search_registry_discovery():
    from src.core.registry import ModuleRegistry
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    mod = registry.get_module("yt_search")
    assert mod is not None
    assert isinstance(mod, YouTubeSearchModule)

