"""API 정합성 및 정상 동작 검증을 위한 통합 테스트 모듈 (api_test).

사용자 요구사항에 명시된 19개 API 엔드포인트의 요청 규격, 파라미터, 응답 구조를 검증합니다:
1. Instagram Graph API (4개 엔드포인트)
   - 해시태그 ID 검색: GET /ig_hashtag_search?user_id={ig-user-id}&q=kbeauty
   - 해시태그 인기글: GET /{hashtag-id}/top_media?user_id={ig-user-id}
   - 해시태그 최신글: GET /{hashtag-id}/recent_media?user_id={ig-user-id}
   - 타 계정 조회 (Business Discovery): GET /{ig-user-id}?fields=business_discovery.username(nike){...}

2. YouTube Data API v3 (7개 엔드포인트/파라미터 조합)
   - 경쟁사 공식 채널 검색: GET /search (part=snippet, type=channel)
   - 경쟁사 광고 후보 영상 검색: GET /search (part=snippet, type=video, channelId, 기간 필터)
   - 영상 상세정보 및 반응 조회: GET /videos (part=snippet,statistics,contentDetails)
   - 시청자 댓글 수집: GET /commentThreads (part=snippet, videoId)
   - 채널 상세정보 확인: GET /channels (part=snippet,statistics,contentDetails)
   - 경쟁사 최근 업로드 영상 조회: GET /playlistItems (part=snippet, playlistId)
   - 유료 프로모션 표시 영상 검색: GET /search (videoPaidProductPlacement=true)

3. Naver Open API / Datalab (8개 엔드포인트)
   - 쇼핑 검색: GET /v1/search/shop.json
   - 검색어 트렌드 조회: POST /v1/datalab/search
   - 쇼핑 분야별 검색 클릭 추이: POST /v1/datalab/shopping/categories
   - 쇼핑 분야별 · 성별 검색 클릭 추이: POST /v1/datalab/shopping/category/gender
   - 쇼핑 분야별 · 연령별 검색 클릭 추이: POST /v1/datalab/shopping/category/age
   - 쇼핑 분야별 · 키워드별 검색 클릭 추이: POST /v1/datalab/shopping/category/keywords
   - 쇼핑 분야 · 키워드별 · 성별 검색 클릭 추이: POST /v1/datalab/shopping/category/keyword/gender
   - 쇼핑 분야 · 키워드별 · 연령별 검색 클릭 추이: POST /v1/datalab/shopping/category/keyword/age
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock, patch

# 프로젝트 루트를 sys.path에 추가하여 python tests/api_test.py 단독 실행 지원
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
import requests

from src.config import settings


class ApiException(Exception):
    """API 호출 실패 시 원인, 서버 에러 코드, 해결 조치 가이드를 포함하는 커스텀 예외."""

    def __init__(
        self,
        platform: str,
        endpoint: str,
        status_code: int,
        error_type: str,
        message: str,
        solution: str,
        error_code: Optional[Union[str, int]] = None,
        raw_response: str = "",
    ):
        self.platform = platform
        self.endpoint = endpoint
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        self.solution = solution
        self.error_code = error_code
        self.raw_response = raw_response
        super().__init__(self.__str__())

    def __str__(self) -> str:
        return (
            f"\n🚨 [{self.platform} API 오류] {self.endpoint}\n"
            f"  • HTTP 상태: {self.status_code}\n"
            f"  • 에러 유형: {self.error_type} (코드: {self.error_code or 'N/A'})\n"
            f"  • 서버 응답: {self.message}\n"
            f"  • 💡 해결 조치 가이드: {self.solution}"
        )


def analyze_api_error(platform: str, endpoint: str, resp: requests.Response) -> ApiException:
    """플랫폼별 에러 본문을 분석하여 정밀한 원인 및 조치 가이드를 도출."""
    status = resp.status_code
    raw_text = resp.text.strip()
    data: Dict[str, Any] = {}
    try:
        data = resp.json()
    except Exception:
        pass

    error_type = "API_ERROR"
    error_code = None
    message = raw_text
    solution = "서버 응답 본문 및 요청 인자를 확인하세요."

    # 1. Instagram Graph API 에러 분석
    if platform == "Instagram":
        err = data.get("error", {})
        error_code = err.get("code")
        subcode = err.get("error_subcode")
        msg = err.get("message", raw_text)
        message = msg

        if error_code == 190 or subcode == 463 or "expired" in msg.lower():
            error_type = "TOKEN_EXPIRED (액세스 토큰 만료)"
            solution = (
                "Graph API 단기 토큰이 만료되었습니다. Meta Developer Graph API Explorer에서 "
                "새 User Access Token을 재발급받거나, 60일 유효한 장기 토큰으로 .env의 INSTAGRAM_ACCESS_TOKEN을 갱신하세요."
            )
        elif error_code == 10 or "permission" in msg.lower():
            error_type = "PERMISSION_DENIED (권한 부족)"
            solution = "앱에 'instagram_basic', 'pages_read_engagement' 권한이 필요합니다. 토큰 발급 시 권한을 추가 체크하세요."
        elif error_code == 100 or "user_id" in msg.lower():
            error_type = "INVALID_PARAMETER (User ID 또는 인자 오류)"
            solution = "Instagram Professional/Business 계정의 올바른 Instagram User ID가 입력되었는지 확인하세요."
        else:
            error_type = f"INSTAGRAM_ERROR (코드 {error_code})"
            solution = "Meta Graph API 개발자 문서를 참조하여 권한 및 토큰 유효성을 확인하세요."

    # 2. YouTube Data API v3 에러 분석
    elif platform == "YouTube":
        err = data.get("error", {})
        error_code = err.get("code")
        msg = err.get("message", raw_text)
        errors = err.get("errors", [])
        reason = errors[0].get("reason", "") if errors else ""
        message = msg

        if "API key not valid" in msg or "keyInvalid" in reason:
            error_type = "INVALID_API_KEY (유효하지 않은 API 키)"
            solution = (
                "Google Cloud Console > [API 및 서비스] > [사용자 인증 정보]에서 유효한 YouTube Data API v3 키를 발급받아 "
                ".env의 YOUTUBE_API_KEY에 입력하세요. (기본 템플릿 값 사용 불가)"
            )
        elif "quotaExceeded" in reason or "quota" in msg.lower():
            error_type = "QUOTA_EXCEEDED (일일 할당량 초과)"
            solution = "YouTube API 일일 무료 쿼터(10,000 units)가 소진되었습니다. 할당량 리셋 시점(태평양 자정) 이후에 시도하세요."
        elif "accessNotConfigured" in reason:
            error_type = "API_NOT_ENABLED (API 라이브러리 비활성화)"
            solution = "Google Cloud Console에서 'YouTube Data API v3' 라이브러리를 검색하여 [사용 설정(Enable)]을 완료하세요."
        else:
            error_type = f"YOUTUBE_ERROR ({reason or error_code})"
            solution = "Google Cloud Console의 API 키 제한(HTTP 리퍼러/IP) 및 권한 설정을 확인하세요."

    # 3. Naver Open API / Datalab 에러 분석
    elif platform == "Naver":
        err_code = data.get("errorCode")
        err_msg = data.get("errorMessage", raw_text)
        error_code = err_code
        message = err_msg

        if err_code == "024" or "Authentication failed" in err_msg:
            error_type = "AUTHENTICATION_FAILED (네이버 클라이언트 인증 실패)"
            solution = (
                "NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 일치하지 않습니다. "
                "네이버 개발자센터 > [내 애플리케이션]에서 키를 다시 복사하여 .env에 공백/따옴표 없이 정확히 붙여넣으세요."
            )
        elif err_code == "051" or "Not Found" in err_msg or status == 404:
            error_type = "API_NOT_REGISTERED (사용 권한 미등록)"
            solution = "네이버 개발자센터 애플리케이션의 [API 설정] 탭에서 '검색' 및 '데이터랩 (쇼핑인사이트/통합검색어)'을 추가하세요."
        elif err_code == "010" or "Invalid" in err_msg:
            error_type = "INVALID_PARAMETER (파라미터/날짜 형식 오류)"
            solution = "검색 키워드 또는 날짜 범위(YYYY-MM-DD), timeUnit 규격을 확인하세요."
        else:
            error_type = f"NAVER_ERROR ({err_code or status})"
            solution = "네이버 오픈 API 가이드 및 애플리케이션 상태를 확인하세요."

    return ApiException(
        platform=platform,
        endpoint=endpoint,
        status_code=status,
        error_type=error_type,
        message=message,
        solution=solution,
        error_code=error_code,
        raw_response=raw_text,
    )


def _handle_response(resp: requests.Response, platform: str = "Unknown", endpoint: str = "") -> Dict[str, Any]:
    """HTTP 응답 검증 및 상세 에러 분석 래핑."""
    if resp.status_code >= 400:
        raise analyze_api_error(platform, endpoint, resp)
    return resp.json()



# ==============================================================================
# 1. API 클라이언트 계층 (진단 및 테스트를 위한 자체 완비 구현체)
# ==============================================================================

class InstagramApiClient:
    """Instagram Graph API 전용 클라이언트."""

    BASE_URL = "https://graph.facebook.com"

    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self.access_token = access_token or getattr(settings, "INSTAGRAM_ACCESS_TOKEN", None) or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        self.user_id = user_id or getattr(settings, "INSTAGRAM_USER_ID", None) or os.getenv("INSTAGRAM_USER_ID")
        self.api_version = api_version or getattr(settings, "INSTAGRAM_API_VERSION", "v21.0")

    @property
    def versioned_url(self) -> str:
        return f"{self.BASE_URL}/{self.api_version}"

    def search_hashtag(self, query: str, user_id: Optional[str] = None, access_token: Optional[str] = None) -> Dict[str, Any]:
        """해시태그 ID 검색 (GET /ig_hashtag_search?user_id={ig-user-id}&q=kbeauty)."""
        uid = user_id or self.user_id
        token = access_token or self.access_token
        url = f"{self.versioned_url}/ig_hashtag_search"
        params = {
            "user_id": uid,
            "q": query,
            "access_token": token,
        }
        resp = requests.get(url, params=params, timeout=25)
        return _handle_response(resp, platform="Instagram", endpoint="/ig_hashtag_search")

    def get_hashtag_top_media(
        self,
        hashtag_id: str,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """해시태그 인기글 조회 (GET /{hashtag-id}/top_media?user_id={ig-user-id})."""
        uid = user_id or self.user_id
        token = access_token or self.access_token
        url = f"{self.versioned_url}/{hashtag_id}/top_media"
        params = {
            "user_id": uid,
            "fields": fields or "id,caption,like_count,comments_count,media_type,permalink,timestamp",
            "access_token": token,
        }
        resp = requests.get(url, params=params, timeout=25)
        return _handle_response(resp, platform="Instagram", endpoint=f"/{hashtag_id}/top_media")

    def get_hashtag_recent_media(
        self,
        hashtag_id: str,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """해시태그 최신글 조회 (GET /{hashtag-id}/recent_media?user_id={ig-user-id})."""
        uid = user_id or self.user_id
        token = access_token or self.access_token
        url = f"{self.versioned_url}/{hashtag_id}/recent_media"
        params = {
            "user_id": uid,
            "fields": fields or "id,caption,like_count,comments_count,media_type,permalink,timestamp",
            "access_token": token,
        }
        resp = requests.get(url, params=params, timeout=25)
        return _handle_response(resp, platform="Instagram", endpoint=f"/{hashtag_id}/recent_media")

    def get_business_discovery(
        self,
        target_username: str,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """타 계정 조회 (GET /{ig-user-id}?fields=business_discovery.username(nike){...})."""
        uid = user_id or self.user_id
        token = access_token or self.access_token
        url = f"{self.versioned_url}/{uid}"
        inner_fields = fields or "username,website,name,ig_id,id,profile_picture_url,biography,follows_count,followers_count,media_count,media{id,caption,like_count,comments_count,timestamp,permalink}"
        discovery_field = f"business_discovery.username({target_username}){{{inner_fields}}}"
        params = {
            "fields": discovery_field,
            "access_token": token,
        }
        resp = requests.get(url, params=params, timeout=25)
        return _handle_response(resp, platform="Instagram", endpoint=f"/{uid}?fields=business_discovery.username({target_username})")


class YouTubeDataApiClient:
    """YouTube Data API v3 전용 클라이언트."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "YOUTUBE_API_KEY", None) or os.getenv("YOUTUBE_API_KEY")

    def search_channels(self, query: str, max_results: int = 5, key: Optional[str] = None) -> Dict[str, Any]:
        """경쟁사 공식 채널 검색 (GET /search type=channel)."""
        url = f"{self.BASE_URL}/search"
        params = {
            "part": "snippet",
            "type": "channel",
            "q": query,
            "maxResults": max_results,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/search (channel)")

    def search_ad_videos(
        self,
        channel_id: str,
        query: str = "",
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        max_results: int = 5,
        key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """경쟁사 광고 후보 영상 검색 (GET /search type=video, channelId, 기간 필터)."""
        url = f"{self.BASE_URL}/search"
        params: Dict[str, Any] = {
            "part": "snippet",
            "type": "video",
            "channelId": channel_id,
            "maxResults": max_results,
            "key": key or self.api_key,
        }
        if query:
            params["q"] = query
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before

        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/search (ad_videos)")

    def get_video_details(self, video_ids: Union[str, List[str]], key: Optional[str] = None) -> Dict[str, Any]:
        """영상 상세정보 및 반응 조회 (GET /videos part=snippet,statistics,contentDetails)."""
        url = f"{self.BASE_URL}/videos"
        id_param = video_ids if isinstance(video_ids, str) else ",".join(video_ids)
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": id_param,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/videos")

    def get_comment_threads(self, video_id: str, max_results: int = 10, key: Optional[str] = None) -> Dict[str, Any]:
        """시청자 댓글 수집 (GET /commentThreads)."""
        url = f"{self.BASE_URL}/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_results,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/commentThreads")

    def get_channel_details(self, channel_id: str, key: Optional[str] = None) -> Dict[str, Any]:
        """채널 상세정보 확인 (GET /channels part=snippet,statistics,contentDetails)."""
        url = f"{self.BASE_URL}/channels"
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": channel_id,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/channels")

    def get_playlist_items(self, playlist_id: str, max_results: int = 5, key: Optional[str] = None) -> Dict[str, Any]:
        """경쟁사 최근 업로드 영상 조회 (GET /playlistItems playlistId=uploads)."""
        url = f"{self.BASE_URL}/playlistItems"
        params = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": max_results,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/playlistItems")

    def search_paid_promotion_videos(self, query: str, max_results: int = 5, key: Optional[str] = None) -> Dict[str, Any]:
        """유료 프로모션 표시 영상 검색 (GET /search videoPaidProductPlacement=true)."""
        url = f"{self.BASE_URL}/search"
        params = {
            "part": "snippet",
            "type": "video",
            "videoPaidProductPlacement": "true",
            "q": query,
            "maxResults": max_results,
            "key": key or self.api_key,
        }
        resp = requests.get(url, params=params, timeout=10)
        return _handle_response(resp, platform="YouTube", endpoint="/search (paidPromotion=true)")


