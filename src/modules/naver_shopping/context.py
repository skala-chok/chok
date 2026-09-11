# ==============================================================================
# 🟢 [Step 4 - 초록점] 프롬프트 컨텍스트 계층
# • 역할: 에이전트 시스템 프롬프트에 자동 주입될 쇼핑/트렌드 도메인 지침을 작성합니다.
# ➔ 다음 단계: 🔵 [Step 5] module.py 로 이동하여 쇼핑 모듈을 완성하세요.
# ==============================================================================

from src.core.base import BaseContextProvider


class NaverShoppingContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- category_code가 필요한 Tool을 호출해야 하는데 사용자가 category_code를 직접 주지 않았다면, "
            "절대 코드를 추측하지 말고 먼저 'find_naver_category_code'를 그 상품/분야 키워드로 호출해 후보를 확인하십시오. "
            "그렇게 찾은 category_code로 이어서 다른 Tool을 호출하면 되고, 후보가 여러 개면(예: 남성용/여성용) "
            "상황에 맞는 것을 고르거나 필요하면 각각 조회하십시오. "
            "'find_naver_category_code'로도 일치하는 카테고리를 못 찾았을 때만 사용자에게 정확한 분야명이나 "
            "category_code를 직접 물어보십시오.\n"
            "- 상품이나 키워드의 통합검색 검색 관심도 및 시기별 추세를 비교할 때는 'get_shopping_trends'를 사용하십시오 (키워드 최대 5개, 2016-01-01 이후 데이터만 조회 가능).\n"
            "- 네이버쇼핑 분야(카테고리)별 클릭 트렌드를 최대 3개까지 비교할 때는 'get_shopping_category_trend'를 사용하십시오.\n"
            "- 특정 분야의 성별/연령대별 클릭 트렌드가 필요하면 각각 'get_shopping_category_gender_trend', 'get_shopping_category_age_trend'를 사용하십시오.\n"
            "- 특정 분야 내 검색 키워드별(최대 5개) 클릭 트렌드 비교는 'get_shopping_keyword_trend'를 사용하십시오.\n"
            "- 특정 키워드의 성별/연령대별 클릭 트렌드가 필요하면 각각 'get_shopping_keyword_gender_trend', 'get_shopping_keyword_age_trend'를 사용하십시오."
        )
