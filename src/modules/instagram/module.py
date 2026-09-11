# ==============================================================================
# 🔵 [Step 5 - 파란점] Instagram 에이전트 모듈 등록 계층
# • 역할: BaseAgentModule을 상속받아 ModuleRegistry에 자동 등록될 모듈 선언
# ==============================================================================

from typing import List
from langchain_core.tools import BaseTool
from src.config import settings
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from .tools import (
    search_hashtag_id,
    get_hashtag_recent_media,
    get_hashtag_top_media,
    get_competitor_profile,
)
from .guardrails import InstagramGuardrail


class InstagramContextProvider(BaseContextProvider):
    """Instagram Graph API 도구 사용을 위한 시스템 프롬프트 가이드라인 제공."""

    def get_system_prompt_snippet(self) -> str:
        return (
            "- 인스타그램 해시태그 및 경쟁사 프로필 조회가 필요할 때 'instagram' 도구들을 사용하십시오.\n"
            "- [해시태그 정규화]: 'search_hashtag_id' 호출 시 공백과 '#'을 제거한 정규화 키워드를 사용하고, 사용자에게 정규화 사실을 안내하십시오.\n"
            "- [최신글과 인기글의 구분]: 'get_hashtag_recent_media'(최근 24시간 실시간 유입)와 'get_hashtag_top_media'(누적 인기 기준선)를 절대 뭉쳐서 표현하지 마십시오.\n"
            "- [조회수 지표 부재]: Instagram Graph API(business_discovery)는 타 계정 미디어의 '조회수(View count)'를 일절 제공하지 않습니다. 절대 조회수를 생성하지 말고, 좋아요/댓글 기반 참여율로 분석하십시오.\n"
            "- [계정 핸들 추측 금지]: 경쟁사 인스타그램 핸들을 임의로 추측하지 말고, 확인되지 않으면 사용자에게 재확인을 요청하십시오.\n"
            "- [유료 광고/광고비 한계]: Graph API로 광고비 집행액이나 유료 광고 여부를 확인할 수 없음을 사용자에게 밝히십시오.\n"
            "- [시계열 추이 한계]: recent_media는 최근 24시간 데이터만 제공하므로 한 달 단위의 시계열 추세를 단정하지 마십시오."
        )


class InstagramModule(BaseAgentModule):
    """인스타그램 Graph API 연동 모듈 (해시태그 검색, 실시간 최신/인기 게시물 수집, 경쟁사 비즈니스 프로필 분석)."""

    @property
    def name(self) -> str:
        return "instagram"

    @property
    def description(self) -> str:
        return (
            "인스타그램 Graph API 연동 모듈: 해시태그 ID 검색, 최근 유입 게시물(24h) 및 인기 게시물 수집, "
            "타 경쟁사 비즈니스 프로필/미디어 분석을 제공합니다."
        )

    def is_enabled(self) -> bool:
        """인스타그램 액세스 토큰 및 User ID 설정 여부 확인."""
        return bool(settings.INSTAGRAM_ACCESS_TOKEN and settings.INSTAGRAM_USER_ID)

    def get_tools(self) -> List[BaseTool]:
        return [
            search_hashtag_id,
            get_hashtag_recent_media,
            get_hashtag_top_media,
            get_competitor_profile,
        ]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [InstagramGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return InstagramContextProvider()
