"""B의 기존 로컬 요구사항과 이관 회귀 검증. 외부 API는 모두 mock한다."""

import copy
import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
import requests

from src.core.guardrails import wrap_tool_with_guardrails
from src.modules.yt_analytics import tools
from src.modules.yt_analytics.client import ERROR_MESSAGES
from src.modules.yt_analytics.guardrails import YouTubeAnalyticsGuardrail

NOW = datetime(2026, 9, 11, 12, tzinfo=timezone.utc)
SECRET = "EXTERNAL_RESPONSE_SENTINEL"


@pytest.fixture(autouse=True)
def youtube_key(monkeypatch):
    monkeypatch.setattr("src.modules.yt_analytics.client.settings.YOUTUBE_API_KEY", "test-only-key")


@pytest.fixture
def http_get():
    with patch("src.modules.yt_analytics.client.requests.get") as mock:
        mock.return_value.json.return_value = {"items": []}
        yield mock


def search_item():
    return {
        "id": {"videoId": "video1"},
        "snippet": {
            "title": "무선이어폰",
            "description": "설명",
            "channelId": "channel1",
            "channelTitle": "채널",
            "publishedAt": "2026-09-01T12:00:00Z",
            "thumbnails": {"high": {"url": "https://example.com/thumb.jpg"}},
        },
    }


def metric_item(video_id="video1", **statistics):
    return {
        "id": video_id,
        "snippet": {"title": "무선이어폰", "publishedAt": "2026-09-01T12:00:00Z"},
        "statistics": statistics,
        "contentDetails": {"duration": "PT2M"},
    }


def comment_item():
    return {
        "snippet": {
            "totalReplyCount": 2,
            "topLevelComment": {
                "id": "comment1",
                "snippet": {
                    "textDisplay": "좋아요",
                    "authorDisplayName": "작성자",
                    "likeCount": 3,
                    "publishedAt": "2026-09-01T12:00:00Z",
                    "updatedAt": "2026-09-02T12:00:00Z",
                },
            },
        },
    }


CASES = [
    (tools.search_paid_promotion_videos, {"keyword": "무선이어폰"}, search_item),
    (tools.get_video_metrics, {"video_ids": ["video1"]}, metric_item),
    (tools.get_video_comments, {"video_id": "video1"}, comment_item),
]


def test_search_parameters_and_parse(http_get):
    http_get.return_value.json.return_value = {"items": [search_item()]}
    rows = tools.search_paid_promotion_videos.invoke(
        {
            "keyword": "무선이어폰",
            "published_after": "2026-08-11T12:00:00Z",
            "max_results": 99,
        }
    )
    assert rows[0] == {
        "video_id": "video1",
        "title": "무선이어폰",
        "description": "설명",
        "channel_id": "channel1",
        "channel_name": "채널",
        "published_at": "2026-09-01T12:00:00Z",
        "thumbnail": "https://example.com/thumb.jpg",
        "url": "https://www.youtube.com/watch?v=video1",
    }
    assert http_get.call_args.kwargs["params"] == {
        "part": "snippet",
        "q": "무선이어폰",
        "type": "video",
        "videoPaidProductPlacement": "true",
        "order": "date",
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "maxResults": 50,
        "publishedAfter": "2026-08-11T12:00:00Z",
        "key": "test-only-key",
    }
    assert http_get.call_args.kwargs["timeout"] == 5
    assert http_get.call_args.args[0].endswith("/search")


@pytest.mark.parametrize("given,expected", [(0, 1), (-2, 1), (20, 20), (99, 50)])
def test_search_limits_and_no_period(http_get, given, expected):
    assert tools.search_paid_promotion_videos.invoke({"keyword": "k", "max_results": given}) == []
    params = http_get.call_args.kwargs["params"]
    assert params["maxResults"] == expected
    assert "publishedAfter" not in params


@pytest.mark.parametrize("date", ["", "2026-09-01", "2026-09-01T00:00:00", "2026-13-01T00:00:00Z"])
def test_search_invalid_date(http_get, date):
    result = tools.search_paid_promotion_videos.invoke({"keyword": "k", "published_after": date})
    assert result["error_code"] == "invalidArgument"
    http_get.assert_not_called()


def test_metrics_empty(http_get):
    assert tools.get_video_metrics.invoke({"video_ids": []}) == []
    http_get.assert_not_called()


