from typing import Optional
from src.core.base import BaseContextProvider


class YouTubeAnalyticsContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 크리에이터나 채널의 규모/영향력을 파악할 때는 'get_channel_stats'를 사용하십시오.\n"
            "- 영상에 대한 시청자 피드백, 여론, 감성 분석이 필요한 경우 'get_video_comments'를 사용하십시오."
        )

    def get_dynamic_context(self, user_query: str) -> Optional[str]:
        return None
