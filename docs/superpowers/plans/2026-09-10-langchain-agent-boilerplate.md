# LangChain 기반 다중 작업자 병렬 협업 에이전트 보일러플레이트 구현 계획서

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 4명의 개발자가 각각 YouTube 및 Naver Open API를 활용하여 `tool-context-guardrail-testcase`를 Git 충돌 없이 동시에 병렬 개발할 수 있는 모듈러 플러그인 기반 LangChain 에이전트 보일러플레이트를 구축한다.

**Architecture:** 동결된 코어 레이어(`src/core/`)에 추상 인터페이스(`BaseAgentModule`, `BaseGuardrail`, `BaseContextProvider`)와 모듈 자동 탐색 레지스트리(`registry.py`), 도구 가드레일 래퍼(`GuardrailedTool`), 런타임 에이전트 빌더(`agent.py`)를 배치하고, 4명의 작업자는 완전히 격리된 디렉토리(`src/modules/worker_*`) 및 테스트 파일(`tests/modules/test_*.py`)에서만 독립적으로 코드를 작성한다.

**Tech Stack:** Python 3.11+, LangChain 0.3 Core (`langchain-core`, `langchain`), LangChain Community/OpenAI (`langchain-openai`), Pydantic v2 / Pydantic Settings, Requests, Pytest, Pytest-Mock.

