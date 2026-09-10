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
