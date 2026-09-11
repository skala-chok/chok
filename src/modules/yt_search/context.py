# ==============================================================================
# 🟢 [Step 4 - 초록점] 프롬프트 컨텍스트 계층
# • 역할: 에이전트 시스템 프롬프트에 자동 주입될 유튜브 검색 도메인 지침을 작성합니다.
# ➔ 다음 단계: 🔵 [Step 5] module.py 로 이동하여 유튜브 검색 모듈을 완성하세요.
# ==============================================================================

from src.core.base import BaseContextProvider


class YouTubeSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 회사의 공식 채널 후보 탐색에는 'find_youtube_channel'을 호출하십시오.\n"
            "- 채널 상세 확인, 기간별 영상, 최근 업로드에는 각 전용 도구를 호출하십시오."
        )
