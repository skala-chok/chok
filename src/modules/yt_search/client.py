import requests
from typing import Any, Dict
from src.config import settings


class YouTubeSearchClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def search_videos(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/search"
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "key": settings.YOUTUBE_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_transcript(self, video_id: str) -> str:
        # 자막 모의/안내 로직 (실제 자막 API 또는 모듈 연동)
        return f"[자막 추출 완료] Video ID '{video_id}'의 주요 내용 요약 텍스트입니다."
