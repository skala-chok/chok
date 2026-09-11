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
    from src.core import AgentRunner as CoreAgentRunner, AgentBuilder as CoreAgentBuilder
    assert CoreAgentRunner is AgentRunner
    assert CoreAgentBuilder is AgentBuilder


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
    assert "에이전트 >\n답변입니다" in captured
    assert "종료합니다." in captured


def test_main_cli_query_exception_handling(capsys):
    test_args = ["main.py", "--query", "에러유발"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", side_effect=RuntimeError("테스트 실행 에러")):
                with pytest.raises(SystemExit) as exc_info:
                    src.main.main()
                assert exc_info.value.code == 1

    captured = capsys.readouterr().err
    assert "[오류] 질의 처리 중 문제가 발생했습니다" in captured


def test_main_cli_initialization_exception_handling(capsys):
    test_args = ["main.py", "--query", "안녕"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules", side_effect=Exception("모듈 탐색 실패")):
            with pytest.raises(SystemExit) as exc_info:
                src.main.main()
            assert exc_info.value.code == 1

    captured = capsys.readouterr().err
    assert "[오류] 시스템 초기화 중 문제가 발생했습니다" in captured


def test_main_cli_setup_logging_level():
    test_args = ["main.py", "--log-level", "DEBUG", "--query", "테스트"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="응답"):
                with patch("src.main.setup_logging") as mock_setup:
                    src.main.main()
                    mock_setup.assert_called_once_with("DEBUG")


def test_agent_runner_callbacks_and_status_hook():
    """AgentRunner.run 실행 시 callbacks 및 on_status 훅이 올바르게 전달되는지 검증."""
    from src.core.scenario_registry import ScenarioRegistry

    registry = ModuleRegistry()
    registry.register(DummyModule())

    llm = FakeChatWithTools(responses=["Agent answered!"])
    runner = AgentRunner(
        registry=registry,
        llm=llm,
        scenario_registry=ScenarioRegistry(),  # 빈 레지스트리로 일반 에이전트 강제
    )

    mock_cb = MagicMock()
    status_events = []

    def on_status(msg: str):
        status_events.append(msg)

    try:
        from langchain_classic.agents import AgentExecutor
    except ImportError:
        from langchain.agents import AgentExecutor

    with patch.object(AgentExecutor, "invoke", side_effect=lambda self, *args, **kwargs: {"output": "Agent answered!"}) as mock_invoke:
        result = runner.run("안녕하세요", callbacks=[mock_cb], on_status=on_status)

        assert result == "Agent answered!"
        mock_invoke.assert_called_once()
        # config에 callbacks가 전달되었는지 확인
        call_kwargs = mock_invoke.call_args[1]
        assert "config" in call_kwargs
        assert mock_cb in call_kwargs["config"].get("callbacks", [])
        # on_status에 일반 에이전트 시작 이벤트가 기록되었는지 확인
        assert any("일반 에이전트" in ev for ev in status_events)


def test_agent_runner_scenario_tool_reporting_hook():
    """시나리오 실행 시 주입된 도구 호출이 on_status 훅을 통해 실시간 로깅되는지 검증."""
    from pydantic import BaseModel, Field
    from src.core.scenario import BaseScenario
    from src.core.scenario_registry import ScenarioRegistry

    class MockParams(BaseModel):
        q: str = Field(default="test")

    class MockReportScenario(BaseScenario):
        @property
        def name(self):
            return "mock_report_scen"

        @property
        def description(self):
            return "Mock Reporting Scenario"

        @property
        def parameters_schema(self):
            return MockParams

        @property
        def required_tool_names(self):
            return ["greet"]

        def execute(self, params, tools, context=None):
            # 도구 호출
            tool_res = tools["greet"].invoke({"name": "World"})
            return f"Scenario Result: {tool_res}"

    registry = ModuleRegistry()
    registry.register(DummyModule())

    scen_registry = ScenarioRegistry()
    scen_registry.register(MockReportScenario())

    runner = AgentRunner(
        registry=registry,
        llm=MagicMock(),
        scenario_registry=scen_registry,
    )

    # Router mock
    mock_plan = MagicMock()
    mock_plan.scenario_name = "mock_report_scen"
    mock_plan.confidence = 0.95
    mock_plan.parameters = {"q": "test"}

    status_events = []
    def on_status(msg: str):
        status_events.append(msg)

    with patch.object(runner.router, "route", return_value=mock_plan):
        result = runner.run("테스트", on_status=on_status)

        assert "Scenario Result: Hello, World!" in result
        # 시나리오 라우팅 이벤트 기록 확인
        assert any("mock_report_scen" in ev for ev in status_events)
        # 도구 호출 시작 및 완료 이벤트 기록 확인
        assert any("greet" in ev for ev in status_events)


def test_agent_runner_scenario_callbacks_tool_result_collection():
    """시나리오 실행 중 호출되는 도구의 실행 결과가 callbacks 핸들러에 정상 기록되는지 검증."""
    from pydantic import BaseModel
    from src.core.scenario import BaseScenario
    from src.core.scenario_registry import ScenarioRegistry

    class MockParams(BaseModel):
        q: str = ""

    class MockReportScenario(BaseScenario):
        @property
        def name(self):
            return "callback_test_scen"

        @property
        def description(self):
            return "Callback Test Scenario"

        @property
        def parameters_schema(self):
            return MockParams

        @property
        def required_tool_names(self):
            return ["greet"]

        def execute(self, params, tools, context=None):
            return tools["greet"].invoke({"name": "CallbackTester"})

    registry = ModuleRegistry()
    registry.register(DummyModule())

    scen_registry = ScenarioRegistry()
    scen_registry.register(MockReportScenario())

    runner = AgentRunner(
        registry=registry,
        llm=MagicMock(),
        scenario_registry=scen_registry,
    )

    mock_plan = MagicMock()
    mock_plan.scenario_name = "callback_test_scen"
    mock_plan.confidence = 0.99
    mock_plan.parameters = {"q": "test"}

    class DummyCallback:
        def __init__(self):
            self.tool_results = {}

        def record_tool_result(self, tool_name: str, result: str):
            self.tool_results[tool_name] = result

    cb = DummyCallback()
    with patch.object(runner.router, "route", return_value=mock_plan):
        result = runner.run("테스트", callbacks=[cb])

        assert result == "Hello, CallbackTester!"
        assert "greet" in cb.tool_results
        assert cb.tool_results["greet"] == "Hello, CallbackTester!"


def test_streamlit_tool_callback_handler():
    """StreamlitToolCallbackHandler의 tool_results 수집 및 record_tool_result 동작 검증."""
    from app import StreamlitToolCallbackHandler

    mock_status = MagicMock()
    log_store = []
    handler = StreamlitToolCallbackHandler(mock_status, log_store)

    # 1. on_tool_start -> on_tool_end
    handler.on_tool_start({"name": "get_shopping_trends"}, "{'keywords': '러닝화'}")
    assert handler._current_tool_name == "get_shopping_trends"

    handler.on_tool_end("[러닝화]\n  - 2026-01-01: 50.0")
    assert "get_shopping_trends" in handler.tool_results
    assert "50.0" in handler.tool_results["get_shopping_trends"]

    # 2. record_tool_result 직접 기록
    handler.record_tool_result("custom_tool", "custom_result_value")
    assert handler.tool_results["custom_tool"] == "custom_result_value"


def test_extract_json_payload():
    """응답 텍스트에서 ```json ... ``` 블록이 정상 분리되는지 검증."""
    from app import _extract_json_payload

    # 1. 앞에 JSON 블록이 있고 뒤에 마크다운이 있는 경우 (시나리오 표준)
    sample_with_json = "```json\n{\n  \"status\": \"success\"\n}\n```\n\n### 📊 리포트 제목\n- 결과 내용입니다."
    json_str, md_body = _extract_json_payload(sample_with_json)
    assert json_str is not None
    assert '"status": "success"' in json_str
    assert md_body == "### 📊 리포트 제목\n- 결과 내용입니다."

    # 2. JSON 블록이 없는 일반 마크다운/텍스트인 경우
    sample_text = "일반적인 텍스트 응답입니다."
    json_str2, md_body2 = _extract_json_payload(sample_text)
    assert json_str2 is None
    assert md_body2 == sample_text

    # 3. 뒤에 JSON 블록이 있는 경우
    sample_suffix_json = "### 마크다운 요약\n\n```json\n{\"id\": 123}\n```"
    json_str3, md_body3 = _extract_json_payload(sample_suffix_json)
    assert json_str3 is not None
    assert '"id": 123' in json_str3
    assert md_body3 == "### 마크다운 요약"


def test_render_agent_message_show_json_toggle(monkeypatch):
    """_render_agent_message가 show_json 토글 값에 따라 JSON expander 노출 여부를 올바르게 제어하는지 검증."""
    import streamlit as st
    from app import _render_agent_message

    expander_calls = []

    class MockExpanderContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_expander(label, expanded=False):
        expander_calls.append((label, expanded))
        return MockExpanderContext()

    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "expander", mock_expander)
    monkeypatch.setattr(st, "json", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "code", lambda *args, **kwargs: None)

    msg_with_json = {
        "role": "assistant",
        "content": "```json\n{\"test\": 1}\n```\n\n### 분석 리포트 본문",
    }

    # 1. show_json=False (기본값): JSON expander를 렌더링하지 않아 노이즈 제거
    expander_calls.clear()
    _render_agent_message(msg_with_json, show_json=False)
    assert len(expander_calls) == 0

    # 2. show_json=True (토글 활성화): JSON expander가 렌더링됨
    expander_calls.clear()
    _render_agent_message(msg_with_json, show_json=True)
    assert len(expander_calls) == 1
    assert "JSON" in expander_calls[0][0]
    assert expander_calls[0][1] is True



