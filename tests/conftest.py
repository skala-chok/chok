import pytest
from typing import Any
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)


class ToolCallingFakeChat(FakeMessagesListChatModel):
    """Fake chat model supporting BaseMessage responses and bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self


class FakeChatWithTools(FakeListChatModel):
    """Fake chat model supporting string responses and bind_tools."""

    def bind_tools(self, tools, **kwargs):
        return self



def make_tool_mock(result: Any) -> MagicMock:
    """공통 Mock 도구 헬퍼: invoke 호출 시 지정된 결과를 반환합니다."""
    tool = MagicMock()
    tool.invoke.return_value = result
    return tool


@pytest.fixture
def mock_llm():
    """Mock ChatOpenAI instance for unit testing without API keys."""
    return MagicMock(spec=BaseChatModel)

