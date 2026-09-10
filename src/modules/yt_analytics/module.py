# ==============================================================================
# 🔵 [Step 5 - 파란점] 모듈 선언 및 통합 계층
# • 역할: BaseAgentModule을 구현하여 유튜브 통계/댓글 도구, 가드레일, 컨텍스트를 하나로 묶습니다.
# ➔ 다음 단계: 🟣 [Step 6] tests/modules/test_yt_analytics.py 로 이동하여 단위 테스트를 작성하세요.
# ==============================================================================

from typing import List
from langchain_core.tools import BaseTool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from src.config import settings
from .tools import get_channel_stats, get_video_comments
from .guardrails import YouTubeAnalyticsGuardrail
from .context import YouTubeAnalyticsContextProvider


class YouTubeAnalyticsModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "yt_analytics"

    @property
    def description(self) -> str:
        return "YouTube 채널 통계 및 시청자 댓글 분석"

    def is_enabled(self) -> bool:
        return bool(settings.YOUTUBE_API_KEY)

    def get_tools(self) -> List[BaseTool]:
        # [Tool 등록 영역] tools.py에서 새로 정의한 도구를 아래 리스트에 추가하시면 됩니다.
        return [get_channel_stats, get_video_comments]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [YouTubeAnalyticsGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return YouTubeAnalyticsContextProvider()
