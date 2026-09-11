from unittest.mock import MagicMock, patch
import pytest
from langchain_core.tools import tool
from langchain_core.messages import AIMessage

from src.core.agent import AgentRunner, AgentBuilder
from src.core.base import BaseAgentModule, BaseContextProvider, BaseGuardrail, GuardrailResult
from src.core.registry import ModuleRegistry
from tests.conftest import FakeChatWithTools


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






