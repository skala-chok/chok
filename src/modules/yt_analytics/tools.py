# ==============================================================================
# 🟡 [Step 3 - 노란점] LangChain 도구(@tool) 정의 계층
# • 역할: LLM이 호출할 채널 통계 조회 및 댓글 수집 도구를 정의합니다.
# ➔ 다음 단계: 🟢 [Step 4] context.py 로 이동하여 통계/댓글 분석 지침을 작성하세요.
# ==============================================================================

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool

from .client import YouTubeAnalyticsClient, YouTubeAPIError
from .guardrails import YouTubeAnalyticsGuardrail, parse_timestamp

logger = logging.getLogger(__name__)
client = YouTubeAnalyticsClient()
guardrail = YouTubeAnalyticsGuardrail()

ANALYSIS_NOTE = "수집된 공개 댓글 기준이며 전체 고객/시청자를 대표하지 않습니다. 삭제된 댓글과 답글 전체는 포함되지 않습니다. 원문과 LLM의 해석을 구분하세요."


@tool
def get_channel_stats(channel_id: str) -> str:
    """Get subscriber count, total views, and video count of a YouTube channel by channel_id."""
    try:
        data = client.get_channel_info(channel_id)
        items = data.get("items", [])
        if not items:
            return f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다."
        stats = items[0].get("statistics", {})
        return (
            f"[채널 통계 ({channel_id})]\n"
            f"- 구독자 수: {int(stats.get('subscriberCount', 0)):,}명\n"
            f"- 총 조회수: {int(stats.get('viewCount', 0)):,}회\n"
            f"- 업로드 영상 수: {stats.get('videoCount', 0)}개"
        )
    except Exception as e:
        return f"채널 통계 조회 중 오류: {str(e)}"


def _text(value: Any) -> str:
    """외부 문자열의 타입을 확인한다. 원문을 오류 메시지에 넣지 않는다."""
    if not isinstance(value, str):
        raise ValueError
    return value


