# ==============================================================================
# 🟢 [Step 4 - 초록점] 프롬프트 컨텍스트 계층
# • 역할: 에이전트 시스템 프롬프트에 자동 주입될 도메인 지침과 도구 사용 요령을 작성합니다.
# • 팁: 어떤 상황에서 이 모듈의 도구를 써야 하는지 불릿 포인트로 작성하세요.
# ➔ 다음 단계: 🔵 [Step 5] module.py 로 이동하여 모듈을 완성하세요.
# ==============================================================================

from src.core.base import BaseContextProvider


class NaverSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 대한민국 국내 시사 및 실시간 이슈는 'search_naver_news'를 우선적으로 활용하십시오.\n"
            "- 실제 사용기, 맛집, 라이프스타일 후기 등은 'search_naver_blog'를 활용하십시오."
        )
