# ==============================================================================
# 🟢 [Step 4 - 초록점] 프롬프트 컨텍스트 계층
# • 역할: 에이전트 시스템 프롬프트에 자동 주입될 쇼핑/트렌드 도메인 지침을 작성합니다.
# ➔ 다음 단계: 🔵 [Step 5] module.py 로 이동하여 쇼핑 모듈을 완성하세요.
# ==============================================================================

from src.core.base import BaseContextProvider


class NaverShoppingContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 상품 가격 비교 및 최저가 탐색 시 'search_naver_shopping'을 사용하십시오.\n"
            "- 상품이나 키워드의 검색 관심도 및 시기별 추세를 비교할 때는 'get_shopping_trends'를 사용하십시오."
        )
