import logging
import time
from typing import Any, Callable, Dict, List, Optional
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
from .scenario import BaseScenario
from .scenario_registry import ScenarioRegistry
from .router import ScenarioRouter

logger = logging.getLogger(__name__)


class AgentRunner:
    """Compiles enabled modules, applies guardrails, and executes scenarios or LangChain tool calling agent."""

    def __init__(
        self,
        registry: ModuleRegistry,
        llm: Optional[BaseChatModel] = None,
        scenario_registry: Optional[ScenarioRegistry] = None,
        router: Optional[ScenarioRouter] = None,
    ):
        self.registry = registry
        self.enabled_modules = self.registry.get_enabled_modules()
        all_modules = self.registry.get_all_modules()
        disabled_modules = [m for m in all_modules if not m.is_enabled()]
        if disabled_modules:
            logger.info(
                "비활성화된 모듈 (%d개): %s (필수 API 키/설정 미부여)",
                len(disabled_modules),
                [m.name for m in disabled_modules],
            )

        # Collect tools, guardrails, and context snippets
        self.all_guardrails: List[BaseGuardrail] = []
        raw_tools = []
        self.tools_map = {}
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
                self.tools_map[wrapped_t.name] = wrapped_t

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
            llm_kwargs: Dict[str, Any] = {
                "model": settings.MODEL_NAME,
                "api_key": settings.OPENAI_API_KEY or "dummy-key",
                "temperature": settings.TEMPERATURE,
            }
            if any(p in settings.MODEL_NAME for p in ("gpt-5", "o1", "o3")):
                llm_kwargs["reasoning_effort"] = "none"
            self.llm = ChatOpenAI(**llm_kwargs)

        # Assemble Scenario Registry & Router
        if scenario_registry is not None:
            self.scenario_registry = scenario_registry
        else:
            self.scenario_registry = ScenarioRegistry()
            self.scenario_registry.discover_scenarios("src.scenarios")

        if router is not None:
            self.router = router
        elif len(self.scenario_registry) > 0:
            self.router = ScenarioRouter(registry=self.scenario_registry, llm=self.llm)
        else:
            self.router = None

        # Assemble Prompt for Fallback General Agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt_text),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create Fallback General Agent
        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        self.executor = AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True,
        )

    def run(
        self,
        query: str,
        callbacks: Optional[List[Any]] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Run input guardrail check, route to scenario chain if matched, or fallback to agent executor."""
        # 1. Pre-execution Input Guardrail Check
        for guardrail in self.all_guardrails:
            val_res = guardrail.validate_input(query)
            if not val_res.passed:
                logger.warning(
                    "[사전 가드레일 차단] 가드레일: %s | 사유: %s | 질의: '%s'",
                    type(guardrail).__name__,
                    val_res.error_message,
                    query,
                )
                if on_status:
                    on_status(f"🛑 [사전 가드레일 차단] {val_res.error_message}")
                return f"[안내] 입력이 가드레일 정책에 의해 차단되었습니다: {val_res.error_message}"

        # 2. Intelligent Scenario Routing
        if self.router and len(self.scenario_registry) > 0:
            try:
                plan = self.router.route(query)
                if plan and plan.scenario_name in self.scenario_registry:
                    scenario: BaseScenario = self.scenario_registry[plan.scenario_name]
                    logger.info("선택된 시나리오 체인 실행: %s", scenario.name)
                    if on_status:
                        on_status(
                            f"🎯 **[시나리오 라우터 판정]** `{scenario.name}` 자동 매칭 (신뢰도: {plan.confidence:.2f})"
                        )

                    # Filter required tools for this scenario
                    scenario_tools = {}
                    if scenario.required_tool_names:
                        for t_name in scenario.required_tool_names:
                            if t_name in self.tools_map:
                                scenario_tools[t_name] = self.tools_map[t_name]
                    else:
                        scenario_tools = dict(self.tools_map)

                    # Wrap tools with real-time on_status reporting if hook provided
                    if on_status:
                        reporting_tools = {}
                        for t_name, original_tool in scenario_tools.items():
                            class _ReportingToolWrapper:
                                def __init__(self, inner, name, reporter):
                                    self._inner = inner
                                    self.name = name
                                    self._reporter = reporter
                                    self.description = getattr(inner, "description", "")
                                    self.args_schema = getattr(inner, "args_schema", None)

                                def invoke(self, input_args, *args, **kwargs):
                                    self._reporter(
                                        f"🔧 **[도구 실행]** `{self.name}`\n- 파라미터: `{input_args}`"
                                    )
                                    t0 = time.time()
                                    try:
                                        res = self._inner.invoke(input_args, *args, **kwargs)
                                        el = time.time() - t0
                                        res_str = str(res)
                                        preview = res_str[:120] + "..." if len(res_str) > 120 else res_str
                                        self._reporter(
                                            f"✅ **[도구 완료]** `{self.name}` ({el:.2f}초)\n> {preview}"
                                        )
                                        return res
                                    except Exception as e_tool:
                                        el = time.time() - t0
                                        self._reporter(
                                            f"❌ **[도구 오류]** `{self.name}` ({el:.2f}초): {e_tool}"
                                        )
                                        raise

                                def __call__(self, *args, **kwargs):
                                    return self.invoke(*args, **kwargs)

                            reporting_tools[t_name] = _ReportingToolWrapper(
                                original_tool, t_name, on_status
                            )
                        scenario_tools_to_inject = reporting_tools
                    else:
                        scenario_tools_to_inject = scenario_tools

                    # Parse parameters via scenario schema
                    schema_cls = scenario.parameters_schema
                    try:
                        validated_params = schema_cls(**plan.parameters)
                    except Exception as e_param:
                        logger.warning(
                            "시나리오 파라미터 유효성 검증 실패 (%s): %s -> 일반 에이전트 폴백",
                            scenario.name,
                            e_param,
                        )
                        validated_params = None

                    if validated_params is not None:
                        try:
                            context: Dict[str, Any] = {
                                "llm": self.llm,
                                "plan": plan,
                                "query": query,
                            }
                            if on_status:
                                on_status(f"⚙️ **[시나리오 실행 파이프라인 가동]** `{scenario.name}`")
                            return scenario.run(
                                params=validated_params,
                                tools=scenario_tools_to_inject,
                                context=context,
                            )
                        except Exception as e_exec:
                            logger.error(
                                "시나리오 실행 중 예외 발생 (%s): %s -> 일반 에이전트 폴백",
                                scenario.name,
                                e_exec,
                                exc_info=True,
                            )
            except Exception as e_route:
                logger.warning("시나리오 라우터 처리 실패 -> 일반 에이전트 폴백: %s", e_route)

        # 3. Fallback: General Agent Executor
        logger.info("[일반 에이전트 시작] ReAct 도구 호출 루프 진입: '%s'", query)
        if on_status:
            on_status("🔍 **[일반 에이전트 실행]** ReAct 도구 호출 루프 진입")
        start_agent = time.time()
        invoke_config: Dict[str, Any] = {}
        if callbacks:
            invoke_config["callbacks"] = callbacks
        result = self.executor.invoke({"input": query}, config=invoke_config)
        elapsed_agent = time.time() - start_agent
        output_text = (
            result.get("output", "") if isinstance(result, dict) else str(result)
        )
        logger.info(
            "[일반 에이전트 완료] 소요시간: %.2fs | 결과 크기: %d자",
            elapsed_agent,
            len(output_text),
        )
        if on_status:
            on_status(f"✅ **[일반 에이전트 완료]** 소요시간: {elapsed_agent:.2f}초")
        return output_text


AgentBuilder = AgentRunner
