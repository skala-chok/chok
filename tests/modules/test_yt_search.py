from unittest.mock import MagicMock, patch

import requests

from src.modules.yt_search.client import YouTubeSearchClient
from src.modules.yt_search.guardrails import YouTubeSearchGuardrail
from src.modules.yt_search.module import YouTubeSearchModule
from src.modules.yt_search.tools import _video_items


def test_module_registers_only_requested_tools():
    module = YouTubeSearchModule()
    assert [tool.name for tool in module.get_tools()] == [
        "find_youtube_channel",
        "get_channel_details",
        "get_channel_videos",
        "get_competitor_recent_uploads",
    ]


def test_guardrail_validates_channel_and_date_arguments():
    guardrail = YouTubeSearchGuardrail()
    assert not guardrail.validate_tool_args("get_channel_details", {}).passed
    assert not guardrail.validate_tool_args(
        "get_channel_videos", {"channel_id": "UC1", "published_after": "bad"}
    ).passed
    assert guardrail.validate_tool_args(
        "get_channel_videos", {"channel_id": "UC1", "published_after": "2026-01-01T00:00:00Z"}
    ).passed


@patch("src.modules.yt_search.client.requests.get")
def test_client_search_failure_returns_channel_contract_fallback(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("offline")
    result = YouTubeSearchClient().find_channels("A사")
    assert result["items"][0]["id"]["channelId"] == "fallback_channel"
    assert "[Fallback Mock]" in result["items"][0]["snippet"]["title"]


@patch("src.modules.yt_search.client.requests.get")
def test_recent_upload_failure_returns_playlist_contract_fallback(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout("offline")
    result = YouTubeSearchClient().get_recent_uploads("UC1")
    assert result["items"][0]["contentDetails"]["videoId"] == "fallback_video"
    assert "[Fallback Mock]" in result["items"][0]["snippet"]["title"]


@patch("src.modules.yt_search.client.requests.get")
def test_channel_details_uses_mocked_http(mock_get):
    response = MagicMock()
    response.json.return_value = {"items": []}
    mock_get.return_value = response
    assert YouTubeSearchClient().get_channel_details("UC1") == {"items": []}


def test_video_normalizer_ignores_malformed_items():
    assert _video_items({"items": ["bad", {"contentDetails": {"videoId": "v1"}}]}) == [
        {
            "video_id": "v1", "title": "", "description": "", "channel_name": "",
            "published_at": "", "url": "https://www.youtube.com/watch?v=v1",
        }
    ]


def test_video_normalizer_accepts_playlist_item_string_id():
    assert _video_items({"items": [{"id": "playlist-item", "contentDetails": {"videoId": "v1"}}]})[0]["video_id"] == "v1"


@patch("src.modules.yt_search.client.requests.get")
def test_client_expands_date_only_published_after(mock_get):
    response = MagicMock()
    response.json.return_value = {"items": []}
    mock_get.return_value = response
    YouTubeSearchClient().search_videos("러닝화", channel_id="UC1", published_after="2026-01-01")
    assert mock_get.call_args.kwargs["params"]["publishedAfter"] == "2026-01-01T00:00:00Z"
