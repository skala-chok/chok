# ==============================================================================
# 🔴 [Step 1 - 빨간점] 외부 API 통신 클라이언트 계층
# • 역할: 네이버 쇼핑 및 데이터랩 트렌드 API와 직접 통신하는 함수를 작성합니다.
# ➔ 다음 단계: 🟠 [Step 2] guardrails.py 로 이동하여 0원 상품 필터링 등 가드레일을 작성하세요.
# ==============================================================================

import logging
from typing import Any, Dict, List, Optional

import requests

from src.config import settings

logger = logging.getLogger(__name__)


class NaverShoppingClient:
    # NAVER API HUB 검색어 트렌드 API (구 datalab/search 대체)
    DATALAB_URL = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
    # NAVER API HUB 쇼핑 인사이트 API 묶음 (분야/키워드 x 전체/성별/연령)
    SHOPPING_INSIGHT_BASE_URL = "https://naverapihub.apigw.ntruss.com/shopping/v1"

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
            "Content-Type": "application/json",
        }

    @headers.setter
    def headers(self, value: Dict[str, str]):
        self._headers = value

    def _get_fallback_trend_data(self, label: str) -> Dict[str, Any]:
        """OpenAPI 실패 시 반환할 표준 스키마의 폴백 목 데이터 (handoff/04_testing_harness.md 3.3)."""
        return {
            "results": [
                {
                    "title": f"[Fallback Mock] {label}",
                    "data": [
                        {
                            "period": "1970-01-01",
                            "ratio": 0,
                        }
                    ],
                }
            ]
        }

    def get_datalab_trend(self, keywords: List[str], start_date: str, end_date: str) -> Dict[str, Any]:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "month",
            "keywordGroups": [{"groupName": kw, "keywords": [kw]} for kw in keywords],
        }
        try:
            resp = requests.post(self.DATALAB_URL, headers=self.headers, json=body, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("네이버 검색어 트렌드 OpenAPI 호출 실패, 폴백 목 데이터를 반환합니다: %s", e)
            label = ", ".join(keywords) if keywords else "키워드"
            return self._get_fallback_trend_data(f"{label} 관련 오프라인 검색 추이 데이터")

    def _post_shopping_insight(self, path: str, body: Dict[str, Any], fallback_label: str) -> Dict[str, Any]:
        url = f"{self.SHOPPING_INSIGHT_BASE_URL}/{path}"
        try:
            resp = requests.post(url, headers=self.headers, json=body, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("네이버 쇼핑 인사이트(%s) OpenAPI 호출 실패, 폴백 목 데이터를 반환합니다: %s", path, e)
            return self._get_fallback_trend_data(f"{fallback_label} 관련 오프라인 쇼핑 인사이트 데이터")

    @staticmethod
    def _with_optional(body: Dict[str, Any], device: Optional[str], gender: Optional[str], ages: Optional[List[str]]) -> Dict[str, Any]:
        if device:
            body["device"] = device
        if gender:
            body["gender"] = gender
        if ages:
            body["ages"] = ages
        return body

    def get_category_trend(
        self,
        categories: Dict[str, str],
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        gender: Optional[str] = None,
        ages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/categories - 분야별(최대 3개) 클릭 트렌드 비교"""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": [{"name": name, "param": [code]} for name, code in list(categories.items())[:3]],
        }
        label = ", ".join(categories.keys()) if categories else "분야"
        return self._post_shopping_insight("categories", self._with_optional(body, device, gender, ages), label)

    def get_category_gender_trend(
        self,
        category_code: str,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        ages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/category/gender - 특정 분야의 성별 클릭 트렌드"""
        body = {"startDate": start_date, "endDate": end_date, "timeUnit": time_unit, "category": category_code}
        return self._post_shopping_insight(
            "category/gender", self._with_optional(body, device, None, ages), category_code
        )

    def get_category_age_trend(
        self,
        category_code: str,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/category/age - 특정 분야의 연령별 클릭 트렌드"""
        body = {"startDate": start_date, "endDate": end_date, "timeUnit": time_unit, "category": category_code}
        return self._post_shopping_insight(
            "category/age", self._with_optional(body, device, gender, None), category_code
        )

    def get_category_keyword_trend(
        self,
        category_code: str,
        keywords: Dict[str, str],
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        gender: Optional[str] = None,
        ages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/category/keywords - 분야 내 키워드별(최대 5개) 클릭 트렌드 비교"""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category_code,
            "keyword": [{"name": name, "param": [term]} for name, term in list(keywords.items())[:5]],
        }
        label = f"{category_code}: {', '.join(keywords.keys())}" if keywords else category_code
        return self._post_shopping_insight(
            "category/keywords", self._with_optional(body, device, gender, ages), label
        )

    def get_keyword_gender_trend(
        self,
        category_code: str,
        keyword: str,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        ages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/category/keyword/gender - 특정 키워드의 성별 클릭 트렌드"""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category_code,
            "keyword": keyword,
        }
        return self._post_shopping_insight(
            "category/keyword/gender", self._with_optional(body, device, None, ages), keyword
        )

    def get_keyword_age_trend(
        self,
        category_code: str,
        keyword: str,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        device: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /shopping/v1/category/keyword/age - 특정 키워드의 연령별 클릭 트렌드"""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category_code,
            "keyword": keyword,
        }
        return self._post_shopping_insight(
            "category/keyword/age", self._with_optional(body, device, gender, None), keyword
        )
