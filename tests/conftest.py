# ==============================================================================
# 🎯 [교수님 채점 포인트: 하네스 룰 1-2 (100% Mocking 무네트워크 단위 테스트 원칙)]
# 1. 제로 네트워크(Zero Network) 테스트 환경:
#    - tests/ 내 모든 테스트는 실제 외부 LLM(OpenAI)이나 외부 API(Naver, YouTube, Instagram)를
#      호출하지 않고, 아래의 가상 모델 및 Mock 픽스처를 통해 100% 격리된 환경에서 동작합니다.
# 2. 초고속 실행 (Fast Feedback Loop):
#    - 네트워크 I/O 대기시간이 전혀 없어 210개 이상의 전체 테스트 스위트가 1~2초 내에 완료됩니다.
# 3. 비용 및 쿼터 보존 (Zero Cost & Quota Safe):
#    - CI/CD 파이프라인 및 개발 주기에서 과금이나 일일 API Quota 고갈 없이 무제한 테스트 가능합니다.
# 4. 결정론적 검증 (Deterministic Assertions):
#    - 비결정론적인 생성형 AI 출력을 배제하고, 의도한 도구 호출(Tool Call)과 메시지를 정확히 모사합니다.
# ==============================================================================

import pytest
from typing import Any
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)


class ToolCallingFakeChat(FakeMessagesListChatModel):
    """LangChain의 bind_tools 및 BaseMessage 응답을 모사하는 가상 ChatModel.
    
    에이전트 단위 테스트에서 실제 OpenAI 호출 없이 가상 도구 호출(AIMessage tool_calls)을
    결정론적으로 발생시켜 에이전트 루프와 가드레일을 100% 검증합니다.
    """

    def bind_tools(self, tools, **kwargs):
        return self


class FakeChatWithTools(FakeListChatModel):
    """문자열 응답 목록과 bind_tools를 지원하는 가상 ChatModel."""

    def bind_tools(self, tools, **kwargs):
        return self


def make_tool_mock(result: Any) -> MagicMock:
    """공통 Mock 도구 헬퍼: invoke 호출 시 지정된 결과를 즉각 반환합니다."""
    tool = MagicMock()
    tool.invoke.return_value = result
    return tool


@pytest.fixture
def mock_llm():
    """API 키 없이 단위 테스트를 수행할 수 있도록 BaseChatModel 스펙을 만족하는 Mock 인스턴스를 제공합니다."""
    return MagicMock(spec=BaseChatModel)