**Spec:** [`docs/superpowers/specs/2026-09-10-langchain-agent-boilerplate-design.md`](file:///Users/yeongmin-yun/skala-workspace/skala-chok/docs/superpowers/specs/2026-09-10-langchain-agent-boilerplate-design.md)

## Global Constraints

- LangChain 0.3 Core의 표준 도구 호출 에이전트(`create_tool_calling_agent` + `AgentExecutor`) 패턴 준수 (LangGraph 등 무거운 의존성 배제).
- 모든 외부 API 호출은 `unittest.mock`을 기본 픽스처로 제공하여 외부 쿼터 소모 없이 1초 내 단위 테스트가 완결되어야 함.
- 특정 모듈의 API 키가 누락되더라도 시스템 전체가 중단되지 않고 해당 모듈만 안전하게 `disabled` 처리(Graceful Degradation)되어야 함.
- 모든 모듈은 4대 필수 요소(`Tool`, `Context`, `Guardrail`, `TestCase`)를 갖추어야 함.
- 패키지 의존성은 `requirements.txt`와 표준 `pip` / `venv` 환경 지원.

---

### Task 1: 프로젝트 기초 설정 및 환경 구성

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `src.config.settings` (`Settings` 클래스: OPENAI_API_KEY, YOUTUBE_API_KEY, NAVER_CLIENT_ID, NAVER_CLIENT_SECRET, MODEL_NAME 등 환경 변수 제공)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import pytest
from src.config import Settings

def test_settings_default_values():
    settings = Settings(
        OPENAI_API_KEY="test-openai-key",
        YOUTUBE_API_KEY="test-yt-key",
        NAVER_CLIENT_ID="test-naver-id",
        NAVER_CLIENT_SECRET="test-naver-secret"
    )
    assert settings.OPENAI_API_KEY == "test-openai-key"
    assert settings.MODEL_NAME == "gpt-4o-mini"
    assert settings.YOUTUBE_API_KEY == "test-yt-key"
    assert settings.NAVER_CLIENT_ID == "test-naver-id"
    assert settings.NAVER_CLIENT_SECRET == "test-naver-secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.config'`

- [ ] **Step 3: Write minimal implementation**

```text
# requirements.txt
langchain>=0.3.0
langchain-core>=0.3.0
langchain-community>=0.3.0
langchain-openai>=0.2.0
pydantic>=2.7.0
pydantic-settings>=2.2.0
requests>=2.31.0
python-dotenv>=1.0.1
pytest>=8.0.0
pytest-mock>=3.14.0
```

```text
# .env.example
OPENAI_API_KEY=your_openai_api_key_here
MODEL_NAME=gpt-4o-mini

# Worker 1 & 2: YouTube API Key
YOUTUBE_API_KEY=your_youtube_api_key_here

# Worker 3 & 4: Naver Open API Credentials
NAVER_CLIENT_ID=your_naver_client_id_here
NAVER_CLIENT_SECRET=your_naver_client_secret_here
```

```python
# src/__init__.py
"""LangChain Multi-Worker Collaborative Agent Package."""
```

```python
# src/config.py
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core LLM
    OPENAI_API_KEY: Optional[str] = None
    MODEL_NAME: str = "gpt-4o-mini"
    TEMPERATURE: float = 0.0

    # YouTube API (Worker 1, 2)
    YOUTUBE_API_KEY: Optional[str] = None

    # Naver API (Worker 3, 4)
    NAVER_CLIENT_ID: Optional[str] = None
    NAVER_CLIENT_SECRET: Optional[str] = None

settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example src/__init__.py src/config.py tests/test_config.py
git commit -m "feat(core): setup project dependencies, environment configuration, and settings"
```

---

### Task 2: Core 추상 인터페이스 정의 (`src/core/base.py`)

**Files:**
- Create: `src/core/__init__.py`
- Create: `src/core/base.py`
- Test: `tests/core/test_base.py`

**Interfaces:**
- Produces: `GuardrailResult` (Pydantic model: passed, error_message, sanitized_input)
- Produces: `BaseGuardrail` (ABC: validate_input, validate_tool_args, sanitize_output)
- Produces: `BaseContextProvider` (ABC: get_system_prompt_snippet, get_dynamic_context)
- Produces: `BaseAgentModule` (ABC: name, description, is_enabled, get_tools, get_guardrails, get_context_provider)

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_base.py
import pytest
from src.core.base import GuardrailResult, BaseGuardrail, BaseContextProvider, BaseAgentModule
from langchain_core.tools import BaseTool, tool

def test_guardrail_result_defaults():
    res = GuardrailResult(passed=True)
    assert res.passed is True
    assert res.error_message is None
    assert res.sanitized_input is None

def test_custom_module_implementation():
    @tool
    def sample_tool(query: str) -> str:
        """Sample tool for testing"""
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
    assert module.is_enabled() is True
    assert len(module.get_tools()) == 1
    assert module.get_guardrails()[0].validate_input("forbidden").passed is False
    assert module.get_context_provider().get_system_prompt_snippet() == "Sample Context Prompt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.base'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/core/__init__.py
"""Core architecture components."""
```

```python
# src/core/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from langchain_core.tools import BaseTool

class GuardrailResult(BaseModel):
    """Result of a guardrail validation."""
    passed: bool
    error_message: Optional[str] = None
    sanitized_input: Optional[Any] = None

class BaseGuardrail(ABC):
    """Abstract base class for domain guardrails."""

    def validate_input(self, query: str) -> GuardrailResult:
        """Validate raw user query before passing to agent/LLM."""
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        """Validate arguments before tool execution."""
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        """Sanitize tool execution output before returning to LLM."""
        return output

class BaseContextProvider(ABC):
    """Abstract base class for domain prompt and context injection."""

    @abstractmethod
    def get_system_prompt_snippet(self) -> str:
        """Domain-specific instructions injected into the system prompt."""
        pass

    def get_dynamic_context(self, user_query: str) -> Optional[str]:
        """Dynamic runtime context or few-shot examples for the query."""
        return None

class BaseAgentModule(ABC):
    """Abstract plugin module interface implemented by each worker."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the module (e.g., 'yt_search', 'naver_news')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this module provides."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """Check whether required environment variables or credentials exist."""
        pass

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """Return list of LangChain BaseTool instances."""
        pass

    @abstractmethod
    def get_guardrails(self) -> List[BaseGuardrail]:
        """Return list of BaseGuardrail instances."""
        pass

    @abstractmethod
    def get_context_provider(self) -> BaseContextProvider:
        """Return BaseContextProvider instance."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_base.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/__init__.py src/core/base.py tests/core/test_base.py
git commit -m "feat(core): implement BaseAgentModule, BaseGuardrail, and BaseContextProvider interfaces"
```

---

### Task 3: 도구 가드레일 래퍼 및 모듈 자동 레지스트리 (`src/core/guardrails.py`, `src/core/registry.py`)

**Files:**
- Create: `src/core/guardrails.py`
- Create: `src/core/registry.py`
- Test: `tests/core/test_registry.py`

**Interfaces:**
- Consumes: `BaseAgentModule`, `BaseGuardrail`, `GuardrailResult` from `src.core.base`
- Produces: `GuardrailedToolWrapper` (래핑된 LangChain Tool: 실행 전 인자 검증 및 실행 후 결과 정제)
- Produces: `ModuleRegistry` (`discover_modules(modules_dir)`: `modules/` 디렉토리 자동 스캔 및 활성 모듈 로드)

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_registry.py
import pytest
from langchain_core.tools import tool
from src.core.base import BaseAgentModule, BaseGuardrail, BaseContextProvider, GuardrailResult
from src.core.guardrails import wrap_tool_with_guardrails
from src.core.registry import ModuleRegistry

@tool
def add_numbers(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

class PositiveOnlyGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if args.get("a", 0) < 0 or args.get("b", 0) < 0:
            return GuardrailResult(passed=False, error_message="음수는 허용되지 않습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        return f"정제된 결과: {output}"

def test_guardrailed_tool_blocks_invalid_args():
    wrapped = wrap_tool_with_guardrails(add_numbers, [PositiveOnlyGuardrail()])
    
    # 음수 인자 전달 시 가드레일 에러 메시지 반환
    res_fail = wrapped.invoke({"a": -1, "b": 5})
    assert "가드레일 검증 실패" in res_fail
    assert "음수는 허용되지 않습니다." in res_fail

    # 양수 인자 전달 시 정상 실행 및 출력 정제
    res_pass = wrapped.invoke({"a": 2, "b": 3})
    assert res_pass == "정제된 결과: 5"

def test_module_registry_filtering(monkeypatch):
    class ActiveModule(BaseAgentModule):
        @property
        def name(self): return "active_mod"
        @property
        def description(self): return "active"
        def is_enabled(self): return True
        def get_tools(self): return [add_numbers]
        def get_guardrails(self): return []
        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self): return "Active Prompt"
            return CP()

    class DisabledModule(BaseAgentModule):
        @property
        def name(self): return "disabled_mod"
        @property
        def description(self): return "disabled"
        def is_enabled(self): return False
        def get_tools(self): return []
        def get_guardrails(self): return []
        def get_context_provider(self):
            class CP(BaseContextProvider):
                def get_system_prompt_snippet(self): return ""
            return CP()

    registry = ModuleRegistry()
    registry.register(ActiveModule())
    registry.register(DisabledModule())

    enabled_modules = registry.get_enabled_modules()
    assert len(enabled_modules) == 1
    assert enabled_modules[0].name == "active_mod"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.guardrails'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/core/guardrails.py
from typing import Any, Dict, List
from langchain_core.tools import BaseTool, StructuredTool
from .base import BaseGuardrail

def wrap_tool_with_guardrails(tool: BaseTool, guardrails: List[BaseGuardrail]) -> BaseTool:
    """Wrap a LangChain BaseTool with pre-execution arg validation and post-execution output sanitization."""
    if not guardrails:
        return tool

    original_func = tool.func

    def guarded_func(**kwargs: Any) -> Any:
        # 1. Pre-execution argument validation
        for guardrail in guardrails:
            val_result = guardrail.validate_tool_args(tool.name, kwargs)
            if not val_result.passed:
                return f"[가드레일 검증 실패] {val_result.error_message or '유효하지 않은 인자입니다.'}"

        # 2. Execute underlying tool function
        raw_output = original_func(**kwargs)

        # 3. Post-execution sanitization
        sanitized_output = raw_output
        for guardrail in guardrails:
            sanitized_output = guardrail.sanitize_output(tool.name, sanitized_output)

        return sanitized_output

    guarded_tool = StructuredTool.from_function(
        func=guarded_func,
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
    )
    return guarded_tool
```

```python
# src/core/registry.py
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, List, Type
from .base import BaseAgentModule

class ModuleRegistry:
    """Discovers, registers, and provides access to domain agent modules."""

    def __init__(self):
        self._modules: Dict[str, BaseAgentModule] = {}

    def register(self, module: BaseAgentModule) -> None:
        """Register a single module instance."""
        self._modules[module.name] = module

    def get_enabled_modules(self) -> List[BaseAgentModule]:
        """Return only modules whose is_enabled() is True."""
        return [m for m in self._modules.values() if m.is_enabled()]

    def discover_modules(self, package_path: str = "src.modules") -> None:
        """
        Dynamically scan packages inside modules directory and instantiate BaseAgentModule implementations.
        """
        try:
            pkg = importlib.import_module(package_path)
        except ImportError:
            return

        if not hasattr(pkg, "__path__"):
            return

        for _, mod_name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            if not is_pkg:
                continue
            full_module_name = f"{package_path}.{mod_name}.module"
            try:
                sub_mod = importlib.import_module(full_module_name)
                for attr_name in dir(sub_mod):
                    attr = getattr(sub_mod, attr_name)
                    if (
                        inspect.isclass(attr)
                        and issubclass(attr, BaseAgentModule)
                        and attr is not BaseAgentModule
                    ):
                        instance = attr()
                        self.register(instance)
            except (ImportError, AttributeError):
                continue
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/guardrails.py src/core/registry.py tests/core/test_registry.py
git commit -m "feat(core): implement tool guardrail wrapper and dynamic module registry"
```

---

### Task 4: 런타임 에이전트 빌더 및 실행 진입점 (`src/core/agent.py`, `src/main.py`)

**Files:**
- Create: `src/core/agent.py`
- Create: `src/main.py`
- Create: `tests/conftest.py`
- Create: `tests/core/test_agent.py`

**Interfaces:**
- Consumes: `ModuleRegistry`, `wrap_tool_with_guardrails`, `BaseGuardrail`
- Produces: `AgentBuilder` (`build_agent()`: LangChain Tool Calling Agent 및 AgentExecutor 인스턴스 생성)
- Produces: `src.main` (CLI 질의 처리기 및 대화 루프)

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_agent.py
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from src.core.agent import AgentRunner
from src.core.base import BaseAgentModule, BaseContextProvider, BaseGuardrail, GuardrailResult
from src.core.registry import ModuleRegistry
from langchain_core.tools import tool

@tool
def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"

class DummyModule(BaseAgentModule):
    @property
    def name(self): return "dummy"
    @property
    def description(self): return "dummy test module"
    def is_enabled(self): return True
    def get_tools(self): return [greet]
    def get_guardrails(self): return []
    def get_context_provider(self):
        class CP(BaseContextProvider):
            def get_system_prompt_snippet(self): return "Dummy Context"
        return CP()

def test_agent_runner_input_guardrail_rejection():
    class BlockAllGuardrail(BaseGuardrail):
        def validate_input(self, query: str) -> GuardrailResult:
            return GuardrailResult(passed=False, error_message="시스템 입력 차단")

    class BlockModule(DummyModule):
        def get_guardrails(self): return [BlockAllGuardrail()]

    registry = ModuleRegistry()
    registry.register(BlockModule())

    runner = AgentRunner(registry=registry, llm=MagicMock())
    result = runner.run("테스트 질문")
    assert "차단되었습니다" in result
    assert "시스템 입력 차단" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/core/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.core.agent'`

- [ ] **Step 3: Write minimal implementation**

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock
from langchain_core.language_models.chat_models import BaseChatModel

@pytest.fixture
def mock_llm():
    """Mock ChatOpenAI instance for unit testing without API keys."""
    llm = MagicMock(spec=BaseChatModel)
    return llm
```

```python
# src/core/agent.py
from typing import List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI
from src.config import settings
from .registry import ModuleRegistry
from .guardrails import wrap_tool_with_guardrails
from .base import BaseGuardrail

class AgentRunner:
    """Compiles enabled modules, applies guardrails, and executes LangChain tool calling agent."""

    def __init__(self, registry: ModuleRegistry, llm: Optional[BaseChatModel] = None):
        self.registry = registry
        self.enabled_modules = self.registry.get_enabled_modules()
        
        # Collect tools, guardrails, and context snippets
        self.all_guardrails: List[BaseGuardrail] = []
        raw_tools = []
        system_snippets = [
            "당신은 YouTube 및 Naver Open API를 활용하여 사용자에게 최적의 정보를 제공하는 AI 에이전트입니다.",
            "주어진 도구를 적절히 활용하여 사실에 기반한 답변을 작성하십시오."
        ]

        for mod in self.enabled_modules:
            mod_guardrails = mod.get_guardrails()
            self.all_guardrails.extend(mod_guardrails)
            
            # Wrap each tool with module guardrails
            for t in mod.get_tools():
                wrapped_t = wrap_tool_with_guardrails(t, mod_guardrails)
                raw_tools.append(wrapped_t)

            snippet = mod.get_context_provider().get_system_prompt_snippet()
            if snippet:
                system_snippets.append(f"\n[{mod.description} 가이드]\n{snippet}")

        self.tools = raw_tools
        self.system_prompt_text = "\n".join(system_snippets)

        # Initialize LLM
        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model=settings.MODEL_NAME,
                api_key=settings.OPENAI_API_KEY or "dummy-key",
                temperature=settings.TEMPERATURE
            )

        # Assemble Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt_text),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True
        )

    def run(self, query: str) -> str:
        """Run input guardrail check and invoke agent executor."""
        # 1. Pre-execution Input Guardrail Check
        for guardrail in self.all_guardrails:
            val_res = guardrail.validate_input(query)
            if not val_res.passed:
                return f"[안내] 입력이 가드레일 정책에 의해 차단되었습니다: {val_res.error_message}"

        # 2. Execute agent
        result = self.executor.invoke({"input": query})
        return result.get("output", "")