def test_metrics_calculation_multiple_ids_and_missing_fields(http_get):
    http_get.return_value.json.return_value = {
        "items": [
            metric_item(viewCount="1000", likeCount="40", commentCount="10"),
            metric_item("video2"),
        ]
    }
    with patch.object(tools, "datetime") as clock:
        clock.now.return_value = NOW
        rows = tools.get_video_metrics.invoke({"video_ids": ["video1", "absent", "video2"]})
    assert [r["video_id"] for r in rows] == ["video1", "video2"]
    assert rows[0]["engagement_rate"] == 5
    assert rows[0]["daily_views"] == 100
    assert rows[0]["duration"] == "PT2M"
    assert rows[0]["tags"] == []
    assert rows[0]["description"] == ""
    assert rows[1]["views"] == rows[1]["likes"] == rows[1]["comments"] == 0
    assert rows[1]["engagement_rate"] == rows[1]["daily_views"] == 0
    assert http_get.call_args.kwargs["params"]["id"] == "video1,absent,video2"
    assert http_get.call_args.kwargs["params"]["part"] == "snippet,statistics,contentDetails"


@pytest.mark.parametrize(
    "statistics,rate",
    [
        ({"viewCount": "100", "likeCount": "5"}, 5),
        ({"viewCount": "100", "commentCount": "2"}, 2),
        ({"viewCount": "0"}, 0),
    ],
)
def test_same_day_and_missing_counts(http_get, statistics, rate):
    item = metric_item(**statistics)
    item["snippet"]["publishedAt"] = "2026-09-11T01:00:00Z"
    http_get.return_value.json.return_value = {"items": [item]}
    with patch.object(tools, "datetime") as clock:
        clock.now.return_value = NOW
        row = tools.get_video_metrics.invoke({"video_ids": ["video1"]})[0]
    assert row["engagement_rate"] == rate
    assert row["daily_views"] == int(statistics["viewCount"])


def test_batch_all_ids_and_no_partial_success(http_get):
    ids = [f"video{i}" for i in range(51)]
    http_get.return_value.json.side_effect = [
        {"items": [metric_item(ids[0])]},
        {"items": [metric_item(ids[-1])]},
    ]
    rows = tools.get_video_metrics.invoke({"video_ids": ids + [ids[0]]})
    assert len(rows) == 2
    assert len(http_get.call_args_list[0].kwargs["params"]["id"].split(",")) == 50
    assert http_get.call_args_list[1].kwargs["params"]["id"] == ids[-1]
    http_get.return_value.json.side_effect = [{"items": [metric_item()]}, {"items": [{}]}]
    result = tools.get_video_metrics.invoke({"video_ids": ids})
    assert result["error_code"] == "invalidResponse"


@pytest.mark.parametrize("order", ["time", "relevance"])
@pytest.mark.parametrize("given,expected", [(0, 1), (-1, 1), (50, 50), (999, 100)])
def test_comments_order_limits_and_parse(http_get, order, given, expected):
    http_get.return_value.json.return_value = {"items": [comment_item()]}
    result = tools.get_video_comments.invoke(
        {
            "video_id": "video1",
            "order": order,
            "max_results": given,
        }
    )
    assert result["comment_count_returned"] == 1
    assert result["comments"][0] == {
        "comment_id": "comment1",
        "text": "좋아요",
        "author": "작성자",
        "like_count": 3,
        "published_at": "2026-09-01T12:00:00Z",
        "updated_at": "2026-09-02T12:00:00Z",
        "reply_count": 2,
    }
    assert http_get.call_args.kwargs["params"] == {
        "part": "snippet",
        "videoId": "video1",
        "maxResults": expected,
        "order": order,
        "textFormat": "plainText",
        "key": "test-only-key",
    }
    assert "수집된 공개 댓글 기준" in result["analysis_note"]


def test_invalid_order_no_api(http_get):
    result = tools.get_video_comments.invoke({"video_id": "video1", "order": "bad"})
    assert result["error_code"] == "invalidOrder"
    http_get.assert_not_called()


@pytest.mark.parametrize("tool,args,factory", CASES)
@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"unexpected": True},
        {"items": None},
        {"items": {}},
        {"items": [None]},
        {"items": [{}]},
    ],
)
def test_malformed_response_is_safe(http_get, tool, args, factory, payload):
    http_get.return_value.json.return_value = payload
    # 실제 팀 GuardrailedTool 래퍼를 통과해도 KeyError/TypeError가 전파되지 않는다.
    wrapped = wrap_tool_with_guardrails(tool, [YouTubeAnalyticsGuardrail()])
    result = wrapped.invoke(args)
    assert result["error_code"] == "invalidResponse"
    assert result["error"] == ERROR_MESSAGES["invalidResponse"]


@pytest.mark.parametrize("tool,args,factory", CASES)
def test_normal_empty_distinct_from_failure(http_get, tool, args, factory):
    result = tool.invoke(args)
    if tool.name == "get_video_comments":
        assert result["comments"] == []
        assert "error" not in result
    else:
        assert result == []


