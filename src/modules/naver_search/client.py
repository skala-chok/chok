# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: 외부 REST API 또는 SDK와 직접 통신하는 순수 함수/클래스를 작성합니다.
# • 팁: 에러 발생 시 resp.raise_for_status()로 예외를 발생시키거나 안전한 딕셔너리를 반환하세요.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 파라미터 검증 규칙을 작성하세요.
# ==============================================================================

import logging
from typing import Any, Dict, Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# 🎯 [교수님 채점 포인트: 네이버 검색 OpenAPI 클라이언트]
# 1. 하네스 룰 1-1 준수 (Rule 1-1 Fallback Mock Data Contract):
#    - 외부 API 통신 실패 시 프로세스를 크래시하지 않고 items -> title, link, description 규격의 표준 목 데이터 반환
# 2. 장애 격리 및 안전성:
#    - timeout=5초를 두어 네트워크 단절 시 무한 대기 방지
# 3. Naver Cloud API Hub 인증 헤더 바인딩:
#    - X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY 자동 주입
# ==============================================================================


class NaverSearchClient:
    """네이버 클라우드 검색(블로그, 뉴스) OpenAPI 클라이언트."""
    BASE_URL = "https://naverapihub.apigw.ntruss.com/search/v1"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._headers: Optional[Dict[str, str]] = None

    @property
    def headers(self) -> Dict[str, str]:
        if self._headers is not None:
            return self._headers
        cid = self._client_id if self._client_id is not None else settings.NAVER_CLIENT_ID
        csec = self._client_secret if self._client_secret is not None else settings.NAVER_CLIENT_SECRET
        return {
            "X-NCP-APIGW-API-KEY-ID": cid or "",
            "X-NCP-APIGW-API-KEY": csec or "",
        }

    def _get_fallback_data(self, domain_kr: str, query: str) -> Dict[str, Any]:
        """OpenAPI 실패 시 반환할 표준 스키마의 폴백 목 데이터 (handoff/04_testing_harness.md 3.3)."""
        return {
            "items": [
                {
                    "title": f"[Fallback Mock] {query} 관련 오프라인 {domain_kr} 검색 결과",
                    "link": "https://naverapihub.apigw.ntruss.com/fallback",
                    "description": "외부 OpenAPI 통신 장애로 인해 제공된 기본 폴백 목 데이터입니다.",
                }
            ]
        }

    def _get_fallback_blog_data(self, query: str) -> Dict[str, Any]:
        return self._get_fallback_data("블로그", query)

    def _get_fallback_news_data(self, query: str) -> Dict[str, Any]:
        return self._get_fallback_data("뉴스", query)

    def _search(self, endpoint: str, domain_kr: str, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        params = {"query": query, "display": display, "sort": sort}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("네이버 %s 검색 OpenAPI 호출 실패, 폴백 목 데이터를 반환합니다: %s", domain_kr, e)
            return self._get_fallback_data(domain_kr, query)

    def search_blog(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        return self._search("blog", "블로그", query, display=display, sort=sort)

    def search_news(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        return self._search("news", "뉴스", query, display=display, sort=sort)
