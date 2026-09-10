from src.core.base import BaseContextProvider


class NaverSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 대한민국 국내 시사 및 실시간 이슈는 'search_naver_news'를 우선적으로 활용하십시오.\n"
            "- 실제 사용기, 맛집, 라이프스타일 후기 등은 'search_naver_blog'를 활용하십시오."
        )