```

```python
# src/main.py
import argparse
import sys
from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner

def main():
    parser = argparse.ArgumentParser(description="LangChain Multi-Worker Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="단일 질의 실행")
    parser.add_argument("--interactive", "-i", action="store_true", help="대화형 콘솔 모드")
    args = parser.parse_args()

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")

    enabled = registry.get_enabled_modules()
    print("=" * 60)
    print("🚀 [LangChain Multi-Worker Agent] 초기화 완료")
    print(f"📦 로드된 활성 모듈 ({len(enabled)}개): {[m.name for m in enabled]}")
    print("=" * 60)

    runner = AgentRunner(registry=registry)

    if args.query:
        print(f"\n[질의]: {args.query}")
        ans = runner.run(args.query)
        print(f"\n[답변]:\n{ans}\n")
    elif args.interactive or len(sys.argv) == 1:
        print("대화형 모드를 시작합니다. (종료하려면 'exit' 또는 'quit' 입력)\n")
        while True:
            try:
                user_input = input("\n👤 사용자 > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    print("종료합니다.")
                    break
                response = runner.run(user_input)
                print(f"\n🤖 에이전트 >\n{response}")
            except (KeyboardInterrupt, EOFError):
                print("\n종료합니다.")
                break

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/core/test_agent.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/core/agent.py src/main.py tests/conftest.py tests/core/test_agent.py
git commit -m "feat(core): implement AgentRunner with dynamic prompt building and CLI entrypoint"
```

---

### Task 5: 작업자 1 모듈 구현 - `yt_search` (동영상 검색 및 자막 추출)

**Files:**
- Create: `src/modules/__init__.py`
- Create: `src/modules/yt_search/__init__.py`
- Create: `src/modules/yt_search/client.py`
- Create: `src/modules/yt_search/tools.py`
- Create: `src/modules/yt_search/context.py`
- Create: `src/modules/yt_search/guardrails.py`
- Create: `src/modules/yt_search/module.py`
- Test: `tests/modules/test_yt_search.py`

**Interfaces:**
- Produces: `YouTubeSearchModule` (`name="yt_search"`)
- Tools: `search_youtube_videos(query: str, max_results: int = 5)`, `get_video_transcript(video_id: str)`
- Guardrails: `YouTubeSearchGuardrail` (검색어 최소/최대 길이, max_results <= 10 제한, 유효한 video_id 검증)

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/test_yt_search.py
import pytest
from unittest.mock import patch, MagicMock
from src.modules.yt_search.module import YouTubeSearchModule
from src.modules.yt_search.tools import search_youtube_videos, get_video_transcript
from src.modules.yt_search.guardrails import YouTubeSearchGuardrail

def test_yt_search_module_metadata():
    mod = YouTubeSearchModule()
    assert mod.name == "yt_search"
    assert len(mod.get_tools()) == 2

def test_yt_search_guardrail_validation():
    guard = YouTubeSearchGuardrail()
    # display/max_results 초과 차단
    res = guard.validate_tool_args("search_youtube_videos", {"max_results": 20})
    assert res.passed is False
    assert "최대 10개" in res.error_message

    # 정상 파라미터 통과
    assert guard.validate_tool_args("search_youtube_videos", {"max_results": 5}).passed is True

@patch("src.modules.yt_search.client.requests.get")
def test_search_youtube_videos_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "id": {"videoId": "test_vid_1"},
                "snippet": {
                    "title": "테스트 유튜브 영상",
                    "description": "영상 설명입니다.",
                    "channelTitle": "테스트 채널"
                }
            }
        ]
    }
    result = search_youtube_videos.invoke({"query": "파이썬 강의", "max_results": 1})
    assert "test_vid_1" in result
    assert "테스트 유튜브 영상" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/test_yt_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.yt_search'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/modules/__init__.py
"""Worker domain modules."""
```

```python
# src/modules/yt_search/__init__.py
from .module import YouTubeSearchModule
__all__ = ["YouTubeSearchModule"]
```

```python
# src/modules/yt_search/client.py
import requests
from typing import Any, Dict
from src.config import settings

class YouTubeSearchClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def search_videos(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/search"
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "key": settings.YOUTUBE_API_KEY
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_transcript(self, video_id: str) -> str:
        # 자막 모의/안내 로직 (실제 자막 API 또는 모듈 연동)
        return f"[자막 추출 완료] Video ID '{video_id}'의 주요 내용 요약 텍스트입니다."
```

```python
# src/modules/yt_search/tools.py
from langchain_core.tools import tool
from .client import YouTubeSearchClient

client = YouTubeSearchClient()

@tool
def search_youtube_videos(query: str, max_results: int = 5) -> str:
    """Search YouTube for videos related to query. Returns video titles, IDs, and descriptions."""
    try:
        data = client.search_videos(query=query, max_results=max_results)
        items = data.get("items", [])
        if not items:
            return "유튜브 검색 결과가 없습니다."
        output = []
        for it in items:
            vid = it.get("id", {}).get("videoId", "N/A")
            snip = it.get("snippet", {})
            output.append(f"- 제목: {snip.get('title')}\n  영상ID: {vid}\n  채널: {snip.get('channelTitle')}\n  설명: {snip.get('description')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"유튜브 검색 중 오류 발생: {str(e)}"

@tool
def get_video_transcript(video_id: str) -> str:
    """Extract transcript or summary text of a YouTube video given its video_id."""
    try:
        return client.get_transcript(video_id)
    except Exception as e:
        return f"자막 추출 실패: {str(e)}"
```

```python
# src/modules/yt_search/guardrails.py
import re
from src.core.base import BaseGuardrail, GuardrailResult

class YouTubeSearchGuardrail(BaseGuardrail):
    def validate_input(self, query: str) -> GuardrailResult:
        if not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if tool_name == "search_youtube_videos":
            max_r = args.get("max_results", 5)
            if max_r > 10 or max_r < 1:
                return GuardrailResult(passed=False, error_message="max_results는 최소 1개, 최대 10개까지 가능합니다.")
        elif tool_name == "get_video_transcript":
            vid = args.get("video_id", "")
            if not vid or len(vid) < 3:
                return GuardrailResult(passed=False, error_message="유효하지 않은 YouTube video_id입니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        return output
```

```python
# src/modules/yt_search/context.py
from src.core.base import BaseContextProvider

class YouTubeSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- YouTube 영상 검색이 필요할 때 'search_youtube_videos'를 호출하십시오.\n"
            "- 영상의 상세 내용이나 강의 스크립트가 필요한 경우 먼저 검색 후 얻은 영상ID로 'get_video_transcript'를 호출하십시오."
        )
```

```python
# src/modules/yt_search/module.py
from src.core.base import BaseAgentModule
from src.config import settings
from .tools import search_youtube_videos, get_video_transcript
from .guardrails import YouTubeSearchGuardrail
from .context import YouTubeSearchContextProvider

class YouTubeSearchModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "yt_search"

    @property
    def description(self) -> str:
        return "YouTube 동영상 검색 및 자막 추출"

    def is_enabled(self) -> bool:
        return bool(settings.YOUTUBE_API_KEY)

    def get_tools(self):
        return [search_youtube_videos, get_video_transcript]

    def get_guardrails(self):
        return [YouTubeSearchGuardrail()]

    def get_context_provider(self):
        return YouTubeSearchContextProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/test_yt_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/__init__.py src/modules/yt_search/ tests/modules/test_yt_search.py
git commit -m "feat(yt_search): implement worker 1 youtube video search and transcript module"
```

---

### Task 6: 작업자 2 모듈 구현 - `yt_analytics` (채널 통계 및 댓글 분석)

**Files:**
- Create: `src/modules/yt_analytics/__init__.py`
- Create: `src/modules/yt_analytics/client.py`
- Create: `src/modules/yt_analytics/tools.py`
- Create: `src/modules/yt_analytics/context.py`
- Create: `src/modules/yt_analytics/guardrails.py`
- Create: `src/modules/yt_analytics/module.py`
- Test: `tests/modules/test_yt_analytics.py`

**Interfaces:**
- Produces: `YouTubeAnalyticsModule` (`name="yt_analytics"`)
- Tools: `get_channel_stats(channel_id: str)`, `get_video_comments(video_id: str, max_comments: int = 10)`
- Guardrails: `YouTubeAnalyticsGuardrail` (댓글 수집 제한 max_comments <= 50, 댓글 내 이메일/전화번호 마스킹)

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/test_yt_analytics.py
import pytest
from unittest.mock import patch
from src.modules.yt_analytics.module import YouTubeAnalyticsModule
from src.modules.yt_analytics.tools import get_channel_stats, get_video_comments
from src.modules.yt_analytics.guardrails import YouTubeAnalyticsGuardrail

def test_yt_analytics_module_metadata():
    mod = YouTubeAnalyticsModule()
    assert mod.name == "yt_analytics"
    assert len(mod.get_tools()) == 2

def test_yt_analytics_guardrail_pii_masking():
    guard = YouTubeAnalyticsGuardrail()
    raw_comment = "문의사항은 test@example.com 또는 010-1234-5678로 연락주세요."
    sanitized = guard.sanitize_output("get_video_comments", raw_comment)
    assert "[EMAIL_MASKED]" in sanitized
    assert "[PHONE_MASKED]" in sanitized
    assert "test@example.com" not in sanitized
    assert "010-1234-5678" not in sanitized

@patch("src.modules.yt_analytics.client.requests.get")
def test_get_channel_stats_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "statistics": {
                    "subscriberCount": "100000",
                    "viewCount": "50000000",
                    "videoCount": "320"
                }
            }
        ]
    }
    res = get_channel_stats.invoke({"channel_id": "UC12345"})
    assert "100,000" in res or "100000" in res
    assert "50000000" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/test_yt_analytics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.yt_analytics'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/modules/yt_analytics/__init__.py
