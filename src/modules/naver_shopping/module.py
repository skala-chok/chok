# ==============================================================================
# 🔵 [Step 5 - 파란점] 모듈 선언 및 통합 계층
# • 역할: BaseAgentModule을 구현하여 쇼핑 도구, 가드레일, 컨텍스트를 하나로 묶습니다.
# ➔ 다음 단계: 🟣 [Step 6] tests/modules/test_naver_shopping.py 로 이동하여 단위 테스트를 작성하세요.
# ==============================================================================

from typing import List
from langchain_core.tools import BaseTool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider
from src.config import settings
from .tools import search_naver_shopping, get_shopping_trends
from .guardrails import NaverShoppingGuardrail
from .context import NaverShoppingContextProvider


class NaverShoppingModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "naver_shopping"

    @property
    def description(self) -> str:
        return "네이버 쇼핑 최저가 및 데이터랩 트렌드 분석"

    def is_enabled(self) -> bool:
        return bool(settings.NAVER_CLIENT_ID and settings.NAVER_CLIENT_SECRET)

    def get_tools(self) -> List[BaseTool]:
        # [Tool 등록 영역] tools.py에서 새로 정의한 도구를 아래 리스트에 추가하시면 됩니다.
        return [search_naver_shopping, get_shopping_trends]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [NaverShoppingGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return NaverShoppingContextProvider()