@pytest.mark.parametrize("tool,args,factory", CASES)
@pytest.mark.parametrize(
    "reason,status",
    [
        ("commentsDisabled", 403),
        ("videoNotFound", 404),
        ("quotaExceeded", 403),
        ("forbidden", 403),
        (SECRET, 500),
    ],
)
def test_http_errors_no_raw_response(http_get, caplog, tool, args, factory, reason, status):
    response = Mock(status_code=status)
    response.json.return_value = {"error": {"message": SECRET, "errors": [{"reason": reason}]}}
    http_get.return_value.raise_for_status.side_effect = requests.HTTPError(
        SECRET, response=response
    )
    result = tool.invoke(args)
    assert result["error_code"] == (reason if reason in ERROR_MESSAGES else "apiError")
    assert SECRET not in json.dumps(result)
    assert SECRET not in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize("tool,args,factory", CASES)
@pytest.mark.parametrize(
    "error",
    [requests.Timeout(SECRET), requests.ConnectionError(SECRET), requests.RequestException(SECRET)],
)
def test_network_errors_no_mock_data(http_get, tool, args, factory, error):
    http_get.side_effect = error
    result = tool.invoke(args)
    assert result["error_code"] == "networkError"
    assert SECRET not in json.dumps(result)
    assert "Fallback Mock" not in json.dumps(result)


@pytest.mark.parametrize("value", [SECRET, None, [], {}, 1.5, True, -1])
@pytest.mark.parametrize("field", ["viewCount", "likeCount", "commentCount"])
def test_metric_count_parsing_is_safe(http_get, caplog, value, field):
    http_get.return_value.json.return_value = {"items": [metric_item(**{field: value})]}
    result = tools.get_video_metrics.invoke({"video_ids": ["video1"]})
    assert result == {"error": ERROR_MESSAGES["invalidResponse"], "error_code": "invalidResponse"}
    assert SECRET not in caplog.text


@pytest.mark.parametrize("field", ["likeCount", "totalReplyCount"])
def test_comment_count_parsing_is_safe(http_get, field):
    item = comment_item()
    if field == "likeCount":
        item["snippet"]["topLevelComment"]["snippet"][field] = SECRET
    else:
        item["snippet"][field] = SECRET
    http_get.return_value.json.return_value = {"items": [item]}
    result = tools.get_video_comments.invoke({"video_id": "video1"})
    assert result["error_code"] == "invalidResponse"
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("tool,args,factory", CASES)
def test_bad_json(http_get, tool, args, factory):
    http_get.return_value.json.side_effect = requests.exceptions.JSONDecodeError(SECRET, "", 0)
    result = tool.invoke(args)
    assert result["error_code"] == "invalidResponse"
    assert SECRET not in str(result)


@pytest.mark.parametrize("tool,args,factory", CASES)
def test_missing_key_no_network(http_get, monkeypatch, tool, args, factory):
    monkeypatch.setattr("src.modules.yt_analytics.client.settings.YOUTUBE_API_KEY", None)
    assert tool.invoke(args)["error_code"] == "missingApiKey"
    http_get.assert_not_called()


def test_structured_pii_sanitization_preserves_original_and_url(http_get):
    item = comment_item()
    item["snippet"]["topLevelComment"]["snippet"][
        "textDisplay"
    ] = "<b>문의</b> user@example.com 010-1234-5678"
    http_get.return_value.json.return_value = {"items": [item]}
    raw = tools.get_video_comments.invoke({"video_id": "video1"})
    original = copy.deepcopy(raw)
    guard = YouTubeAnalyticsGuardrail()
    sanitized = guard.sanitize_output("get_video_comments", raw)
    assert raw == original
    assert sanitized["comments"][0]["text"] == "문의 [EMAIL_MASKED] [PHONE_MASKED]"
    assert guard.sanitize_output(
        "get_video_metrics", {"url": "https://example.com/01012345678"}
    ) == {
        "url": "https://example.com/01012345678",
    }


def test_non_b_structured_output_is_unchanged():
    guard = YouTubeAnalyticsGuardrail()
    output = {"label": "<b>채널</b> user@example.com"}

    assert guard.sanitize_output("get_channel_stats", output) is output


def test_search_metrics_comments_handoff(http_get):
    http_get.return_value.json.side_effect = [
        {"items": [search_item()]},
        {"items": [metric_item(viewCount="100")]},
        {"items": [comment_item()]},
    ]
    candidates = tools.search_paid_promotion_videos.invoke(
        {
            "keyword": "무선이어폰",
            "published_after": "2026-08-11T12:00:00Z",
        }
    )
    # A가 반환하는 snake_case video_id 목록도 같은 인터페이스로 연결한다.
    metrics = tools.get_video_metrics.invoke({"video_ids": [row["video_id"] for row in candidates]})
    comments = tools.get_video_comments.invoke({"video_id": metrics[0]["video_id"]})
    assert candidates[0]["url"] == metrics[0]["url"]
    assert comments["comment_count_returned"] == 1
    assert [call.args[0].split("/")[-1] for call in http_get.call_args_list] == [
        "search",
        "videos",
        "commentThreads",
    ]