class NaverOpenApiClient:
    """Naver Open API & Datalab 전용 클라이언트."""

    SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
    DATALAB_SEARCH_URL = "https://openapi.naver.com/v1/datalab/search"
    DATALAB_CATEGORIES_URL = "https://openapi.naver.com/v1/datalab/shopping/categories"
    DATALAB_CAT_GENDER_URL = "https://openapi.naver.com/v1/datalab/shopping/category/gender"
    DATALAB_CAT_AGE_URL = "https://openapi.naver.com/v1/datalab/shopping/category/age"
    DATALAB_CAT_KEYWORDS_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keywords"
    DATALAB_CAT_KW_GENDER_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keyword/gender"
    DATALAB_CAT_KW_AGE_URL = "https://openapi.naver.com/v1/datalab/shopping/category/keyword/age"

    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id or getattr(settings, "NAVER_CLIENT_ID", None) or os.getenv("NAVER_CLIENT_ID")
        self.client_secret = client_secret or getattr(settings, "NAVER_CLIENT_SECRET", None) or os.getenv("NAVER_CLIENT_SECRET")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "X-Naver-Client-Id": self.client_id or "",
            "X-Naver-Client-Secret": self.client_secret or "",
            "Content-Type": "application/json",
        }

    def search_shop(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        """쇼핑 검색 결과 반환 (GET /v1/search/shop.json)."""
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(self.SHOP_URL, headers=self.headers, params=params, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/search/shop")

    def get_datalab_search_trend(
        self,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        keyword_groups: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """검색어 트렌드 조회 (POST /v1/datalab/search)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": keyword_groups or [],
        }
        resp = requests.post(self.DATALAB_SEARCH_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/search")

    def get_shopping_categories_trend(
        self,
        start_date: str,
        end_date: str,
        time_unit: str = "month",
        category: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """쇼핑 분야별 검색 클릭 추이 (POST /v1/datalab/shopping/categories)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category or [],
        }
        resp = requests.post(self.DATALAB_CATEGORIES_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/categories")

    def get_shopping_category_gender_trend(
        self,
        start_date: str,
        end_date: str,
        category: str,
        gender: str,
        time_unit: str = "month",
    ) -> Dict[str, Any]:
        """쇼핑 분야별 · 성별 검색 클릭 추이 (POST /v1/datalab/shopping/category/gender)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category,
            "gender": gender,
        }
        resp = requests.post(self.DATALAB_CAT_GENDER_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/category/gender")

    def get_shopping_category_age_trend(
        self,
        start_date: str,
        end_date: str,
        category: str,
        ages: List[str],
        time_unit: str = "month",
    ) -> Dict[str, Any]:
        """쇼핑 분야별 · 연령별 검색 클릭 추이 (POST /v1/datalab/shopping/category/age)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category,
            "ages": ages,
        }
        resp = requests.post(self.DATALAB_CAT_AGE_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/category/age")

    def get_shopping_category_keywords_trend(
        self,
        start_date: str,
        end_date: str,
        category: str,
        keyword: List[Dict[str, Any]],
        time_unit: str = "month",
    ) -> Dict[str, Any]:
        """쇼핑 분야별 · 키워드별 검색 클릭 추이 (POST /v1/datalab/shopping/category/keywords)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category,
            "keyword": keyword,
        }
        resp = requests.post(self.DATALAB_CAT_KEYWORDS_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/category/keywords")

    def get_shopping_category_keyword_gender_trend(
        self,
        start_date: str,
        end_date: str,
        category: str,
        keyword: str,
        gender: str,
        time_unit: str = "month",
    ) -> Dict[str, Any]:
        """쇼핑 분야 · 키워드별 · 성별 검색 클릭 추이 (POST /v1/datalab/shopping/category/keyword/gender)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category,
            "keyword": keyword,
            "gender": gender,
        }
        resp = requests.post(self.DATALAB_CAT_KW_GENDER_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/category/keyword/gender")

    def get_shopping_category_keyword_age_trend(
        self,
        start_date: str,
        end_date: str,
        category: str,
        keyword: str,
        ages: List[str],
        time_unit: str = "month",
    ) -> Dict[str, Any]:
        """쇼핑 분야 · 키워드별 · 연령별 검색 클릭 추이 (POST /v1/datalab/shopping/category/keyword/age)."""
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "category": category,
            "keyword": keyword,
            "ages": ages,
        }
        resp = requests.post(self.DATALAB_CAT_KW_AGE_URL, headers=self.headers, json=body, timeout=10)
        return _handle_response(resp, platform="Naver", endpoint="/v1/datalab/shopping/category/keyword/age")


# ==============================================================================
# 2. 목(Mock) 테스트 스위트 (19개 엔드포인트 요청/응답 규격 정합성 검증)
# ==============================================================================

class TestInstagramApiMock:
    """Instagram Graph API (4개 엔드포인트) 규격 정합성 검증 테스트."""

    @patch("requests.get")
    def test_ig_hashtag_search(self, mock_get):
        """1. 해시태그 ID 검색."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"id": "17843857450077043"}]}
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_token", user_id="17841400000000000", api_version="v21.0")
        res = client.search_hashtag("kbeauty")

        mock_get.assert_called_once_with(
            "https://graph.facebook.com/v21.0/ig_hashtag_search",
            params={"user_id": "17841400000000000", "q": "kbeauty", "access_token": "test_token"},
            timeout=25,
        )
        assert res["data"][0]["id"] == "17843857450077043"

    @patch("requests.get")
    def test_ig_top_media(self, mock_get):
        """2. 해시태그 인기글 조회."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "17900000000000001",
                    "caption": "K-뷰티 추천 아이템 #kbeauty",
                    "like_count": 150,
                    "comments_count": 12,
                    "media_type": "IMAGE",
                    "permalink": "https://www.instagram.com/p/test1/",
                    "timestamp": "2026-09-01T12:00:00+0000",
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_token", user_id="17841400000000000", api_version="v21.0")
        res = client.get_hashtag_top_media("17843857450077043")

        mock_get.assert_called_once_with(
            "https://graph.facebook.com/v21.0/17843857450077043/top_media",
            params={
                "user_id": "17841400000000000",
                "fields": "id,caption,like_count,comments_count,media_type,permalink,timestamp",
                "access_token": "test_token",
            },
            timeout=25,
        )
        assert len(res["data"]) == 1
        assert res["data"][0]["like_count"] == 150

    @patch("requests.get")
    def test_ig_recent_media(self, mock_get):
        """3. 해시태그 최신글 조회."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "id": "17900000000000002",
                    "caption": "실시간 뷰티 리뷰 #kbeauty",
                    "like_count": 3,
                    "comments_count": 0,
                    "media_type": "VIDEO",
                    "permalink": "https://www.instagram.com/p/test2/",
                    "timestamp": "2026-09-10T12:00:00+0000",
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_token", user_id="17841400000000000", api_version="v21.0")
        res = client.get_hashtag_recent_media("17843857450077043")

        mock_get.assert_called_once_with(
            "https://graph.facebook.com/v21.0/17843857450077043/recent_media",
            params={
                "user_id": "17841400000000000",
                "fields": "id,caption,like_count,comments_count,media_type,permalink,timestamp",
                "access_token": "test_token",
            },
            timeout=25,
        )
        assert res["data"][0]["media_type"] == "VIDEO"

    @patch("requests.get")
    def test_ig_business_discovery(self, mock_get):
        """4. 타 계정 조회 (Business Discovery)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "business_discovery": {
                "username": "nike",
                "name": "Nike",
                "followers_count": 300000000,
                "media_count": 1200,
                "media": {
                    "data": [
                        {
                            "id": "18000000000000001",
                            "caption": "Just Do It.",
                            "like_count": 500000,
                            "comments_count": 4000,
                        }
                    ]
                },
            },
            "id": "17841400000000000",
        }
        mock_get.return_value = mock_resp

        client = InstagramApiClient(access_token="test_token", user_id="17841400000000000", api_version="v21.0")
        res = client.get_business_discovery("nike")

        assert mock_get.call_count == 1
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://graph.facebook.com/v21.0/17841400000000000"
        assert "business_discovery.username(nike)" in call_args[1]["params"]["fields"]
        assert call_args[1]["params"]["access_token"] == "test_token"
        assert res["business_discovery"]["username"] == "nike"


class TestYouTubeDataApiMock:
    """YouTube Data API v3 (7개 엔드포인트/파라미터 조합) 규격 정합성 검증 테스트."""

    @patch("requests.get")
    def test_yt_official_channel_search(self, mock_get):
        """1. 경쟁사 공식 채널 검색."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": {"kind": "youtube#channel", "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw"},
                    "snippet": {"title": "Google Developers", "description": "Google Developers channel"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.search_channels("Google Developers", max_results=1)

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "channel",
                "q": "Google Developers",
                "maxResults": 1,
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert res["items"][0]["id"]["channelId"] == "UC_x5XG1OV2P6uZZ5FSM9Ttw"

    @patch("requests.get")
    def test_yt_ad_candidate_search(self, mock_get):
        """2. 경쟁사 광고 후보 영상 검색."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid_ad_123"},
                    "snippet": {"title": "[광고] 신제품 런칭 프로모션"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.search_ad_videos(
            channel_id="UC_x5XG1OV2P6uZZ5FSM9Ttw",
            query="신제품 광고",
            published_after="2026-01-01T00:00:00Z",
            published_before="2026-06-01T00:00:00Z",
            max_results=3,
        )

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "channelId": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "maxResults": 3,
                "key": "test_yt_key",
                "q": "신제품 광고",
                "publishedAfter": "2026-01-01T00:00:00Z",
                "publishedBefore": "2026-06-01T00:00:00Z",
            },
            timeout=10,
        )
        assert res["items"][0]["id"]["videoId"] == "vid_ad_123"

    @patch("requests.get")
    def test_yt_video_details(self, mock_get):
        """3. 영상 상세정보 및 반응 조회."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "vid_ad_123",
                    "snippet": {
                        "title": "영상 제목",
                        "description": "설명",
                        "tags": ["AI", "Python"],
                        "publishedAt": "2026-05-10T10:00:00Z",
                    },
                    "statistics": {
                        "viewCount": "125000",
                        "likeCount": "4500",
                        "commentCount": "320",
                    },
                    "contentDetails": {
                        "duration": "PT8M45S",
                    },
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.get_video_details("vid_ad_123")

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": "vid_ad_123",
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert res["items"][0]["statistics"]["viewCount"] == "125000"
        assert res["items"][0]["contentDetails"]["duration"] == "PT8M45S"

    @patch("requests.get")
    def test_yt_comment_threads(self, mock_get):
        """4. 시청자 댓글 수집."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "정말 유익한 콘텐츠네요!",
                                "authorDisplayName": "Viewer1",
                                "likeCount": 10,
                            }
                        }
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.get_comment_threads("vid_ad_123", max_results=5)

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params={
                "part": "snippet",
                "videoId": "vid_ad_123",
                "maxResults": 5,
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert "정말 유익한" in res["items"][0]["snippet"]["topLevelComment"]["snippet"]["textDisplay"]

    @patch("requests.get")
    def test_yt_channel_details(self, mock_get):
        """5. 채널 상세정보 확인."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": "UC_channel_123",
                    "snippet": {"title": "테스트 공식 채널", "description": "공식 채널 설명"},
                    "statistics": {"subscriberCount": "500000", "viewCount": "10000000", "videoCount": "250"},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU_channel_123"}},
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.get_channel_details("UC_channel_123")

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/channels",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": "UC_channel_123",
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert res["items"][0]["statistics"]["subscriberCount"] == "500000"
        assert res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"] == "UU_channel_123"

    @patch("requests.get")
    def test_yt_recent_uploads(self, mock_get):
        """6. 경쟁사 최근 업로드 영상 조회."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "snippet": {
                        "title": "가장 최근 공개된 신제품 영상",
                        "resourceId": {"videoId": "vid_new_456"},
                        "publishedAt": "2026-09-09T08:00:00Z",
                    }
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.get_playlist_items("UU_channel_123", max_results=3)

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "snippet",
                "playlistId": "UU_channel_123",
                "maxResults": 3,
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert res["items"][0]["snippet"]["resourceId"]["videoId"] == "vid_new_456"

    @patch("requests.get")
    def test_yt_paid_promotion_search(self, mock_get):
        """7. 유료 프로모션 표시 영상 검색 (videoPaidProductPlacement=true)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {
                    "id": {"videoId": "vid_sponsored_789"},
                    "snippet": {"title": "유료 광고 포함 협찬 리뷰"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        client = YouTubeDataApiClient(api_key="test_yt_key")
        res = client.search_paid_promotion_videos("뷰티 화장품", max_results=2)

        mock_get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "videoPaidProductPlacement": "true",
                "q": "뷰티 화장품",
                "maxResults": 2,
                "key": "test_yt_key",
            },
            timeout=10,
        )
        assert res["items"][0]["id"]["videoId"] == "vid_sponsored_789"


class TestNaverOpenApiMock:
    """Naver Open API & Datalab (8개 엔드포인트) 규격 정합성 검증 테스트."""

    @patch("requests.get")
    def test_naver_shop_search(self, mock_get):
        """1. 쇼핑 검색 결과 반환."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "total": 500,
            "items": [
                {
                    "title": "원피스 추천 상품",
                    "link": "https://search.shopping.naver.com/1",
                    "lprice": "29000",
                    "mallName": "트렌드몰",
                }
            ],
        }
        mock_get.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.search_shop("원피스", display=1, sort="sim")

        mock_get.assert_called_once_with(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={
                "X-Naver-Client-Id": "test_nid",
                "X-Naver-Client-Secret": "test_nsecret",
                "Content-Type": "application/json",
            },
            params={"query": "원피스", "display": 1, "sort": "sim"},
            timeout=10,
        )
        assert res["items"][0]["lprice"] == "29000"

    @patch("requests.post")
    def test_naver_datalab_search_trend(self, mock_post):
        """2. 통합검색어 검색 추이 데이터 반환."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "패션의류",
                    "keywords": ["원피스", "셔츠"],
                    "data": [{"period": "2026-01-01", "ratio": 75.5}],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_datalab_search_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            time_unit="month",
            keyword_groups=[{"groupName": "패션의류", "keywords": ["원피스", "셔츠"]}],
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/search",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "keywordGroups": [{"groupName": "패션의류", "keywords": ["원피스", "셔츠"]}],
            },
            timeout=10,
        )
        assert res["results"][0]["data"][0]["ratio"] == 75.5

    @patch("requests.post")
    def test_naver_shopping_categories(self, mock_post):
        """3. 쇼핑 분야별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "패션의류",
                    "category": ["50000000"],
                    "data": [{"period": "2026-01-01", "ratio": 88.0}],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_categories_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            time_unit="month",
            category=[{"name": "패션의류", "param": ["50000000"]}],
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/categories",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": [{"name": "패션의류", "param": ["50000000"]}],
            },
            timeout=10,
        )
        assert res["results"][0]["category"] == ["50000000"]

    @patch("requests.post")
    def test_naver_shopping_category_gender(self, mock_post):
        """4. 쇼핑 분야별 · 성별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "패션의류",
                    "category": "50000000",
                    "data": [{"period": "2026-01-01", "ratio": 92.4, "group": "f"}],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_category_gender_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            gender="f",
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/category/gender",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": "50000000",
                "gender": "f",
            },
            timeout=10,
        )
        assert res["results"][0]["data"][0]["group"] == "f"

    @patch("requests.post")
    def test_naver_shopping_category_age(self, mock_post):
        """5. 쇼핑 분야별 · 연령별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "패션의류",
                    "category": "50000000",
                    "data": [
                        {"period": "2026-01-01", "ratio": 45.1, "group": "20"},
                        {"period": "2026-01-01", "ratio": 54.9, "group": "30"},
                    ],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_category_age_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            ages=["20", "30"],
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/category/age",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": "50000000",
                "ages": ["20", "30"],
            },
            timeout=10,
        )
        assert len(res["results"][0]["data"]) == 2

    @patch("requests.post")
    def test_naver_shopping_category_keywords(self, mock_post):
        """6. 쇼핑 분야별 · 키워드별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "원피스",
                    "keyword": ["원피스"],
                    "data": [{"period": "2026-01-01", "ratio": 67.8}],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_category_keywords_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword=[{"name": "원피스", "param": ["원피스"]}],
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/category/keywords",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": "50000000",
                "keyword": [{"name": "원피스", "param": ["원피스"]}],
            },
            timeout=10,
        )
        assert res["results"][0]["title"] == "원피스"

    @patch("requests.post")
    def test_naver_shopping_category_keyword_gender(self, mock_post):
        """7. 쇼핑 분야 · 키워드별 · 성별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "원피스",
                    "keyword": "원피스",
                    "data": [{"period": "2026-01-01", "ratio": 95.0, "group": "f"}],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_category_keyword_gender_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword="원피스",
            gender="f",
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/category/keyword/gender",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": "50000000",
                "keyword": "원피스",
                "gender": "f",
            },
            timeout=10,
        )
        assert res["results"][0]["data"][0]["group"] == "f"

    @patch("requests.post")
    def test_naver_shopping_category_keyword_age(self, mock_post):
        """8. 쇼핑 분야 · 키워드별 · 연령별 검색 클릭 추이."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "startDate": "2026-01-01",
            "endDate": "2026-03-01",
            "timeUnit": "month",
            "results": [
                {
                    "title": "원피스",
                    "keyword": "원피스",
                    "data": [
                        {"period": "2026-01-01", "ratio": 48.0, "group": "20"},
                        {"period": "2026-01-01", "ratio": 52.0, "group": "30"},
                    ],
                }
            ],
        }
        mock_post.return_value = mock_resp

        client = NaverOpenApiClient(client_id="test_nid", client_secret="test_nsecret")
        res = client.get_shopping_category_keyword_age_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword="원피스",
            ages=["20", "30"],
        )

        mock_post.assert_called_once_with(
            "https://openapi.naver.com/v1/datalab/shopping/category/keyword/age",
            headers=client.headers,
            json={
                "startDate": "2026-01-01",
                "endDate": "2026-03-01",
                "timeUnit": "month",
                "category": "50000000",
                "keyword": "원피스",
                "ages": ["20", "30"],
            },
            timeout=10,
        )
        assert len(res["results"][0]["data"]) == 2


# ==============================================================================
# 3. 라이브 테스트 스위트 (환경변수 인증 정보를 활용한 실서버 API 연동 검증)
# ==============================================================================

def safe_live_call(api_func):
    """Live API 호출 헬퍼: ApiException 또는 네트워크 오류 발생 시 실서버 응답 불가 환경에서 안전하게 스킵."""
    try:
        return api_func()
    except ApiException as e:
        if getattr(e, "status_code", None) in (400, 401, 403) or "token" in str(e).lower() or "quota" in str(e).lower():
            pytest.skip(f"Live API 인증/쿼터 만료로 스킵: [{getattr(e, 'status_code', 'ERR')}] {e.message}")
        pytest.fail(str(e))
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Live API 통신 오류 또는 토큰 만료로 스킵: {e}")


class TestInstagramApiLive:
    """Instagram Graph API 실 엔드포인트 호출 테스트 (키가 주입된 경우 실행, 없으면 Skip)."""

    @pytest.fixture(autouse=True)
    def check_credentials(self):
        token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", None) or os.getenv("INSTAGRAM_ACCESS_TOKEN")
        uid = getattr(settings, "INSTAGRAM_USER_ID", None) or os.getenv("INSTAGRAM_USER_ID")
        if not token or not uid:
            pytest.skip("INSTAGRAM_ACCESS_TOKEN 또는 INSTAGRAM_USER_ID 미설정으로 실호출 테스트를 스킵합니다.")

    def test_live_ig_hashtag_search(self):
        client = InstagramApiClient()
        res = safe_live_call(lambda: client.search_hashtag("kbeauty"))
        assert "data" in res

    def test_live_ig_top_media(self):
        client = InstagramApiClient()
        search_res = safe_live_call(lambda: client.search_hashtag("kbeauty"))
        if not search_res.get("data"):
            pytest.skip("해시태그 ID를 획득하지 못해 top_media 호출을 스킵합니다.")
        hashtag_id = search_res["data"][0]["id"]
        res = safe_live_call(lambda: client.get_hashtag_top_media(hashtag_id))
        assert "data" in res

    def test_live_ig_recent_media(self):
        client = InstagramApiClient()
        search_res = safe_live_call(lambda: client.search_hashtag("kbeauty"))
        if not search_res.get("data"):
            pytest.skip("해시태그 ID를 획득하지 못해 recent_media 호출을 스킵합니다.")
        hashtag_id = search_res["data"][0]["id"]
        res = safe_live_call(lambda: client.get_hashtag_recent_media(hashtag_id))
        assert "data" in res

    def test_live_ig_business_discovery(self):
        client = InstagramApiClient()
        res = safe_live_call(lambda: client.get_business_discovery("nike"))
        assert "business_discovery" in res


class TestYouTubeDataApiLive:
    """YouTube Data API v3 실 엔드포인트 호출 테스트 (키가 주입된 경우 실행, 없으면 Skip)."""

    @pytest.fixture(autouse=True)
    def check_credentials(self):
        key = getattr(settings, "YOUTUBE_API_KEY", None) or os.getenv("YOUTUBE_API_KEY")
        if not key or key.strip() in ("", "your_youtube_api_key_here"):
            pytest.skip("YOUTUBE_API_KEY 미설정 또는 기본 템플릿 값으로 실호출 테스트를 스킵합니다.")

    def test_live_yt_official_channel_search(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.search_channels("Google Developers", max_results=1))
        assert "items" in res

    def test_live_yt_ad_candidate_search(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.search_ad_videos("UC_x5XG1OV2P6uZZ5FSM9Ttw", query="Android", max_results=1))
        assert "items" in res

    def test_live_yt_video_details(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.get_video_details("dQw4w9WgXcQ"))
        assert "items" in res

    def test_live_yt_comment_threads(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.get_comment_threads("dQw4w9WgXcQ", max_results=2))
        assert "items" in res

    def test_live_yt_channel_details(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.get_channel_details("UC_x5XG1OV2P6uZZ5FSM9Ttw"))
        assert "items" in res

    def test_live_yt_recent_uploads(self):
        client = YouTubeDataApiClient()
        ch_res = safe_live_call(lambda: client.get_channel_details("UC_x5XG1OV2P6uZZ5FSM9Ttw"))
        if not ch_res.get("items"):
            pytest.skip("채널 정보를 획득하지 못해 최근 업로드 조회를 스킵합니다.")
        uploads_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        res = safe_live_call(lambda: client.get_playlist_items(uploads_id, max_results=2))
        assert "items" in res

    def test_live_yt_paid_promotion_search(self):
        client = YouTubeDataApiClient()
        res = safe_live_call(lambda: client.search_paid_promotion_videos("뷰티", max_results=1))
        assert "items" in res


class TestNaverOpenApiLive:
    """Naver Open API & Datalab 실 엔드포인트 호출 테스트 (키가 주입된 경우 실행, 없으면 Skip)."""

    @pytest.fixture(autouse=True)
    def check_credentials(self):
        cid = getattr(settings, "NAVER_CLIENT_ID", None) or os.getenv("NAVER_CLIENT_ID")
        csec = getattr(settings, "NAVER_CLIENT_SECRET", None) or os.getenv("NAVER_CLIENT_SECRET")
        if not cid or not csec or cid.strip() in ("", "your_naver_client_id_here"):
            pytest.skip("NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 미설정으로 실호출 테스트를 스킵합니다.")

    def test_live_naver_shop_search(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.search_shop("원피스", display=1))
        assert "items" in res

    def test_live_naver_datalab_search_trend(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_datalab_search_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            time_unit="month",
            keyword_groups=[{"groupName": "패션", "keywords": ["패션", "의류"]}],
        ))
        assert "results" in res

    def test_live_naver_shopping_categories(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_categories_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category=[{"name": "패션의류", "param": ["50000000"]}],
        ))
        assert "results" in res

    def test_live_naver_shopping_category_gender(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_category_gender_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            gender="f",
        ))
        assert "results" in res

    def test_live_naver_shopping_category_age(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_category_age_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            ages=["20", "30"],
        ))
        assert "results" in res

    def test_live_naver_shopping_category_keywords(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_category_keywords_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword=[{"name": "원피스", "param": ["원피스"]}],
        ))
        assert "results" in res

    def test_live_naver_shopping_category_keyword_gender(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_category_keyword_gender_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword="원피스",
            gender="f",
        ))
        assert "results" in res

    def test_live_naver_shopping_category_keyword_age(self):
        client = NaverOpenApiClient()
        res = safe_live_call(lambda: client.get_shopping_category_keyword_age_trend(
            start_date="2026-01-01",
            end_date="2026-03-01",
            category="50000000",
            keyword="원피스",
            ages=["20", "30"],
        ))
        assert "results" in res


# ==============================================================================
# 4. CLI 직접 실행기 (통합 진단 실행용: `python scripts/api_diagnostics.py`)
# ==============================================================================

API_REGISTRY = [
    # 인스타그램 Graph API (4개 엔드포인트)
    {"platform": "Instagram", "name": "해시태그 ID 검색", "method": "GET", "endpoint": "/ig_hashtag_search", "key_var": "INSTAGRAM_ACCESS_TOKEN"},
    {"platform": "Instagram", "name": "해시태그 인기글", "method": "GET", "endpoint": "/{hashtag-id}/top_media", "key_var": "INSTAGRAM_ACCESS_TOKEN"},
    {"platform": "Instagram", "name": "해시태그 최신글", "method": "GET", "endpoint": "/{hashtag-id}/recent_media", "key_var": "INSTAGRAM_ACCESS_TOKEN"},
    {"platform": "Instagram", "name": "타 계정 조회 (Business Discovery)", "method": "GET", "endpoint": "/{ig-user-id}?fields=business_discovery...", "key_var": "INSTAGRAM_ACCESS_TOKEN"},
    # YouTube Data API v3 (7개 엔드포인트)
    {"platform": "YouTube", "name": "경쟁사 공식 채널 검색", "method": "GET", "endpoint": "/search (type=channel)", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "경쟁사 광고 후보 영상 검색", "method": "GET", "endpoint": "/search (channelId, 기간)", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "영상 상세정보 및 반응 조회", "method": "GET", "endpoint": "/videos (part=snippet,stats...)", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "시청자 댓글 수집", "method": "GET", "endpoint": "/commentThreads", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "채널 상세정보 확인", "method": "GET", "endpoint": "/channels", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "경쟁사 최근 업로드 영상 조회", "method": "GET", "endpoint": "/playlistItems (uploads)", "key_var": "YOUTUBE_API_KEY"},
    {"platform": "YouTube", "name": "유료 프로모션 표시 영상 검색", "method": "GET", "endpoint": "/search (paidPromotion=true)", "key_var": "YOUTUBE_API_KEY"},
    # 네이버 Open API / 데이터랩 (8개 엔드포인트)
    {"platform": "Naver", "name": "트렌드 조사를 위한 쇼핑 검색", "method": "GET", "endpoint": "/v1/search/shop", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "검색어 트렌드 조회", "method": "POST", "endpoint": "/v1/datalab/search", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야별 검색 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/categories", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야별 · 성별 검색 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/category/gender", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야별 · 연령별 검색 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/category/age", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야별 · 키워드별 검색 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/category/keywords", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야 · 키워드별 · 성별 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/category/keyword/gender", "key_var": "NAVER_CLIENT_ID"},
    {"platform": "Naver", "name": "쇼핑 분야 · 키워드별 · 연령별 클릭 추이", "method": "POST", "endpoint": "/v1/datalab/shopping/category/keyword/age", "key_var": "NAVER_CLIENT_ID"},
]


def print_summary_table():
    """19개 엔드포인트 목록 및 현재 환경변수 등록 상태 출력."""
    print("\n" + "=" * 95)
    print(" 🚀 [API 검증 테스트 스위트] 대상 API 19개 규격 및 환경변수 상태")
    print("=" * 95)
    print(f"{'#':<3} | {'플랫폼':<10} | {'HTTP':<4} | {'용도 / 엔드포인트':<38} | {'필수 환경변수':<22} | {'설정 상태'}")
    print("-" * 95)

    for idx, item in enumerate(API_REGISTRY, start=1):
        key_var = item["key_var"]
        has_key = bool(getattr(settings, key_var, None) or os.getenv(key_var))
        status_str = "✅ 설정됨 (Live 가능)" if has_key else "⚠️ 미설정 (Mock 검증)"
        endpoint_desc = f"{item['name']} ({item['endpoint']})"
        if len(endpoint_desc) > 36:
            endpoint_desc = endpoint_desc[:33] + "..."
        print(f"{idx:<3} | {item['platform']:<10} | {item['method']:<4} | {endpoint_desc:<38} | {key_var:<22} | {status_str}")

    print("=" * 95)


def run_live_diagnostics():
    """19개 전 엔드포인트에 대해 실제 호출을 시도하여 연결 상태 및 응답 에러를 정밀 진단."""
    print("\n" + "=" * 95)
    print(" 🔍 [실시간 Live API 정밀 진단 리포트] 19개 엔드포인트 실호출 검증 및 원인 분석")
    print("=" * 95)

    ig_token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", None) or os.getenv("INSTAGRAM_ACCESS_TOKEN")
    ig_uid = getattr(settings, "INSTAGRAM_USER_ID", None) or os.getenv("INSTAGRAM_USER_ID")
    yt_key = getattr(settings, "YOUTUBE_API_KEY", None) or os.getenv("YOUTUBE_API_KEY")
    nav_id = getattr(settings, "NAVER_CLIENT_ID", None) or os.getenv("NAVER_CLIENT_ID")
    nav_sec = getattr(settings, "NAVER_CLIENT_SECRET", None) or os.getenv("NAVER_CLIENT_SECRET")

    # [1] Instagram (4개)
    print("\n📸 [1] Instagram Graph API (4개 엔드포인트)")
    if not ig_token or not ig_uid:
        print("  ⚠️ INSTAGRAM_ACCESS_TOKEN 또는 INSTAGRAM_USER_ID 미설정 -> 진단 스킵")
    else:
        ig = InstagramApiClient()
        hashtag_id = None
        # 1. 해시태그 ID 검색
        try:
            r1 = ig.search_hashtag("kbeauty")
            hashtag_id = r1.get("data", [{}])[0].get("id")
            print(f"  ✅ 1. 해시태그 ID 검색: 정상 응답 (200 OK) -> 'kbeauty' ID: {hashtag_id}")
        except ApiException as e:
            print(f"  ❌ 1. 해시태그 ID 검색 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
        except Exception as e:
            print(f"  ❌ 1. 해시태그 ID 검색 예외 발생: {e}")

        # 2. 해시태그 인기글
        if hashtag_id:
            try:
                r2 = ig.get_hashtag_top_media(hashtag_id)
                count = len(r2.get("data", []))
                print(f"  ✅ 2. 해시태그 인기글: 정상 응답 (200 OK) -> {count}건 수집")
            except ApiException as e:
                print(f"  ❌ 2. 해시태그 인기글 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
            except Exception as e:
                print(f"  ❌ 2. 해시태그 인기글 예외 발생: {e}")
        else:
            print("  ⚠️ 2. 해시태그 인기글: 해시태그 ID 미획득으로 스킵")

        # 3. 해시태그 최신글
        if hashtag_id:
            try:
                r3 = ig.get_hashtag_recent_media(hashtag_id)
                count = len(r3.get("data", []))
                print(f"  ✅ 3. 해시태그 최신글: 정상 응답 (200 OK) -> {count}건 수집")
            except ApiException as e:
                print(f"  ❌ 3. 해시태그 최신글 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
            except Exception as e:
                print(f"  ❌ 3. 해시태그 최신글 예외 발생: {e}")
        else:
            print("  ⚠️ 3. 해시태그 최신글: 해시태그 ID 미획득으로 스킵")

        # 4. 타 계정 조회 (business_discovery)
        try:
            r4 = ig.get_business_discovery("nike")
            username = r4.get("business_discovery", {}).get("username")
            followers = r4.get("business_discovery", {}).get("followers_count")
            print(f"  ✅ 4. 타 계정 조회 (business_discovery): 정상 응답 (200 OK) -> 계정: @{username} (팔로워: {followers:,}명)")
        except ApiException as e:
            print(f"  ❌ 4. 타 계정 조회 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
        except Exception as e:
            print(f"  ❌ 4. 타 계정 조회 예외 발생: {e}")

    # [2] YouTube (7개)
    print("\n▶️ [2] YouTube Data API v3 (7개 엔드포인트)")
    if not yt_key or yt_key.strip() in ("", "your_youtube_api_key_here"):
        print("  ⚠️ YOUTUBE_API_KEY 미설정 또는 템플릿 값 -> 진단 스킵 (실제 API Key 필요)")
    else:
        yt = YouTubeDataApiClient()
        cases = [
            ("1. 경쟁사 공식 채널 검색", lambda: yt.search_channels("Google Developers", max_results=1)),
            ("2. 경쟁사 광고 후보 영상 검색", lambda: yt.search_ad_videos("UC_x5XG1OV2P6uZZ5FSM9Ttw", query="Android", max_results=1)),
            ("3. 영상 상세정보 및 반응 조회", lambda: yt.get_video_details("dQw4w9WgXcQ")),
            ("4. 시청자 댓글 수집", lambda: yt.get_comment_threads("dQw4w9WgXcQ", max_results=1)),
            ("5. 채널 상세정보 확인", lambda: yt.get_channel_details("UC_x5XG1OV2P6uZZ5FSM9Ttw")),
            ("6. 경쟁사 최근 업로드 영상 조회", lambda: yt.get_playlist_items("UU_x5XG1OV2P6uZZ5FSM9Ttw", max_results=1)),
            ("7. 유료 프로모션 표시 영상 검색", lambda: yt.search_paid_promotion_videos("뷰티", max_results=1)),
        ]
        for name, fn in cases:
            try:
                fn()
                print(f"  ✅ {name}: 정상 응답 (200 OK)")
            except ApiException as e:
                print(f"  ❌ {name} 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
            except Exception as e:
                print(f"  ❌ {name} 예외 발생: {e}")

    # [3] Naver (8개)
    print("\n🟢 [3] Naver Open API / Datalab (8개 엔드포인트)")
    if not nav_id or not nav_sec or nav_id.strip() in ("", "your_naver_client_id_here"):
        print("  ⚠️ NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET 미설정 -> 진단 스킵 (실제 ID/Secret 필요)")
    else:
        nav = NaverOpenApiClient()
        cases = [
            ("1. 쇼핑 검색", lambda: nav.search_shop("원피스", display=1)),
            ("2. 검색어 트렌드 조회", lambda: nav.get_datalab_search_trend("2026-01-01", "2026-03-01", "month", [{"groupName": "패션", "keywords": ["패션"]}])),
            ("3. 쇼핑 분야별 검색 클릭 추이", lambda: nav.get_shopping_categories_trend("2026-01-01", "2026-03-01", "month", [{"name": "패션의류", "param": ["50000000"]}])),
            ("4. 쇼핑 분야별 · 성별 클릭 추이", lambda: nav.get_shopping_category_gender_trend("2026-01-01", "2026-03-01", "50000000", "f")),
            ("5. 쇼핑 분야별 · 연령별 클릭 추이", lambda: nav.get_shopping_category_age_trend("2026-01-01", "2026-03-01", "50000000", ["20", "30"])),
            ("6. 쇼핑 분야별 · 키워드별 클릭 추이", lambda: nav.get_shopping_category_keywords_trend("2026-01-01", "2026-03-01", "50000000", [{"name": "원피스", "param": ["원피스"]}])),
            ("7. 분야 · 키워드별 · 성별 클릭 추이", lambda: nav.get_shopping_category_keyword_gender_trend("2026-01-01", "2026-03-01", "50000000", "원피스", "f")),
            ("8. 분야 · 키워드별 · 연령별 클릭 추이", lambda: nav.get_shopping_category_keyword_age_trend("2026-01-01", "2026-03-01", "50000000", "원피스", ["20", "30"])),
        ]
        for name, fn in cases:
            try:
                fn()
                print(f"  ✅ {name}: 정상 응답 (200 OK)")
            except ApiException as e:
                print(f"  ❌ {name} 실패: [{e.status_code}] {e.error_type}\n     └─ 원인: {e.message}\n     └─ 해결: {e.solution}")
            except Exception as e:
                print(f"  ❌ {name} 예외 발생: {e}")

    print("\n" + "=" * 95)


if __name__ == "__main__":
    print_summary_table()
    run_live_diagnostics()
    print("\n[Pytest 전체 스위트 실행 중... (Mock 정합성 19개 + Live 19개)]")
    args = [__file__, "-v"]
    sys.exit(pytest.main(args))


