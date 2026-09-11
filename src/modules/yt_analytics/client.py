# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: YouTube Data API 채널 통계 및 영상 댓글 수집 클라이언트를 작성합니다.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 댓글 PII 마스킹 등 가드레일을 작성하세요.
# ==============================================================================

from typing import Any, Dict, List, Optional

import requests

from src.config import settings

ERROR_MESSAGES = {
    "commentsDisabled": "이 영상은 댓글 사용이 중지되어 있습니다.",
    "videoNotFound": "영상을 찾을 수 없거나 비공개 상태입니다.",
    "quotaExceeded": "YouTube API 할당량을 초과했습니다.",
    "dailyLimitExceeded": "YouTube API 일일 한도를 초과했습니다.",
    "keyInvalid": "YouTube API 인증 설정을 확인하세요.",
    "forbidden": "YouTube API 접근 권한을 확인하세요.",
    "apiError": "YouTube API 요청에 실패했습니다.",
    "networkError": "YouTube API 연결에 실패했습니다.",
    "invalidResponse": "YouTube API 응답 형식이 올바르지 않습니다.",
    "missingApiKey": "YOUTUBE_API_KEY 환경변수를 설정하세요.",
}


class YouTubeAPIError(RuntimeError):
    """B 전용 오류: 키·원문 응답 대신 안전한 코드/상태만 전달한다."""

    def __init__(self, code: str, status: Optional[int] = None) -> None:
        self.code = code if code in ERROR_MESSAGES else "apiError"
        self.status = status
        super().__init__(ERROR_MESSAGES[self.code])


class YouTubeAnalyticsClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/channels"
        params = {
            "part": "statistics,snippet",
            "id": channel_id,
            "key": settings.YOUTUBE_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def _request(self, resource: str, **params: Any) -> Dict[str, Any]:
        """B 요청의 인증·통신·최상위 응답을 검사한다. 원문 오류는 노출하지 않는다."""
        if not settings.YOUTUBE_API_KEY:
            raise YouTubeAPIError("missingApiKey")
        try:
            response = requests.get(
                f"{self.BASE_URL}/{resource}",
                params={**params, "key": settings.YOUTUBE_API_KEY},
                timeout=5,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as error:
            code = "apiError"
            status = error.response.status_code if error.response is not None else None
            try:
                reasons = error.response.json()["error"]["errors"]
                code = next(
                    (item["reason"] for item in reasons if item["reason"] in ERROR_MESSAGES),
                    code,
                )
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
            raise YouTubeAPIError(code, status) from None
        except requests.exceptions.JSONDecodeError:
            raise YouTubeAPIError("invalidResponse") from None
        except requests.exceptions.RequestException:
            raise YouTubeAPIError("networkError") from None
        except ValueError:
            raise YouTubeAPIError("invalidResponse") from None
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise YouTubeAPIError("invalidResponse")
        if any(not isinstance(item, dict) for item in data["items"]):
            raise YouTubeAPIError("invalidResponse")
        return data

    def search_paid_promotion_videos(
        self,
        keyword: str,
        published_after: Optional[str] = None,
        max_results: int = 20,
    ) -> Dict[str, Any]:
        """유료 프로모션 표시 영상의 첫 페이지를 조회한다."""
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "videoPaidProductPlacement": "true",
            "order": "date",
            "regionCode": "KR",
            "relevanceLanguage": "ko",
            "maxResults": min(max(max_results, 1), 50),
        }
        if published_after is not None:
            params["publishedAfter"] = published_after
        return self._request("search", **params)

    def get_video_metrics(self, video_ids: List[str]) -> Dict[str, Any]:
        """최대 50개 영상의 원본 메타데이터·통계를 조회한다. 배치는 Tool이 담당한다."""
        return self._request(
            "videos",
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
        )

    def get_comments(
        self,
        video_id: str,
        max_comments: int = 10,
        *,
        order: str = "relevance",
    ) -> Dict[str, Any]:
        """공개 최상위 댓글 조회. 기존 client의 max_comments 인자를 유지한다."""
        return self._request(
            "commentThreads",
            part="snippet",
            videoId=video_id,
            maxResults=min(max(max_comments, 1), 100),
            order=order,
            textFormat="plainText",
        )
