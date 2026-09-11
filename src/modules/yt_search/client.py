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


class YouTubeSearchClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def _search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.get(f"{self.BASE_URL}/search", params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.warning("YouTube search failed; returning fallback: %s", exc)
            return {"items": [{"id": {"videoId": "fallback_video"}, "snippet": {
                "title": "[Fallback Mock] YouTube search unavailable",
                "channelTitle": "System Fallback", "description": str(exc),
                "publishedAt": "1970-01-01T00:00:00Z"}}]}

    def search_videos(
        self, query: str, max_results: int = 5, channel_id: Optional[str] = None,
        published_after: Optional[str] = None, published_before: Optional[str] = None,
        paid_product_placement: bool = False,
    ) -> Dict[str, Any]:
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
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before
        if paid_product_placement:
            params["videoPaidProductPlacement"] = "true"
        return self._search(params)

    def find_channels(self, company: str, max_results: int = 5) -> Dict[str, Any]:
        return self._search({
            "part": "snippet", "q": company, "type": "channel", "maxResults": max_results,
            "key": settings.YOUTUBE_API_KEY,
        })

    def get_transcript(self, video_id: str) -> str:
        # 자막 모의/안내 로직 (실제 자막 API 또는 모듈 연동)
        return f"[자막 추출 완료] Video ID '{video_id}'의 주요 내용 요약 텍스트입니다."
