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
        return [get_channel_stats, get_video_comments]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [YouTubeAnalyticsGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return YouTubeAnalyticsContextProvider()
