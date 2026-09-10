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
        return [search_naver_blog, search_naver_news]

    def get_guardrails(self) -> List[BaseGuardrail]:
        return [NaverSearchGuardrail()]

    def get_context_provider(self) -> BaseContextProvider:
        return NaverSearchContextProvider()
