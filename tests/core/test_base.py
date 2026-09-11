import pytest
from src.core.base import GuardrailResult, BaseGuardrail, BaseContextProvider, BaseAgentModule
from langchain_core.tools import BaseTool, tool


def test_guardrail_result_defaults():
    res = GuardrailResult(passed=True)
    assert res.passed is True
    assert res.error_message is None
    assert res.sanitized_input is None

    res_fail = GuardrailResult(passed=False, error_message="금지어 포함", sanitized_input="대체 텍스트")
    assert res_fail.passed is False
    assert res_fail.error_message == "금지어 포함"
    assert res_fail.sanitized_input == "대체 텍스트"


def test_base_guardrail_default_methods():
    class DummyGuardrail(BaseGuardrail):
        pass

    guardrail = DummyGuardrail()
    res_input = guardrail.validate_input("hello")
    assert isinstance(res_input, GuardrailResult)
    assert res_input.passed is True

    res_args = guardrail.validate_tool_args("my_tool", {"arg1": "val"})
    assert isinstance(res_args, GuardrailResult)
    assert res_args.passed is True

    sanitized = guardrail.sanitize_output("my_tool", "raw_output")
    assert sanitized == "raw_output"


def test_base_context_provider_abstract():
    class IncompleteContextProvider(BaseContextProvider):
        pass

    with pytest.raises(TypeError):
        IncompleteContextProvider()

    class CompleteContextProvider(BaseContextProvider):
        def get_system_prompt_snippet(self) -> str:
            return "Domain snippet"

    provider = CompleteContextProvider()
    assert provider.get_system_prompt_snippet() == "Domain snippet"
    assert provider.get_dynamic_context("user query") is None


def test_base_agent_module_abstract():
    class IncompleteModule(BaseAgentModule):
        pass

    with pytest.raises(TypeError):
        IncompleteModule()


def test_custom_module_implementation():
    @tool
    def sample_tool(query: str) -> str:
        """테스트용 샘플 도구."""
        return f"result: {query}"

    class CustomGuardrail(BaseGuardrail):
        def validate_input(self, query: str) -> GuardrailResult:
            if "forbidden" in query:
                return GuardrailResult(passed=False, error_message="금지어 포함")
            return GuardrailResult(passed=True)

        def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
            return GuardrailResult(passed=True)

        def sanitize_output(self, tool_name: str, output: any) -> any:
            return output

    class CustomContextProvider(BaseContextProvider):
        def get_system_prompt_snippet(self) -> str:
            return "Sample Context Prompt"

    class SampleModule(BaseAgentModule):
        @property
        def name(self) -> str:
            return "sample_module"

        @property
        def description(self) -> str:
            return "Sample module for testing"

        def is_enabled(self) -> bool:
            return True

        def get_tools(self):
            return [sample_tool]

        def get_guardrails(self):
            return [CustomGuardrail()]

        def get_context_provider(self):
            return CustomContextProvider()

    module = SampleModule()
    assert module.name == "sample_module"
    assert module.description == "Sample module for testing"
    assert module.is_enabled() is True
    assert len(module.get_tools()) == 1
    assert module.get_guardrails()[0].validate_input("forbidden").passed is False
    assert module.get_guardrails()[0].validate_input("safe").passed is True
    assert module.get_context_provider().get_system_prompt_snippet() == "Sample Context Prompt"
