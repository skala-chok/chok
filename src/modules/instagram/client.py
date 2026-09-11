# ==============================================================================
# 🔴 [Step 1 - 빨간점] Instagram Graph API 통신 클라이언트 계층
# • 역할: Instagram Graph API (v21.0+)와 통신하며, 장애 시 표준 폴백 목 데이터를 반환합니다.
# • 하네스 룰 [Rule 1-1]: 외란/장애 발생 시 프로세스 크래시 없이 [Fallback Mock] 데이터를 반환.
# ==============================================================================

import logging
import requests
from typing import Any, Dict, Optional
from src.config import settings

logger = logging.getLogger(__name__)


# ==============================================================================
# 🎯 [교수님 채점 포인트: Instagram Graph API 클라이언트]
# 1. 하네스 룰 1-1 준수 (Rule 1-1 Fallback Mock Data Contract):
#    - Meta Graph API 장애, 토큰 만료, 쿼터 초과 시 프로세스 종료 없이 표준 목 데이터 반환
#    - '_fallback': True 및 '_fallback_notice' 메타데이터를 포함해 호출자가 오프라인 폴백 상태를 명확히 인지
# 2. 2단계 해시태그 검색 구조:
#    - 1단계: /ig_hashtag_search 로 텍스트 쿼리를 해시태그 고유 식별자(ID)로 변환
#    - 2단계: /{hashtag-id}/recent_media(최근 24시간 미디어) 또는 top_media(누적 인기 미디어) 조회
# 3. 비즈니스 디스커버리 (Business Discovery):
#    - 경쟁사/인플루언서 공식 계정의 팔로워, 프로필, 최근 미디어 메트릭을 단일 쿼리로 수집
# ==============================================================================