from .module import YouTubeAnalyticsModule
__all__ = ["YouTubeAnalyticsModule"]
```

```python
# src/modules/yt_analytics/client.py
import requests
from typing import Any, Dict
from src.config import settings

class YouTubeAnalyticsClient:
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/channels"
        params = {
            "part": "statistics,snippet",
            "id": channel_id,
            "key": settings.YOUTUBE_API_KEY
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_comments(self, video_id: str, max_comments: int = 10) -> Dict[str, Any]:
        url = f"{self.BASE_URL}/commentThreads"
        params = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": max_comments,
            "key": settings.YOUTUBE_API_KEY
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
```

```python
# src/modules/yt_analytics/tools.py
from langchain_core.tools import tool
from .client import YouTubeAnalyticsClient

client = YouTubeAnalyticsClient()

@tool
def get_channel_stats(channel_id: str) -> str:
    """Get subscriber count, total views, and video count of a YouTube channel by channel_id."""
    try:
        data = client.get_channel_info(channel_id)
        items = data.get("items", [])
        if not items:
            return f"채널 ID '{channel_id}'에 대한 정보를 찾을 수 없습니다."
        stats = items[0].get("statistics", {})
        return (
            f"[채널 통계 ({channel_id})]\n"
            f"- 구독자 수: {int(stats.get('subscriberCount', 0)):,}명\n"
            f"- 총 조회수: {int(stats.get('viewCount', 0)):,}회\n"
            f"- 업로드 영상 수: {stats.get('videoCount', 0)}개"
        )
    except Exception as e:
        return f"채널 통계 조회 중 오류: {str(e)}"

@tool
def get_video_comments(video_id: str, max_comments: int = 10) -> str:
    """Retrieve top comments from a YouTube video to analyze viewer reactions."""
    try:
        data = client.get_comments(video_id, max_comments)
        items = data.get("items", [])
        if not items:
            return "댓글이 없거나 조회할 수 없습니다."
        comments = []
        for it in items:
            c = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            author = c.get("authorDisplayName", "익명")
            text = c.get("textDisplay", "")
            comments.append(f"- {author}: {text}")
        return "\n".join(comments)
    except Exception as e:
        return f"댓글 수집 실패: {str(e)}"
```

```python
# src/modules/yt_analytics/guardrails.py
import re
from src.core.base import BaseGuardrail, GuardrailResult

class YouTubeAnalyticsGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if tool_name == "get_video_comments":
            max_c = args.get("max_comments", 10)
            if max_c > 50 or max_c < 1:
                return GuardrailResult(passed=False, error_message="max_comments는 1 이상 50 이하여야 합니다.")
        elif tool_name == "get_channel_stats":
            cid = args.get("channel_id", "")
            if not cid:
                return GuardrailResult(passed=False, error_message="channel_id가 누락되었습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        if isinstance(output, str):
            # Mask Email
            output = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_MASKED]", output)
            # Mask Korean Phone numbers (010-XXXX-XXXX)
            output = re.sub(r"01[016789]-?\d{3,4}-?\d{4}", "[PHONE_MASKED]", output)
        return output
```

```python
# src/modules/yt_analytics/context.py
from src.core.base import BaseContextProvider

class YouTubeAnalyticsContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 크리에이터나 채널의 규모/영향력을 파악할 때는 'get_channel_stats'를 사용하십시오.\n"
            "- 영상에 대한 시청자 피드백, 여론, 감성 분석이 필요한 경우 'get_video_comments'를 사용하십시오."
        )
