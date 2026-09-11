# ==============================================================================
# 🔵 [Step 5 - 파란점] 모듈 선언 및 통합 계층
# • 역할: BaseAgentModule을 구현하여 Step 3(🟡 도구), Step 2(🟠 가드레일), Step 4(🟢 컨텍스트)를 묶습니다.
# • 팁: is_enabled()에서 필수 API 키의 존재 여부를 검사하여 Graceful Degradation을 보장하세요.
# ➔ 다음 단계: 🟣 [Step 6] tests/modules/test_naver_search.py 로 이동하여 Mock 단위 테스트를 작성하세요.
# ==============================================================================

from typing import List, Optional

from langchain_core.tools import BaseTool

from src.config import settings
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider

from .tools import search_naver_blog, search_naver_news
from .guardrails import NaverSearchGuardrail


class NaverSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 대한민국 국내 시사 및 실시간 이슈는 'search_naver_news'를 우선적으로 활용하십시오.\n"
            "- 실제 사용기, 맛집, 라이프스타일 후기 등은 'search_naver_blog'를 활용하십시오."
        )

    def get_dynamic_context(self, user_query: str) -> Optional[str]:
        return None


class NaverSearchModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "naver_search"

    @property
    def description(self) -> str:
        return "네이버 블로그 및 뉴스 검색"

    def is_enabled(self) -> bool:
        return bool(settings.NAVER_CLIENT_ID and settings.NAVER_CLIENT_SECRET)

    def get_tools(self) -> List[BaseTool]:
        return [search_naver_blog, search_naver_news]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [NaverSearchGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return NaverSearchContextProvider()
