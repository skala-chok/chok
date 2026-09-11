# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: YouTube Data API v3 영상 검색 클라이언트를 작성합니다.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 max_results 제한 등 가드레일을 작성하세요.
# ==============================================================================

import logging
from typing import Any, Dict, Optional

import requests
from src.config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# 🎯 [코드 참고사항: YouTube Data API v3 검색 클라이언트]
# 1. 하네스 룰 1-1 준수 (Rule 1-1 Fallback Mock Data Contract):
#    - YouTube API Quota(일 10,000 unit 제한) 초과 또는 5xx/Timeout 발생 시
#      정상 응답과 100% 동일한 items -> id -> videoId/channelId 및 snippet 구조의 폴백 데이터 반환
# 2. 타임아웃 방어 (timeout=5s):
#    - 외부 API 지연 시 시스템 블로킹 차단
# 3. RFC3339 UTC 타임스탬프 변환 (_rfc3339):
#    - 사용자가 입력한 YYYY-MM-DD 형식을 Google API 필수 규격(YYYY-MM-DDTHH:MM:SSZ)으로 자동 보정
# ==============================================================================


class YouTubeSearchClient:
    """YouTube Data API v3 기반 영상/채널 검색 및 재생목록 조회 클라이언트."""
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def _search(
        self, params: Dict[str, Any], fallback_id_key: str = "videoId"
    ) -> Dict[str, Any]:
        """[하네스 룰 1-1] 검색 요청 수행 및 장애 시 표준 스키마 폴백 반환."""
        try:
            response = requests.get(f"{self.BASE_URL}/search", params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "YouTube search failed (%s); returning fallback.", type(exc).__name__
            )
            return {"items": [{"id": {fallback_id_key: "fallback_channel" if fallback_id_key == "channelId" else "fallback_video"}, "snippet": {
                "title": "[Fallback Mock] YouTube search unavailable",
                "channelTitle": "System Fallback", "description": str(exc),
                "publishedAt": "1970-01-01T00:00:00Z"}}]}

    def search_videos(
        self, query: str, max_results: int = 5, channel_id: Optional[str] = None,
        published_after: Optional[str] = None, published_before: Optional[str] = None,
        paid_product_placement: bool = False,
    ) -> Dict[str, Any]:
        """키워드 기반 영상 검색 (날짜 범위 및 유료 광고 필터 지원)."""
        url = f"{self.BASE_URL}/search"
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "key": settings.YOUTUBE_API_KEY,
        }
        if channel_id:
            params["channelId"] = channel_id
        if published_after:
            params["publishedAfter"] = self._rfc3339(published_after)
        if published_before:
            params["publishedBefore"] = self._rfc3339(published_before)
        if paid_product_placement:
            params["videoPaidProductPlacement"] = "true"
        return self._search(params)

    @staticmethod
    def _rfc3339(value: str) -> str:
        """YYYY-MM-DD 날짜를 구글 API 필수 규격인 RFC3339 UTC 타임스탬프(YYYY-MM-DDT00:00:00Z)로 변환합니다."""
        return f"{value}T00:00:00Z" if len(value) == 10 else value

    def find_channels(self, company: str, max_results: int = 5) -> Dict[str, Any]:
        return self._search(
            {
                "part": "snippet", "q": company, "type": "channel",
                "maxResults": max_results, "key": settings.YOUTUBE_API_KEY,
            },
            fallback_id_key="channelId",
        )

    def get_channel_details(self, channel_id: str) -> Dict[str, Any]:
        try:
            response = requests.get(f"{self.BASE_URL}/channels", params={"part": "snippet,statistics,status", "id": channel_id, "key": settings.YOUTUBE_API_KEY}, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "YouTube channel lookup failed (%s); returning fallback.",
                type(exc).__name__,
            )
            return {"items": [{"id": channel_id, "snippet": {"title": "[Fallback Mock] Channel unavailable", "description": str(exc), "thumbnails": {}}, "statistics": {"viewCount": "0", "videoCount": "0", "hiddenSubscriberCount": True}, "status": {}}]}

    def get_recent_uploads(self, channel_id: str, max_results: int = 20) -> Dict[str, Any]:
        try:
            channel_response = requests.get(f"{self.BASE_URL}/channels", params={"part": "contentDetails", "id": channel_id, "key": settings.YOUTUBE_API_KEY}, timeout=5)
            channel_response.raise_for_status()
            items = channel_response.json().get("items", [])
            if not items:
                return {"items": []}
            playlist_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            response = requests.get(f"{self.BASE_URL}/playlistItems", params={"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": max_results, "key": settings.YOUTUBE_API_KEY}, timeout=5)
            response.raise_for_status()
            return response.json()
        except (KeyError, requests.exceptions.RequestException) as exc:
            logger.warning(
                "YouTube uploads lookup failed (%s); returning fallback.",
                type(exc).__name__,
            )
            return {"items": [{"contentDetails": {"videoId": "fallback_video", "videoPublishedAt": "1970-01-01T00:00:00Z"}, "snippet": {"title": "[Fallback Mock] Recent uploads unavailable", "description": str(exc), "thumbnails": {}}}]}