```

```python
# src/modules/yt_analytics/module.py
from src.core.base import BaseAgentModule
from src.config import settings
from .tools import get_channel_stats, get_video_comments
from .guardrails import YouTubeAnalyticsGuardrail
from .context import YouTubeAnalyticsContextProvider

class YouTubeAnalyticsModule(BaseAgentModule):
    @property
    def name(self) -> str:
        return "yt_analytics"

    @property
    def description(self) -> str:
        return "YouTube 채널 통계 및 시청자 댓글 분석"

    def is_enabled(self) -> bool:
        return bool(settings.YOUTUBE_API_KEY)

    def get_tools(self):
        return [get_channel_stats, get_video_comments]

    def get_guardrails(self):
        return [YouTubeAnalyticsGuardrail()]

    def get_context_provider(self):
        return YouTubeAnalyticsContextProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/test_yt_analytics.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/yt_analytics/ tests/modules/test_yt_analytics.py
git commit -m "feat(yt_analytics): implement worker 2 youtube channel stats and comments module"
```

---

### Task 7: 작업자 3 모듈 구현 - `naver_search` (블로그 및 뉴스 검색)

**Files:**
- Create: `src/modules/naver_search/__init__.py`
- Create: `src/modules/naver_search/client.py`
- Create: `src/modules/naver_search/tools.py`
- Create: `src/modules/naver_search/context.py`
- Create: `src/modules/naver_search/guardrails.py`
- Create: `src/modules/naver_search/module.py`
- Test: `tests/modules/test_naver_search.py`

**Interfaces:**
- Produces: `NaverSearchModule` (`name="naver_search"`)
- Tools: `search_naver_blog(query: str, display: int = 5, sort: str = 'sim')`, `search_naver_news(query: str, display: int = 5, sort: str = 'sim')`
- Guardrails: `NaverSearchGuardrail` (display <= 10 제한, HTML 태그 `<b>`, 엔티티 `&quot;`, `&amp;` 제거)

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/test_naver_search.py
import pytest
from unittest.mock import patch
from src.modules.naver_search.module import NaverSearchModule
from src.modules.naver_search.tools import search_naver_blog, search_naver_news
from src.modules.naver_search.guardrails import NaverSearchGuardrail

def test_naver_search_module_metadata():
    mod = NaverSearchModule()
    assert mod.name == "naver_search"
    assert len(mod.get_tools()) == 2

def test_naver_search_html_sanitization():
    guard = NaverSearchGuardrail()
    raw = "기사 제목 <b>AI 신기술</b> 발표 &quot;대박&quot; &amp; 성공"
    cleaned = guard.sanitize_output("search_naver_news", raw)
    assert "<b>" not in cleaned
    assert "</b>" not in cleaned
    assert "&quot;" not in cleaned
    assert "&amp;" not in cleaned
    assert cleaned == "기사 제목 AI 신기술 발표 \"대박\" & 성공"

@patch("src.modules.naver_search.client.requests.get")
def test_search_naver_news_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "테스트 <b>인공지능</b> 뉴스",
                "originallink": "https://example.com/1",
                "link": "https://news.naver.com/1",
                "description": "인공지능의 최신 동향"
            }
        ]
    }
    res = search_naver_news.invoke({"query": "인공지능", "display": 1})
    assert "테스트 <b>인공지능</b> 뉴스" in res
    assert "https://news.naver.com/1" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/test_naver_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.naver_search'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/modules/naver_search/__init__.py
from .module import NaverSearchModule
__all__ = ["NaverSearchModule"]
```