def _count(value: Any) -> int:
    """공개 카운트의 정수/숫자 문자열만 허용한다."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError
    number = int(value)
    if number < 0:
        raise ValueError
    return number


def _failure(error: YouTubeAPIError) -> Dict[str, Any]:
    """실패와 정상 빈 결과를 구별하고 안전한 코드만 기록한다."""
    logger.warning("YouTube 조회 실패: code=%s status=%s", error.code, error.status)
    return {"error": str(error), "error_code": error.code}


@tool
def search_paid_promotion_videos(
    keyword: str,
    published_after: Optional[str] = None,
    max_results: int = 20,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """키워드 관련 '유료 프로모션 포함' 표시 콘텐츠를 검색할 때 사용한다.

    YouTube Ads 집행 여부를 뜻하지 않는다. 최신순 첫 페이지, 최대 50개를 반환한다.
    Args:
        keyword: 비어 있지 않은 검색어.
        published_after: 시간대가 있는 RFC3339 날짜. 생략하면 기간 제한 없음.
        max_results: 요청 개수. 1~50으로 제한한다.
    Returns:
        snake_case 영상 목록. 실패 시 error/error_code 딕셔너리이며 빈 결과와 구분한다.
    """
    validation = guardrail.validate_tool_args(
        "search_paid_promotion_videos",
        {
            "keyword": keyword,
            "published_after": published_after,
            "max_results": max_results,
        },
    )
    if not validation.passed:
        return {"error": validation.error_message, "error_code": "invalidArgument"}
    try:
        response = client.search_paid_promotion_videos(keyword, published_after, max_results)
        results = []
        for item in response["items"]:
            snippet = item["snippet"]
            video_id = _text(item["id"]["videoId"])
            published_at = _text(snippet["publishedAt"])
            parse_timestamp(published_at)
            thumbnail = snippet.get("thumbnails", {}).get("high", {}).get("url")
            if thumbnail is not None:
                _text(thumbnail)
            results.append(
                {
                    "video_id": video_id,
                    "title": _text(snippet["title"]),
                    "description": _text(snippet.get("description", "")),
                    "channel_id": _text(snippet["channelId"]),
                    "channel_name": _text(snippet["channelTitle"]),
                    "published_at": published_at,
                    "thumbnail": thumbnail,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        return results
    except YouTubeAPIError as error:
        return _failure(error)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return _failure(YouTubeAPIError("invalidResponse"))


@tool
def get_video_metrics(video_ids: List[str]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """탐색한 video_id 목록의 공개 메타데이터·반응 지표 비교에 사용한다.

    최대 50개씩 모두 조회한다. 누락 ID는 생략, 누락된 카운트는 계산상 0이다.
    engagement_rate는 공개 참여율(%)이며 광고비 대비 효율/CTR/ROAS가 아니다.
    daily_views는 게시 이후 평균이며 실제 일별 추이가 아니다. 근거 url을 유지한다.
    Args:
        video_ids: 단일 영상 ID의 목록. 빈 목록이면 API를 호출하지 않는다.
    Returns:
        영상 지표 목록. 어느 배치든 실패하면 부분 목록 대신 error/error_code를 반환한다.
    """
    validation = guardrail.validate_tool_args("get_video_metrics", {"video_ids": video_ids})
    if not validation.passed:
        return {"error": validation.error_message, "error_code": "invalidArgument"}
    ids = list(dict.fromkeys(video_ids))
    now = datetime.now(timezone.utc)
    results = []
    try:
        for start in range(0, len(ids), 50):
            stop = start + 50
            response = client.get_video_metrics(ids[start:stop])
            for item in response["items"]:
                snippet = item["snippet"]
                statistics = item.get("statistics", {})
                video_id = _text(item["id"])
                views = _count(statistics.get("viewCount", 0))
                likes = _count(statistics.get("likeCount", 0))
                comments = _count(statistics.get("commentCount", 0))
                published_at = _text(snippet["publishedAt"])
                elapsed_days = max((now - parse_timestamp(published_at)).days, 1)
                tags = snippet.get("tags", [])
                if not isinstance(tags, list):
                    raise ValueError
                results.append(
                    {
                        "video_id": video_id,
                        "title": _text(snippet["title"]),
                        "description": _text(snippet.get("description", "")),
                        "tags": [_text(tag) for tag in tags],
                        "published_at": published_at,
                        "duration": _text(item["contentDetails"]["duration"]),
                        "views": views,
                        "likes": likes,
                        "comments": comments,
                        "engagement_rate": round((likes + comments) / max(views, 1) * 100, 3),
                        "daily_views": round(views / elapsed_days, 1),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                    }
                )
        return results
    except YouTubeAPIError as error:
        return _failure(error)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return _failure(YouTubeAPIError("invalidResponse"))


@tool
def get_video_comments(
    video_id: str,
    max_results: int = 50,
    order: str = "relevance",
    max_comments: Optional[int] = None,
) -> Dict[str, Any]:
    """소비자 반응·반복 의견 분석에 필요한 공개 최상위 댓글 원문을 수집한다.

    감성 분석은 하지 않는다. 수집된 공개 댓글은 전체 고객/시청자를 대표하지 않는다.
    Args:
        video_id: 댓글을 조회할 단일 영상 ID.
        max_results: 첫 페이지 요청 개수. 1~100으로 제한한다.
        order: relevance 또는 time.
        max_comments: 기존 호출 호환 인자(1~50). 지정하면 max_results보다 우선한다.
    Returns:
        정규화 댓글과 analysis_note. 실패 시 error/error_code가 추가된다.
    """
    result: Dict[str, Any] = {
        "video_id": video_id,
        "comment_count_returned": 0,
        "order": order,
        "comments": [],
        "analysis_note": ANALYSIS_NOTE,
    }
    validation = guardrail.validate_tool_args(
        "get_video_comments",
        {
            "video_id": video_id,
            "max_results": max_results,
            "order": order,
            "max_comments": max_comments,
        },
    )
    if not validation.passed:
        code = "invalidOrder" if order not in {"relevance", "time"} else "invalidArgument"
        return {**result, "error": validation.error_message, "error_code": code}
    try:
        limit = max_comments if max_comments is not None else max_results
        response = client.get_comments(video_id, limit, order=order)
        comments = []
        for item in response["items"]:
            thread = item["snippet"]
            top = thread["topLevelComment"]
            snippet = top["snippet"]
            published_at = snippet.get("publishedAt")
            updated_at = snippet.get("updatedAt")
            for timestamp in (published_at, updated_at):
                if timestamp is not None:
                    parse_timestamp(timestamp)
            author = snippet.get("authorDisplayName")
            if author is not None:
                _text(author)
            comments.append(
                {
                    "comment_id": _text(top["id"]),
                    "text": _text(snippet["textDisplay"]),
                    "author": author,
                    "like_count": _count(snippet.get("likeCount", 0)),
                    "published_at": published_at,
                    "updated_at": updated_at,
                    "reply_count": _count(thread.get("totalReplyCount", 0)),
                }
            )
        return {**result, "comments": comments, "comment_count_returned": len(comments)}
    except YouTubeAPIError as error:
        return {**result, **_failure(error)}
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return {**result, **_failure(YouTubeAPIError("invalidResponse"))}
