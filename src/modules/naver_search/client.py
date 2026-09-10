import requests
from typing import Any, Dict, Optional
from src.config import settings


class NaverSearchClient:
    BASE_URL = "https://openapi.naver.com/v1/search"

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
        }

    @headers.setter
    def headers(self, value: Dict[str, str]):
        self._headers = value

    def search_blog(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/blog.json"
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(url, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def search_news(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/news.json"
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(url, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