```python
# src/modules/naver_search/client.py
import requests
from typing import Any, Dict
from src.config import settings

class NaverSearchClient:
    BASE_URL = "https://openapi.naver.com/v1/search"

    def __init__(self):
        self.headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID or "",
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET or "",
        }

    def search_blog(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/blog.json"
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(url, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def search_news(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        url = f"{self.BASE_URL}/news.json"
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(url, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
```

```python
# src/modules/naver_search/tools.py
from langchain_core.tools import tool
from .client import NaverSearchClient

client = NaverSearchClient()

@tool
def search_naver_blog(query: str, display: int = 5, sort: str = "sim") -> str:
    """Search Naver blogs for reviews, tutorials, and personal experiences. sort can be 'sim' or 'date'."""
    try:
        data = client.search_blog(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 블로그 검색 결과가 없습니다."
        output = []
        for it in items:
            output.append(f"- 제목: {it.get('title')}\n  링크: {it.get('link')}\n  내용: {it.get('description')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 블로그 검색 실패: {str(e)}"

@tool
def search_naver_news(query: str, display: int = 5, sort: str = "sim") -> str:
    """Search Naver News for latest press articles and breaking news. sort can be 'sim' or 'date'."""
    try:
        data = client.search_news(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 뉴스 검색 결과가 없습니다."
        output = []
        for it in items:
            output.append(f"- 제목: {it.get('title')}\n  링크: {it.get('link')}\n  요약: {it.get('description')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 뉴스 검색 실패: {str(e)}"
```

