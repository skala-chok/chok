from typing import List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

try:
    from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
except ImportError:  # pragma: no cover
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
            "주어진 도구를 적절히 활용하여 사실에 기반한 답변을 작성하십시오.",
        ]

        for mod in self.enabled_modules:
            mod_guardrails = mod.get_guardrails()
            self.all_guardrails.extend(mod_guardrails)

            # Wrap each tool with module guardrails
            for t in mod.get_tools():
                wrapped_t = wrap_tool_with_guardrails(t, mod_guardrails)
                raw_tools.append(wrapped_t)

            context_provider = mod.get_context_provider()
            if context_provider:
                snippet = context_provider.get_system_prompt_snippet()
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
                temperature=settings.TEMPERATURE,
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
            handle_parsing_errors=True,
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
        if isinstance(result, dict):
            return result.get("output", "")
        return str(result)


AgentBuilder = AgentRunner
