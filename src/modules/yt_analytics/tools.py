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
from .guardrails import parse_timestamp

logger = logging.getLogger(__name__)
client = YouTubeAnalyticsClient()

ANALYSIS_NOTE = (
    "수집된 공개 댓글 기준이며 전체 고객/시청자를 대표하지 않습니다. "
    "삭제된 댓글과 답글 전체는 포함되지 않습니다. 원문과 LLM의 해석을 구분하세요."
)


def _safe_int(val: Any) -> int:
    try:
        return max(0, int(val or 0))
    except (ValueError, TypeError):
        return 0


def _failure(error: Exception) -> Dict[str, Any]:
    code = getattr(error, "code", "invalidResponse")
    logger.warning("YouTube 조회 실패: code=%s", code)
    return {"error": str(error), "error_code": code}


@tool
def get_channel_stats(channel_id: str) -> str:
    """채널 ID(channel_id)를 기반으로 YouTube 채널의 구독자 수, 총 조회수, 동영상 수를 조회합니다."""
    try:
        data = client.get_channel_info(channel_id)
        items = data.get("items", [])
        if not items:
            return f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다."
        stats = items[0].get("statistics", {})
        return (
            f"[채널 통계 ({channel_id})]\n"
            f"- 구독자 수: {_safe_int(stats.get('subscriberCount')):,}명\n"
            f"- 총 조회수: {_safe_int(stats.get('viewCount')):,}회\n"
            f"- 업로드 영상 수: {stats.get('videoCount', 0)}개"
        )
    except Exception as e:
        return f"채널 통계 조회 중 오류: {str(e)}"


@tool
def search_paid_promotion_videos(
    keyword: str,
    published_after: Optional[str] = None,
    max_results: int = 20,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """키워드 관련 '유료 프로모션 포함' 표시 콘텐츠를 검색할 때 사용한다."""
    if published_after:
        try:
            parse_timestamp(published_after)
        except ValueError:
            return {"error": "시간대가 있는 RFC3339 날짜를 입력하세요.", "error_code": "invalidArgument"}
    try:
        response = client.search_paid_promotion_videos(keyword, published_after, max_results)
        results = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            vid = item.get("id", {}).get("videoId", "")
            results.append({
                "video_id": vid,
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel_id": snippet.get("channelId", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return results
    except YouTubeAPIError as error:
        return _failure(error)
    except Exception:
        return _failure(YouTubeAPIError("invalidResponse"))


@tool
def get_video_metrics(video_ids: List[str]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """탐색한 video_id 목록의 공개 메타데이터·반응 지표 비교에 사용한다."""
    if not video_ids:
        return []
    ids = list(dict.fromkeys(video_ids))
    now = datetime.now(timezone.utc)
    results = []
    try:
        for start in range(0, len(ids), 50):
            response = client.get_video_metrics(ids[start:start + 50])
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                vid = item.get("id", "")
                views = _safe_int(stats.get("viewCount"))
                likes = _safe_int(stats.get("likeCount"))
                comments = _safe_int(stats.get("commentCount"))
                pub = snippet.get("publishedAt", "")
                days = max((now - parse_timestamp(pub)).days, 1) if pub else 1
                results.append({
                    "video_id": vid,
                    "title": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "tags": snippet.get("tags", []) if isinstance(snippet.get("tags"), list) else [],
                    "published_at": pub,
                    "duration": item.get("contentDetails", {}).get("duration", ""),
                    "views": views,
                    "likes": likes,
                    "comments": comments,
                    "engagement_rate": round((likes + comments) / max(views, 1) * 100, 3),
                    "daily_views": round(views / days, 1),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
        return results
    except YouTubeAPIError as error:
        return _failure(error)
    except Exception:
        return _failure(YouTubeAPIError("invalidResponse"))


@tool
def get_video_comments(
    video_id: str,
    max_results: int = 50,
    order: str = "relevance",
    max_comments: Optional[int] = None,
) -> Dict[str, Any]:
    """소비자 반응·반복 의견 분석에 필요한 공개 최상위 댓글 원문을 수집한다."""
    result: Dict[str, Any] = {
        "video_id": video_id,
        "comment_count_returned": 0,
        "order": order,
        "comments": [],
        "analysis_note": ANALYSIS_NOTE,
    }
    if order not in ("relevance", "time"):
        return {**result, "error": "order는 relevance 또는 time이어야 합니다.", "error_code": "invalidOrder"}
    try:
        limit = max_comments if max_comments is not None else max_results
        response = client.get_comments(video_id, limit, order=order)
        comments = []
        for item in response.get("items", []):
            thread = item.get("snippet", {})
            top = thread.get("topLevelComment", {}).get("snippet", {})
            comments.append({
                "comment_id": thread.get("topLevelComment", {}).get("id", ""),
                "text": top.get("textDisplay", ""),
                "author": top.get("authorDisplayName"),
                "like_count": _safe_int(top.get("likeCount")),
                "published_at": top.get("publishedAt"),
                "updated_at": top.get("updatedAt"),
                "reply_count": _safe_int(thread.get("totalReplyCount")),
            })
        return {**result, "comments": comments, "comment_count_returned": len(comments)}
    except YouTubeAPIError as error:
        return {**result, **_failure(error)}
    except Exception:
        return {**result, **_failure(YouTubeAPIError("invalidResponse"))}
