import inspect
import sys
import pytest
from types import ModuleType
from langchain_core.tools import BaseTool, tool
from src.core.base import (
    BaseAgentModule,
    BaseContextProvider,
    BaseGuardrail,
    GuardrailResult,
)
from src.core.guardrails import wrap_tool_with_guardrails
from src.core.registry import ModuleRegistry


@tool
def add_numbers(a: int, b: int) -> int:
    """두 숫자를 더합니다."""
    return a + b


class PositiveOnlyGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if args.get("a", 0) < 0 or args.get("b", 0) < 0:
            return GuardrailResult(passed=False, error_message="음수는 허용되지 않습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        return f"정제된 결과: {output}"


class MaxValueGuardrail(BaseGuardrail):
    def __init__(self, max_val: int = 100):
        self.max_val = max_val

    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if args.get("a", 0) > self.max_val or args.get("b", 0) > self.max_val:
            return GuardrailResult(passed=False, error_message=f"{self.max_val} 초과 값은 허용되지 않습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        return f"[최종] {output}"


class CustomClassTool(BaseTool):
    name: str = "custom_class_tool"
    description: str = "A custom BaseTool class without .func"

    def _run(self, text: str) -> str:
        return f"processed: {text}"


def test_guardrailed_tool_blocks_invalid_args():
    wrapped = wrap_tool_with_guardrails(add_numbers, [PositiveOnlyGuardrail()])

    # 음수 인자 전달 시 가드레일 에러 메시지 반환
    res_fail = wrapped.invoke({"a": -1, "b": 5})
    assert "가드레일 검증 실패" in res_fail
    assert "음수는 허용되지 않습니다." in res_fail

    # 양수 인자 전달 시 정상 실행 및 출력 정제
    res_pass = wrapped.invoke({"a": 2, "b": 3})
    assert res_pass == "정제된 결과: 5"


def test_guardrailed_tool_empty_guardrails():
    # 가드레일이 없으면 원본 도구 반환
    wrapped = wrap_tool_with_guardrails(add_numbers, [])
    assert wrapped is add_numbers
    assert wrapped.invoke({"a": 2, "b": 3}) == 5


def test_guardrailed_tool_multiple_guardrails_chained():
    # 2개의 가드레일 순차 검증 및 출력 정제 체이닝
    wrapped = wrap_tool_with_guardrails(
        add_numbers, [PositiveOnlyGuardrail(), MaxValueGuardrail(50)]
    )

    # 1번째 가드레일 차단
    res_fail1 = wrapped.invoke({"a": -2, "b": 10})
    assert "음수는 허용되지 않습니다." in res_fail1

    # 2번째 가드레일 차단
    res_fail2 = wrapped.invoke({"a": 10, "b": 60})
    assert "50 초과 값은 허용되지 않습니다." in res_fail2

    # 모두 통과 시 두 정제 함수 모두 적용
    res_pass = wrapped.invoke({"a": 10, "b": 20})
    assert res_pass == "[최종] 정제된 결과: 30"


def test_guardrailed_tool_supports_custom_basetool_class():
    class TextLengthGuardrail(BaseGuardrail):
        def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
            if len(args.get("text", "")) > 10:
                return GuardrailResult(passed=False, error_message="텍스트가 너무 깁니다.")
            return GuardrailResult(passed=True)

        def sanitize_output(self, tool_name: str, output: any) -> any:
            return output.upper()

    tool_instance = CustomClassTool()
    wrapped = wrap_tool_with_guardrails(tool_instance, [TextLengthGuardrail()])

    fail_res = wrapped.invoke({"text": "this is too long text"})
    assert "가드레일 검증 실패" in fail_res
    assert "텍스트가 너무 깁니다." in fail_res

    pass_res = wrapped.invoke({"text": "short"})
    assert pass_res == "PROCESSED: SHORT"


@pytest.mark.anyio
async def test_guardrailed_tool_async_support():
    @tool
    async def async_multiply(x: int, y: int) -> int:
        """두 숫자를 비동기로 곱합니다."""
        return x * y

    class AsyncGuardrail(BaseGuardrail):
        def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
            if args.get("x", 0) == 0 or args.get("y", 0) == 0:
                return GuardrailResult(passed=False, error_message="0은 곱할 수 없습니다.")
            return GuardrailResult(passed=True)

        def sanitize_output(self, tool_name: str, output: any) -> any:
            return f"비동기 결과: {output}"

    wrapped = wrap_tool_with_guardrails(async_multiply, [AsyncGuardrail()])

    fail_res = await wrapped.ainvoke({"x": 0, "y": 10})
    assert "0은 곱할 수 없습니다." in fail_res

    pass_res = await wrapped.ainvoke({"x": 4, "y": 5})
    assert pass_res == "비동기 결과: 20"


def test_module_registry_filtering():
    class ActiveModule(BaseAgentModule):
        @property
        def name(self):
            return "active_mod"

        @property
        def description(self):
            return "active"

        def is_enabled(self):
            return True

        def get_tools(self):
            return [add_numbers]

        def get_guardrails(self):
            return []

        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self):
                    return "Active Prompt"

            return CP()

    class DisabledModule(BaseAgentModule):
        @property
        def name(self):
            return "disabled_mod"

        @property
        def description(self):
            return "disabled"

        def is_enabled(self):
            return False

        def get_tools(self):
            return []

        def get_guardrails(self):
            return []

        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self):
                    return ""

            return CP()

    registry = ModuleRegistry()
    registry.register(ActiveModule())
    registry.register(DisabledModule())

    enabled_modules = registry.get_enabled_modules()
    assert len(enabled_modules) == 1
    assert enabled_modules[0].name == "active_mod"
    assert registry.get_module("active_mod") is not None
    assert registry.get_module("disabled_mod") is not None
    assert registry.get_module("unknown") is None
    assert len(registry.get_all_modules()) == 2
    assert "active_mod" in registry


