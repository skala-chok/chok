# ==============================================================================
# 🔵 [Step 5 - 파란점] 모듈 선언 및 통합 계층
# • 역할: BaseAgentModule을 구현하여 Step 3(🟡 도구), Step 2(🟠 가드레일), Step 4(🟢 컨텍스트)를 묶습니다.
# • 팁: is_enabled()에서 필수 API 키의 존재 여부를 검사하여 Graceful Degradation을 보장하세요.
# ➔ 다음 단계: 🟣 [Step 6] tests/modules/test_naver_search.py 로 이동하여 Mock 단위 테스트를 작성하세요.
# ==============================================================================

from typing import List
from langchain_core.tools import BaseTool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from src.config import settings
from .tools import search_naver_blog, search_naver_news
from .guardrails import NaverSearchGuardrail
from .context import NaverSearchContextProvider


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
        # [Tool 등록 영역] tools.py에서 새로 정의한 도구를 아래 리스트에 추가하시면 됩니다.
        return [search_naver_blog, search_naver_news]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [NaverSearchGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return NaverSearchContextProvider()