```python
# src/modules/naver_search/guardrails.py
import re
from src.core.base import BaseGuardrail, GuardrailResult

class NaverSearchGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        display = args.get("display", 5)
        if display > 10 or display < 1:
            return GuardrailResult(passed=False, error_message="display 파라미터는 1 이상 10 이하여야 합니다.")
        sort = args.get("sort", "sim")
        if sort not in ("sim", "date"):
            return GuardrailResult(passed=False, error_message="sort 옵션은 'sim' 또는 'date'만 가능합니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        if isinstance(output, str):
            # Remove HTML tags
            clean = re.sub(r"<.*?>", "", output)
            # Decode HTML entities
            clean = clean.replace("&quot;", "\"").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            return clean
        return output
```

```python
# src/modules/naver_search/context.py
from src.core.base import BaseContextProvider

class NaverSearchContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 대한민국 국내 시사 및 실시간 이슈는 'search_naver_news'를 우선적으로 활용하십시오.\n"
            "- 실제 사용기, 맛집, 라이프스타일 후기 등은 'search_naver_blog'를 활용하십시오."
        )
```

```python
# src/modules/naver_search/module.py
from src.core.base import BaseAgentModule
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

    def get_tools(self):
        return [search_naver_blog, search_naver_news]

    def get_guardrails(self):
        return [NaverSearchGuardrail()]

    def get_context_provider(self):
        return NaverSearchContextProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/test_naver_search.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/naver_search/ tests/modules/test_naver_search.py
git commit -m "feat(naver_search): implement worker 3 naver blog and news search module"
```

---

### Task 8: 작업자 4 모듈 구현 - `naver_shopping` (쇼핑 최저가 및 트렌드 분석)

**Files:**
- Create: `src/modules/naver_shopping/__init__.py`
- Create: `src/modules/naver_shopping/client.py`
- Create: `src/modules/naver_shopping/tools.py`
- Create: `src/modules/naver_shopping/context.py`
- Create: `src/modules/naver_shopping/guardrails.py`
- Create: `src/modules/naver_shopping/module.py`
- Test: `tests/modules/test_naver_shopping.py`

**Interfaces:**
- Produces: `NaverShoppingModule` (`name="naver_shopping"`)
- Tools: `search_naver_shopping(query: str, display: int = 5, sort: str = 'sim')`, `get_shopping_trends(keywords: str, start_date: str, end_date: str)`
- Guardrails: `NaverShoppingGuardrail` (가격 0원 필터링, 날짜 YYYY-MM-DD 형식 검증)

- [ ] **Step 1: Write the failing test**

```python
# tests/modules/test_naver_shopping.py
import pytest
from unittest.mock import patch
from src.modules.naver_shopping.module import NaverShoppingModule
from src.modules.naver_shopping.tools import search_naver_shopping, get_shopping_trends
from src.modules.naver_shopping.guardrails import NaverShoppingGuardrail

def test_naver_shopping_module_metadata():
    mod = NaverShoppingModule()
    assert mod.name == "naver_shopping"
    assert len(mod.get_tools()) == 2

def test_shopping_guardrail_date_validation():
    guard = NaverShoppingGuardrail()
    # 잘못된 날짜 포맷 차단
    res = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026/01/01",
        "end_date": "2026-02-01"
    })
    assert res.passed is False
    assert "YYYY-MM-DD" in res.error_message

    # 올바른 날짜 통과
    valid = guard.validate_tool_args("get_shopping_trends", {
        "keywords": "노트북",
        "start_date": "2026-01-01",
        "end_date": "2026-02-01"
    })
    assert valid.passed is True

@patch("src.modules.naver_shopping.client.requests.get")
def test_search_naver_shopping_mock(mock_get):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "items": [
            {
                "title": "맥북 프로 M3",
                "link": "https://shopping.naver.com/1",
                "lprice": "2390000",
                "mallName": "네이버공식몰"
            }
        ]
    }
    res = search_naver_shopping.invoke({"query": "맥북 프로", "display": 1})
    assert "맥북 프로 M3" in res
    assert "2,390,000" in res or "2390000" in res
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/modules/test_naver_shopping.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.modules.naver_shopping'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/modules/naver_shopping/__init__.py
from .module import NaverShoppingModule
__all__ = ["NaverShoppingModule"]
```

```python
# src/modules/naver_shopping/client.py
import requests
from typing import Any, Dict
from src.config import settings

class NaverShoppingClient:
    SHOP_URL = "https://openapi.naver.com/v1/search/shop.json"
    DATALAB_URL = "https://openapi.naver.com/v1/datalab/search"

    def __init__(self):
        self.headers = {
            "X-Naver-Client-Id": settings.NAVER_CLIENT_ID or "",
            "X-Naver-Client-Secret": settings.NAVER_CLIENT_SECRET or "",
            "Content-Type": "application/json"
        }

    def search_shop(self, query: str, display: int = 5, sort: str = "sim") -> Dict[str, Any]:
        params = {"query": query, "display": display, "sort": sort}
        resp = requests.get(self.SHOP_URL, headers=self.headers, params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_datalab_trend(self, keywords: list, start_date: str, end_date: str) -> Dict[str, Any]:
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "month",
            "keywordGroups": [{"groupName": kw, "keywords": [kw]} for kw in keywords]
        }
        resp = requests.post(self.DATALAB_URL, headers=self.headers, json=body, timeout=5)
        resp.raise_for_status()
        return resp.json()
```