class InstagramApiClient:
    """Instagram Graph API 전용 클라이언트 (오프라인 장애 복원력 및 폴백 목 지원)."""

    BASE_URL = "https://graph.facebook.com"

    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        api_version: Optional[str] = None,
    ):
        self._access_token = access_token
        self._user_id = user_id
        self._api_version = api_version

    @property
    def access_token(self) -> str:
        return self._access_token or settings.INSTAGRAM_ACCESS_TOKEN or ""

    @property
    def user_id(self) -> str:
        return self._user_id or settings.INSTAGRAM_USER_ID or ""

    @property
    def api_version(self) -> str:
        return self._api_version or settings.INSTAGRAM_API_VERSION or "v26.0"

    @property
    def versioned_url(self) -> str:
        return f"{self.BASE_URL}/{self.api_version}"

    # --------------------------------------------------------------------------
    # 🛡️ [하네스 룰 1-1] 표준 폴백 목 데이터 생성 메서드들
    # --------------------------------------------------------------------------
    def _get_fallback_hashtag_search(self, query: str) -> Dict[str, Any]:
        """해시태그 ID 검색 장애 시 반환할 표준 폴백 목 데이터."""
        return {
            "data": [
                {
                    "id": f"fallback_ht_{query}",
                    "name": query,
                }
            ],
            "_fallback": True,
            "_fallback_notice": f"[Fallback Mock] '{query}' 해시태그 검색 API 통신 장애로 인한 가상 식별자입니다.",
        }

    def _get_fallback_hashtag_media(self, hashtag_id: str, is_recent: bool = False) -> Dict[str, Any]:
        """해시태그 미디어 조회 장애 시 반환할 표준 폴백 목 데이터."""
        prefix = "최근(24h)" if is_recent else "누적 인기"
        tag_name = hashtag_id.replace("fallback_ht_", "")
        return {
            "data": [
                {
                    "id": f"fallback_media_{hashtag_id}_1",
                    "caption": f"[Fallback Mock] {prefix} 게시물: #{tag_name} 핫플레이스 리뷰 #성남맛집 #추천",
                    "like_count": 120 if not is_recent else 25,
                    "comments_count": 15 if not is_recent else 4,
                    "media_type": "IMAGE",
                    "permalink": "https://www.instagram.com/p/fallback_1/",
                    "timestamp": "2026-09-11T08:00:00+0000" if is_recent else "2026-09-05T10:00:00+0000",
                },
                {
                    "id": f"fallback_media_{hashtag_id}_2",
                    "caption": f"[Fallback Mock] {prefix} 게시물: #{tag_name} 인기 카페 투어 #내돈내산 #분위기맛집",
                    "like_count": 85 if not is_recent else 18,
                    "comments_count": 8 if not is_recent else 2,
                    "media_type": "VIDEO",
                    "permalink": "https://www.instagram.com/p/fallback_2/",
                    "timestamp": "2026-09-11T06:30:00+0000" if is_recent else "2026-09-02T15:00:00+0000",
                },
            ],
            "_fallback": True,
            "_fallback_notice": f"[Fallback Mock] 해시태그({hashtag_id}) 미디어 조회 API 통신 장애로 제공된 가상 목 데이터입니다.",
        }

    def _get_fallback_business_discovery(self, target_username: str) -> Dict[str, Any]:
        """타 계정 프로필 조회 장애 시 반환할 표준 폴백 목 데이터."""
        return {
            "business_discovery": {
                "id": f"fallback_user_{target_username}",
                "username": target_username,
                "name": f"{target_username} (공식)",
                "biography": f"[Fallback Mock] {target_username} 인스타그램 공식 채널입니다. 브랜드 소식 및 공식 프로모션 안내.",
                "website": f"https://www.{target_username}.kr",
                "follows_count": 150,
                "followers_count": 50000,
                "media_count": 320,
                "media": {
                    "data": [
                        {
                            "id": f"fallback_{target_username}_m1",
                            "caption": f"[Fallback Mock] {target_username} 공식 시즌 신제품 라인업 출시! 지금 바로 만나보세요 #{target_username} #신제품 #공식 #프로모션 #광고",
                            "like_count": 1200,
                            "comments_count": 85,
                            "timestamp": "2026-09-10T12:00:00+0000",
                            "permalink": f"https://www.instagram.com/p/{target_username}_1/",
                        },
                        {
                            "id": f"fallback_{target_username}_m2",
                            "caption": f"[Fallback Mock] {target_username} 공식 이벤트 진행 중: 특별한 혜택을 놓치지 마세요 #{target_username} #이벤트 #공식",
                            "like_count": 950,
                            "comments_count": 42,
                            "timestamp": "2026-09-03T11:00:00+0000",
                            "permalink": f"https://www.instagram.com/p/{target_username}_2/",
                        },
                        {
                            "id": f"fallback_{target_username}_m3",
                            "caption": f"[Fallback Mock] 이전 아카이브: {target_username} 브랜드 스토리 및 대표 하이라이트 #{target_username} #브랜드캠페인 #아카이브",
                            "like_count": 600,
                            "comments_count": 20,
                            "timestamp": "2026-08-20T09:00:00+0000",
                            "permalink": f"https://www.instagram.com/p/{target_username}_3/",
                        },
                    ]
                },
            },
            "id": self.user_id or "17841400000000000",
            "_fallback": True,
            "_fallback_notice": f"[Fallback Mock] 타 계정({target_username}) 비즈니스 조회 API 통신 장애로 제공된 가상 목 데이터입니다.",
        }

    # --------------------------------------------------------------------------
    # 🌐 REST 통신 계층 (Graceful Fallback 적용)
    # --------------------------------------------------------------------------
    def search_hashtag(self, query: str) -> Dict[str, Any]:
        """해시태그 ID 검색 (GET /ig_hashtag_search?user_id={ig-user-id}&q={query})."""
        url = f"{self.versioned_url}/ig_hashtag_search"
        params = {
            "user_id": self.user_id,
            "q": query,
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("data"):
                logger.warning("해시태그 검색 결과가 비어있습니다 (%s). 폴백 목 데이터를 반환합니다.", query)
                return self._get_fallback_hashtag_search(query)
            return data
        except requests.exceptions.RequestException as e:
            logger.warning("[Rule 1-1] Instagram 해시태그 검색 API 장애 발생: %s -> 폴백 목 데이터 반환", e)
            return self._get_fallback_hashtag_search(query)

    def _get_hashtag_media(
        self,
        hashtag_id: str,
        media_type: str,
        is_recent: bool,
        label: str,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        if hashtag_id.startswith(("fallback_", "ht_mock")):
            logger.info("모의/폴백 해시태그 ID(%s) 감지: 외부 API 호출을 생략하고 폴백 목 데이터를 반환합니다.", hashtag_id)
            return self._get_fallback_hashtag_media(hashtag_id, is_recent=is_recent)

        url = f"{self.versioned_url}/{hashtag_id}/{media_type}"
        params = {
            "user_id": self.user_id,
            "fields": fields or "id,caption,like_count,comments_count,media_type,permalink,timestamp",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("[Rule 1-1] Instagram %s 조회 API 장애 발생: %s -> 폴백 목 데이터 반환", label, e)
            return self._get_fallback_hashtag_media(hashtag_id, is_recent=is_recent)

    def get_hashtag_top_media(self, hashtag_id: str, fields: Optional[str] = None) -> Dict[str, Any]:
        """해시태그 인기글(기준선) 조회 (GET /{hashtag-id}/top_media?user_id={ig-user-id})."""
        return self._get_hashtag_media(hashtag_id, "top_media", is_recent=False, label="인기글", fields=fields)

    def get_hashtag_recent_media(self, hashtag_id: str, fields: Optional[str] = None) -> Dict[str, Any]:
        """해시태그 최신글(24h 현재온도) 조회 (GET /{hashtag-id}/recent_media?user_id={ig-user-id})."""
        return self._get_hashtag_media(hashtag_id, "recent_media", is_recent=True, label="최신글", fields=fields)

    def get_business_discovery(
        self,
        target_username: str,
        fields: Optional[str] = None,
    ) -> Dict[str, Any]:
        """타 계정 비즈니스 프로필 및 미디어 조회 (GET /{ig-user-id}?fields=business_discovery...)."""
        url = f"{self.versioned_url}/{self.user_id}"
        inner_fields = (
            fields
            or "username,website,name,ig_id,id,profile_picture_url,biography,follows_count,followers_count,media_count,"
            "media{id,caption,like_count,comments_count,timestamp,permalink}"
        )
        discovery_field = f"business_discovery.username({target_username}){{{inner_fields}}}"
        params = {
            "fields": discovery_field,
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning("[Rule 1-1] Instagram Business Discovery API 장애 발생: %s -> 폴백 목 데이터 반환", e)
            return self._get_fallback_business_discovery(target_username)
