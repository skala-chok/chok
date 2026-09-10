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