def test_module_registry_discover_modules_nonexistent_package():
    registry = ModuleRegistry()
    # 존재하지 않는 패키지 경로는 예외를 던지지 않고 무시되어야 함
    registry.discover_modules("non_existent_package_xyz")
    assert len(registry.get_all_modules()) == 0


def test_module_registry_discover_modules_dynamic(tmp_path, monkeypatch):
    # tmp_path 아래 임시 패키지 생성: fake_modules/sample_mod/module.py
    pkg_dir = tmp_path / "fake_modules"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    subpkg_dir = pkg_dir / "sample_mod"
    subpkg_dir.mkdir()
    (subpkg_dir / "__init__.py").write_text("", encoding="utf-8")

    module_code = """
from src.core.base import BaseAgentModule, BaseContextProvider

class SampleTestModule(BaseAgentModule):
    @property
    def name(self): return "sample_test"
    @property
    def description(self): return "Sample Description"
    def is_enabled(self): return True
    def get_tools(self): return []
    def get_guardrails(self): return []
    def get_context_provider(self):
        class CP(BaseContextProvider):
            def get_system_prompt_snippet(self): return ""
        return CP()
"""
    (subpkg_dir / "module.py").write_text(module_code, encoding="utf-8")

    # sys.path 에 tmp_path 추가
    monkeypatch.syspath_prepend(str(tmp_path))

    registry = ModuleRegistry()
    registry.discover_modules("fake_modules")

    modules = registry.get_all_modules()
    assert len(modules) == 1
    assert modules[0].name == "sample_test"
    assert modules[0].is_enabled() is True


def test_module_registry_invalid_type_raises_error():
    registry = ModuleRegistry()
    with pytest.raises(TypeError, match="Expected an instance of BaseAgentModule"):
        registry.register("not_a_module")


def test_module_registry_helpers():
    class DummyModule(BaseAgentModule):
        @property
        def name(self):
            return "dummy"

        @property
        def description(self):
            return "dummy"

        def is_enabled(self):
            return True

        def get_tools(self):
            return []

        def get_guardrails(self):
            return []

        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self):
                    return ""

            return CP()

    registry = ModuleRegistry()
    mod = DummyModule()
    registry.register(mod)
    assert len(registry) == 1
    assert registry["dummy"] is mod
    assert "dummy" in registry

    registry.clear()
    assert len(registry) == 0
    assert "dummy" not in registry


def test_guardrailed_tool_structured_tool_sync_and_async_distinction():
    @tool
    def sync_tool(x: int) -> int:
        """Sync tool"""
        return x * 2

    @tool
    async def async_tool(x: int) -> int:
        """Async tool"""
        return x * 2

    wrapped_sync = wrap_tool_with_guardrails(sync_tool, [PositiveOnlyGuardrail()])
    assert wrapped_sync.func is not None
    assert wrapped_sync.coroutine is None

    wrapped_async = wrap_tool_with_guardrails(async_tool, [PositiveOnlyGuardrail()])
    assert wrapped_async.func is None
    assert wrapped_async.coroutine is not None


def test_module_registry_discover_modules_broken_and_imported_classes(
    tmp_path, monkeypatch, caplog
):
    import logging

    pkg_dir = tmp_path / "mixed_modules"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")

    # 1. 문법 오류가 있는 결함 모듈
    broken_dir = pkg_dir / "broken_mod"
    broken_dir.mkdir()
    (broken_dir / "__init__.py").write_text("", encoding="utf-8")
    (broken_dir / "module.py").write_text("def broken( syntax_error: : :", encoding="utf-8")

    # 2. 외부 모듈
    ext_dir = pkg_dir / "external_mod"
    ext_dir.mkdir()
    (ext_dir / "__init__.py").write_text("", encoding="utf-8")
    (ext_dir / "module.py").write_text(
        """
from src.core.base import BaseAgentModule, BaseContextProvider

class ExternalModule(BaseAgentModule):
    @property
    def name(self): return "external"
    @property
    def description(self): return "external"
    def is_enabled(self): return True
    def get_tools(self): return []
    def get_guardrails(self): return []
    def get_context_provider(self):
        class CP(BaseContextProvider):
            def get_system_prompt_snippet(self): return ""
        return CP()
""",
        encoding="utf-8",
    )

    # 3. external_mod에서 ExternalModule을 임포트하는 정상 모듈
    good_dir = pkg_dir / "good_mod"
    good_dir.mkdir()
    (good_dir / "__init__.py").write_text("", encoding="utf-8")
    (good_dir / "module.py").write_text(
        """
from src.core.base import BaseAgentModule, BaseContextProvider
from mixed_modules.external_mod.module import ExternalModule

class GoodModule(BaseAgentModule):
    @property
    def name(self): return "good"
    @property
    def description(self): return "good"
    def is_enabled(self): return True
    def get_tools(self): return []
    def get_guardrails(self): return []
    def get_context_provider(self):
        class CP(BaseContextProvider):
            def get_system_prompt_snippet(self): return ""
        return CP()
""",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))

    registry = ModuleRegistry()
    with caplog.at_level(logging.WARNING):
        registry.discover_modules("mixed_modules")

    # 정상 모듈과 외부 모듈은 등록되고, 결함 모듈은 경고 로그와 함께 안전하게 스킵되어야 함
    assert "good" in registry
    assert "external" in registry
    # 결함 모듈로 인해 전체 탐색 프로세스가 중단되지 않음을 확인
    assert len(registry) == 2