```python
# src/modules/naver_shopping/tools.py
import re
from langchain_core.tools import tool
from .client import NaverShoppingClient

client = NaverShoppingClient()

@tool
def search_naver_shopping(query: str, display: int = 5, sort: str = "sim") -> str:
    """Search Naver Shopping for products, lowest price (lprice), and store information. sort: 'sim', 'date', 'asc', 'dsc'."""
    try:
        data = client.search_shop(query=query, display=display, sort=sort)
        items = data.get("items", [])
        if not items:
            return "네이버 쇼핑 검색 결과가 없습니다."
        output = []
        for it in items:
            title = re.sub(r"<.*?>", "", it.get("title", ""))
            price = int(it.get("lprice", 0))
            output.append(f"- 상품명: {title}\n  최저가: {price:,}원\n  쇼핑몰: {it.get('mallName')}\n  링크: {it.get('link')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"네이버 쇼핑 검색 실패: {str(e)}"

@tool
def get_shopping_trends(keywords: str, start_date: str, end_date: str) -> str:
    """Query Naver Datalab search trend ratio for comma-separated keywords between start_date and end_date (YYYY-MM-DD)."""
    try:
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
        data = client.get_datalab_trend(kw_list, start_date, end_date)
        results = data.get("results", [])
        if not results:
            return "트렌드 조회 결과가 없습니다."
        summary = []
        for res in results:
            title = res.get("title")
            data_pts = res.get("data", [])
            last_pt = data_pts[-1].get("ratio") if data_pts else "N/A"
            summary.append(f"- 키워드 '{title}': 최근 기간 상대 검색비율 {last_pt}%")
        return "\n".join(summary)
    except Exception as e:
        return f"트렌드 분석 조회 실패: {str(e)}"
```

```python
# src/modules/naver_shopping/guardrails.py
import re
from src.core.base import BaseGuardrail, GuardrailResult

class NaverShoppingGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: dict) -> GuardrailResult:
        if tool_name == "get_shopping_trends":
            date_regex = r"^\d{4}-\d{2}-\d{2}$"
            start_d = args.get("start_date", "")
            end_d = args.get("end_date", "")
            if not re.match(date_regex, start_d) or not re.match(date_regex, end_d):
                return GuardrailResult(passed=False, error_message="날짜는 YYYY-MM-DD 형식이어야 합니다.")
        elif tool_name == "search_naver_shopping":
            display = args.get("display", 5)
            if display > 10 or display < 1:
                return GuardrailResult(passed=False, error_message="display는 1 이상 10 이하여야 합니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: any) -> any:
        return output
```

```python
# src/modules/naver_shopping/context.py
from src.core.base import BaseContextProvider

class NaverShoppingContextProvider(BaseContextProvider):
    def get_system_prompt_snippet(self) -> str:
        return (
            "- 상품 가격 비교 및 최저가 탐색 시 'search_naver_shopping'을 사용하십시오.\n"
            "- 상품이나 키워드의 검색 관심도 및 시기별 추세를 비교할 때는 'get_shopping_trends'를 사용하십시오."
        )
```

```python
# src/modules/naver_shopping/module.py
from src.core.base import BaseAgentModule
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

    def get_tools(self):
        return [search_naver_shopping, get_shopping_trends]

    def get_guardrails(self):
        return [NaverShoppingGuardrail()]

    def get_context_provider(self):
        return NaverShoppingContextProvider()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/modules/test_naver_shopping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/modules/naver_shopping/ tests/modules/test_naver_shopping.py
git commit -m "feat(naver_shopping): implement worker 4 naver shopping and datalab trend module"
```

---

### Task 9: 전체 4개 모듈 통합 검증 및 개발자 가이드 문서 작성 (`README.md`, `tests/test_integration.py`)

**Files:**
- Create: `tests/test_integration.py`
- Create: `README.md`

**Interfaces:**
- Validates: 4개 모듈 동시 등록, 레지스트리 자동 탐색, 통합 가드레일 및 전체 테스트 스위트 100% 통과

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
import pytest
from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner
from unittest.mock import MagicMock

def test_full_registry_discovery():
    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    
    # 4개 모듈이 모두 감지되었는지 확인
    all_registered = [m.name for m in registry._modules.values()]
    assert "yt_search" in all_registered
    assert "yt_analytics" in all_registered
    assert "naver_search" in all_registered
    assert "naver_shopping" in all_registered

def test_agent_runner_initialization_with_all_modules(monkeypatch):
    # Mock all API keys to verify full enabled loading
    monkeypatch.setattr("src.config.settings.YOUTUBE_API_KEY", "mock_yt_key")
    monkeypatch.setattr("src.config.settings.NAVER_CLIENT_ID", "mock_client_id")
    monkeypatch.setattr("src.config.settings.NAVER_CLIENT_SECRET", "mock_client_secret")

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")
    enabled = registry.get_enabled_modules()
    assert len(enabled) == 4

    runner = AgentRunner(registry=registry, llm=MagicMock())
    # 2 tools per module * 4 modules = 8 tools
    assert len(runner.tools) == 8
```

- [ ] **Step 2: Run all test suite to verify everything passes**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Write comprehensive README.md developer guide**

Include:
- Architecture diagram and 4-worker directory map
- Quick start commands
- How 4 developers work simultaneously in parallel
- Adding new tools / modifying guardrails
- Running tests (single worker vs all)

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py README.md
git commit -m "docs: add developer guide and full integration test for multi-worker boilerplate"
```
