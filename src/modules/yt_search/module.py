from typing import List
from langchain_core.tools import BaseTool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from src.config import settings
from .tools import search_youtube_videos, get_video_transcript
from .guardrails import YouTubeSearchGuardrail
from .context import YouTubeSearchContextProvider


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
        # [Tool 등록 영역] tools.py에서 새로 정의한 도구를 아래 리스트에 추가하시면 됩니다.
        return [search_youtube_videos, get_video_transcript]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [YouTubeSearchGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return YouTubeSearchContextProvider()
