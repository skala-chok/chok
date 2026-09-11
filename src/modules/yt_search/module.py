# ==============================================================================
# 🔵 [Step 5 - 파란점] 모듈 선언 및 통합 계층
# • 역할: BaseAgentModule을 구현하여 유튜브 검색 도구, 가드레일, 컨텍스트를 하나로 묶습니다.
# ➔ 다음 단계: 🟣 [Step 6] tests/modules/test_yt_search.py 로 이동하여 단위 테스트를 작성하세요.
# ==============================================================================

from typing import List
from langchain_core.tools import BaseTool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from src.config import settings
from .tools import (
    find_youtube_channel, get_channel_videos, get_competitor_recent_uploads,
    get_channel_details,
)
from .guardrails import YouTubeSearchGuardrail
class YouTubeSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 회사의 공식 채널 후보 탐색에는 'find_youtube_channel'을 호출하십시오.\n"
            "- 채널 상세 확인, 기간별 영상, 최근 업로드에는 각 전용 도구를 호출하십시오."
        )


class YouTubeSearchModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "yt_search"

    @property
    def description(self) -> str:
        return "YouTube 동영상 검색 및 자막 추출"

    def is_enabled(self) -> bool:
        return bool(settings.YOUTUBE_API_KEY)

    def get_tools(self) -> List[BaseTool]:
        return [
            find_youtube_channel, get_channel_details, get_channel_videos,
            get_competitor_recent_uploads,
        ]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [YouTubeSearchGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return YouTubeSearchContextProvider()
