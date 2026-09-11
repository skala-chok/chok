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
from .context import InstagramContextProvider


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
