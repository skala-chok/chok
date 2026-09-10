# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: 네이버 쇼핑 및 데이터랩 트렌드 API와 직접 통신하는 함수를 작성합니다.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 0원 상품 필터링 등 가드레일을 작성하세요.
# ==============================================================================

import requests
from typing import Any, Dict, List, Optional
from src.config import settings


class NaverShoppingClient:
    SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
    DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"

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
            "X-Naver-Client-Id": cid or "",
            "X-Naver-Client-Secret": csec or "",
            "Content-Type": "application/json",
        }

    @headers.setter
    def headers(self, value: Dict[str, str]):
        self._headers = value

    def search_shop(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(self.SHOP_URL, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_datalab_trend(self, keywords: List[str], start_date: str, end_date: str) -> Dict[str, Any]:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "month",
            "keywordGroups": [{"groupName": kw, "keywords": [kw]} for kw in keywords],
        }
        resp = requests.post(self.DATALAB_URL, headers=self.headers, json=body, timeout=5)
        resp.raise_for_status()
        return resp.json()
