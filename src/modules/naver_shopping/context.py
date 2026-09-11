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
            "- 상품이나 키워드의 통합검색 검색 관심도 및 시기별 추세를 비교할 때는 'get_shopping_trends'를 사용하십시오.\n"
            "- 네이버쇼핑 분야(카테고리)별 클릭 트렌드를 최대 3개까지 비교할 때는 'get_shopping_category_trend'를 사용하십시오.\n"
            "- 특정 분야의 성별/연령대별 클릭 트렌드가 필요하면 각각 'get_shopping_category_gender_trend', 'get_shopping_category_age_trend'를 사용하십시오.\n"
            "- 특정 분야 내 검색 키워드별(최대 5개) 클릭 트렌드 비교는 'get_shopping_keyword_trend'를 사용하십시오.\n"
            "- 특정 키워드의 성별/연령대별 클릭 트렌드가 필요하면 각각 'get_shopping_keyword_gender_trend', 'get_shopping_keyword_age_trend'를 사용하십시오.\n"
            "- 분야 코드(category_code)를 모를 경우 사용자에게 네이버쇼핑 카테고리 코드를 먼저 물어보거나, 알려진 코드가 없으면 추측하지 말고 그 사실을 알리십시오."
        )
