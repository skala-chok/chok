from src.core.base import BaseContextProvider


class NaverShoppingContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 상품 가격 비교 및 최저가 탐색 시 'search_naver_shopping'을 사용하십시오.\n"
            "- 상품이나 키워드의 검색 관심도 및 시기별 추세를 비교할 때는 'get_shopping_trends'를 사용하십시오."
        )
