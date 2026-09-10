import sys
from unittest.mock import MagicMock, patch
import pytest
from langchain_core.tools import tool
from langchain_core.messages import AIMessage
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.core.agent import AgentRunner, AgentBuilder
from src.core.base import BaseAgentModule, BaseContextProvider, BaseGuardrail, GuardrailResult
from src.core.registry import ModuleRegistry
import src.main


@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"


class DummyModule(BaseAgentModule):
    @property
    def name(self):
        return "dummy"

    @property
    def description(self):
        return "dummy test module"

    def is_enabled(self):
        return True

    def get_tools(self):
        return [greet]

    def get_guardrails(self):
        return []

    def get_context_provider(self):
        class CP(BaseContextProvider):
            def get_system_prompt_snippet(self):
                return "Dummy Context"

        return CP()


class FakeChatWithTools(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_agent_runner_input_guardrail_rejection():
    class BlockAllGuardrail(BaseGuardrail):
        def validate_input(self, query: str) -> GuardrailResult:
            return GuardrailResult(passed=False, error_message="시스템 입력 차단")

    class BlockModule(DummyModule):
        def get_guardrails(self):
            return [BlockAllGuardrail()]

    registry = ModuleRegistry()
    registry.register(BlockModule())

    runner = AgentRunner(registry=registry, llm=MagicMock())
    result = runner.run("테스트 질문")
    assert "차단되었습니다" in result
    assert "시스템 입력 차단" in result


def test_agent_runner_system_prompt_and_tools_compilation():
    registry = ModuleRegistry()
    dummy = DummyModule()
    registry.register(dummy)

    llm = FakeChatWithTools(responses=["Agent response!"])
    runner = AgentRunner(registry=registry, llm=llm)

    # Verify tools
    assert len(runner.tools) == 1
    assert runner.tools[0].name == "greet"

    # Verify system prompt snippet integration
    assert "YouTube 및 Naver Open API" in runner.system_prompt_text
    assert "[dummy test module 가이드]" in runner.system_prompt_text
    assert "Dummy Context" in runner.system_prompt_text

    # Verify successful execution
    result = runner.run("Hello there")
    assert result == "Agent response!"


def test_agent_runner_disabled_module_excluded():
    class DisabledModule(DummyModule):
        @property
        def name(self):
            return "disabled_mod"

        def is_enabled(self):
            return False

    registry = ModuleRegistry()
    registry.register(DisabledModule())

    llm = FakeChatWithTools(responses=["OK"])
    runner = AgentRunner(registry=registry, llm=llm)

    assert len(runner.tools) == 0
    assert "disabled_mod" not in runner.system_prompt_text


def test_agent_runner_empty_context_provider_snippet():
    class EmptyContextModule(DummyModule):
        @property
        def name(self):
            return "empty_ctx"

        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self):
                    return ""

            return CP()

    registry = ModuleRegistry()
    registry.register(EmptyContextModule())

    llm = FakeChatWithTools(responses=["OK"])
    runner = AgentRunner(registry=registry, llm=llm)
    assert "[dummy test module 가이드]" not in runner.system_prompt_text


def test_agent_runner_default_llm_initialization():
    registry = ModuleRegistry()
    with patch("src.core.agent.ChatOpenAI") as mock_chat_openai:
        runner = AgentRunner(registry=registry)
        mock_chat_openai.assert_called_once()
        assert runner.llm == mock_chat_openai.return_value


def test_agent_builder_alias():
    assert AgentBuilder is AgentRunner


def test_mock_llm_fixture(mock_llm):
    assert mock_llm is not None


def test_main_cli_query_mode(capsys):
    test_args = ["main.py", "--query", "날씨 알려줘"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="날씨는 맑음입니다."):
                src.main.main()

    captured = capsys.readouterr().out
    assert "로드된 활성 모듈" in captured
    assert "[질의]: 날씨 알려줘" in captured
    assert "날씨는 맑음입니다." in captured


def test_main_cli_interactive_mode_quit(capsys):
    test_args = ["main.py", "--interactive"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch("builtins.input", side_effect=["", "quit"]):
                src.main.main()

    captured = capsys.readouterr().out
    assert "대화형 모드를 시작합니다." in captured
    assert "종료합니다." in captured


def test_main_cli_interactive_mode_execution_and_eof(capsys):
    test_args = ["main.py", "-i"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="답변입니다"):
                with patch("builtins.input", side_effect=["안녕", EOFError()]):
                    src.main.main()

    captured = capsys.readouterr().out
    assert "🤖 에이전트 >\n답변입니다" in captured
    assert "종료합니다." in captured
