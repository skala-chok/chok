# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: YouTube Data API 채널 통계 및 영상 댓글 수집 클라이언트를 작성합니다.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 댓글 PII 마스킹 등 가드레일을 작성하세요.
# ==============================================================================

import requests
from typing import Any, Dict, List, Optional
from src.config import settings


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

    def get_comments(self, video_id: str, max_comments: int = 10) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_comments,
            "key": settings.YOUTUBE_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
