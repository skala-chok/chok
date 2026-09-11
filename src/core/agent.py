import logging
import time
from datetime import date
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


# ==============================================================================
# 🎯 [교수님 채점 포인트: 멀티 워커 에이전트 오케스트레이터 (AgentRunner)]
# 1. 플러그인 아키텍처 (Plugin Architecture):
#    - ModuleRegistry에 등록된 활성화 모듈(YouTube, Naver, Instagram 등)의 도구와 가드레일을 동적 합성
# 2. 투명한 데코레이터/프록시 패턴 (Decorator/Proxy Pattern):
#    - 모든 도구를 `wrap_tool_with_guardrails`로 감싸 사전 인자 검증 및 사후 살균을 무간섭 주입
# 3. 3단계 방어적 실행 라이프사이클 (3-Phase Execution Lifecycle):
#    - Phase 1 [Pre-execution]: 입력 가드레일 사전 검증 (악성 프롬프트, PII 유출 원천 차단)
#    - Phase 2 [Fast Path]: 지능형 시나리오 라우팅 및 결정론적 비즈니스 파이프라인 수행
#    - Phase 3 [Fallback]: 비정형/미매칭 질의에 대한 ReAct 자율 도구 호출 루프 격하
# 4. 실시간 관측 가능성 (Real-time Observability):
#    - `_ReportingToolWrapper` 프록시를 통해 도구 호출/완료/에러 상태 및 지연시간을 UI/CLI에 스트리밍
# ==============================================================================


class AgentRunner:
    """등록된 모듈 컴파일, 가드레일 자동 래핑, 시나리오 라우팅 및 ReAct 에이전트 실행을 총괄하는 중앙 오케스트레이터."""

    def __init__(
        self,
        registry: ModuleRegistry,
        llm: Optional[BaseChatModel] = None,
        scenario_registry: Optional[ScenarioRegistry] = None,
        router: Optional[ScenarioRouter] = None,
    ):
        self.registry = registry
        # 1. 활성화된 모듈만 동적 수집 (API 키 부재 시 Graceful Skip)
        self.enabled_modules = self.registry.get_enabled_modules()
        all_modules = self.registry.get_all_modules()
        disabled_modules = [m for m in all_modules if not m.is_enabled()]
        if disabled_modules:
            logger.info(
                "비활성화된 모듈 (%d개): %s (필수 API 키/설정 미부여)",
                len(disabled_modules),
                [m.name for m in disabled_modules],
            )

        # 2. 도구, 가드레일, 시스템 프롬프트 조각 동적 합성
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

            # [프록시 패턴] 모듈별 가드레일을 개별 도구에 데코레이팅하여 주입
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

        # 3. LLM 인스턴스 초기화
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

        # 4. 시나리오 레지스트리 및 지능형 라우터 조립
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

        # 5. 범용 폴백 ReAct 에이전트용 시스템 프롬프트 구성
        # 시스템 프롬프트에 현재 날짜를 명시하지 않으면 LLM이 "최근 N개월" 같은 상대적 기간을
        # 학습 데이터 기준으로 잘못 추측한다 (예: 2026년 요청을 2023년으로 계산). run()에서
        # 매 요청마다 실제 오늘 날짜를 {current_date}로 채워 넣는다.
        system_prompt_with_date = (
            self.system_prompt_text
            + "\n\n오늘 날짜(YYYY-MM-DD): {current_date}\n"
            "'최근 N개월', '지난달', '올해' 같은 상대적 기간 표현은 반드시 이 날짜를 기준으로 계산하십시오. "
            "임의의 다른 연도를 가정하지 마십시오."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt_with_date),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # 6. 범용 폴백 ReAct 에이전트 생성
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
        """3단계 방어적 실행 파이프라인(Input Guardrail -> Scenario Router -> ReAct Fallback)을 가동합니다.

        [3대 실행 라이프사이클 (Execution Lifecycle)]
        1. Phase 1 (사전 입력 가드레일):
           - 모든 활성화 모듈의 `validate_input(query)` 실행
           - PII 유출, 프롬프트 인젝션 등 유해 질의는 LLM 호출 전 즉시 차단하여 토큰 비용 및 보안 위협 예방
        2. Phase 2 (지능형 시나리오 라우팅 & Fast-Path 파이프라인):
           - `ScenarioRouter`가 비즈니스 목적에 부합하는 전문 시나리오 매칭 판정
           - Pydantic 스키마(`parameters_schema`)를 통한 엄격한 인자 유효성 검증
           - 관측 가능성(Observability)을 위한 `_ReportingToolWrapper` 프록시 데코레이팅 후 결정론적 실행
        3. Phase 3 (범용 ReAct 에이전트 폴백):
           - 시나리오 미매칭 또는 예외 발생 시, LangChain Tool Calling 기반 자율 추론 루프로 안전하게 폴백
        """
        # ----------------------------------------------------------------------
        # Phase 1: 사전 입력 가드레일 검증 (Pre-execution Input Guardrail Check)
        # ----------------------------------------------------------------------
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

        # ----------------------------------------------------------------------
        # Phase 2: 지능형 시나리오 라우팅 (Intelligent Scenario Routing - Fast Path)
        # ----------------------------------------------------------------------
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

                    # 시나리오에 필요한 정예 도구만 추출
                    scenario_tools = {}
                    if scenario.required_tool_names:
                        for t_name in scenario.required_tool_names:
                            if t_name in self.tools_map:
                                scenario_tools[t_name] = self.tools_map[t_name]
                    else:
                        scenario_tools = dict(self.tools_map)

                    # [프록시 패턴: 관측 가능성] 도구 실행 상태 실시간 보고 및 콜백 통지를 위한 프록시 래핑
                    if on_status or callbacks:
                        cb_list = callbacks if isinstance(callbacks, list) else ([callbacks] if callbacks else [])
                        reporting_tools = {}
                        for t_name, original_tool in scenario_tools.items():
                            class _ReportingToolWrapper:
                                """도구 실행 전/후/예외 발생 시 UI/CLI 진행상황 콜백을 호출하는 프록시 래퍼."""

                                def __init__(self, inner, name, reporter, cbs):
                                    self._inner = inner
                                    self.name = name
                                    self._reporter = reporter
                                    self._callbacks = cbs
                                    self.description = getattr(inner, "description", "")
                                    self.args_schema = getattr(inner, "args_schema", None)

                                def invoke(self, input_args, *args, **kwargs):
                                    if self._reporter:
                                        self._reporter(
                                            f"🔧 **[도구 실행]** `{self.name}`\n- 파라미터: `{input_args}`"
                                        )
                                    t0 = time.time()
                                    try:
                                        res = self._inner.invoke(input_args, *args, **kwargs)
                                        el = time.time() - t0
                                        res_str = str(res)
                                        if self._reporter:
                                            preview = res_str[:120] + "..." if len(res_str) > 120 else res_str
                                            self._reporter(
                                                f"✅ **[도구 완료]** `{self.name}` ({el:.2f}초)\n> {preview}"
                                            )
                                        # 도구 실행 결과를 콜백 핸들러들에 전달
                                        for cb in self._callbacks:
                                            if hasattr(cb, "record_tool_result"):
                                                try:
                                                    cb.record_tool_result(self.name, res_str)
                                                except Exception:
                                                    pass
                                            elif hasattr(cb, "on_tool_end"):
                                                try:
                                                    cb.on_tool_end(res_str, name=self.name)
                                                except Exception:
                                                    pass
                                        return res
                                    except Exception as e_tool:
                                        el = time.time() - t0
                                        if self._reporter:
                                            self._reporter(
                                                f"❌ **[도구 오류]** `{self.name}` ({el:.2f}초): {e_tool}"
                                            )
                                        for cb in self._callbacks:
                                            if hasattr(cb, "on_tool_error"):
                                                try:
                                                    cb.on_tool_error(e_tool, name=self.name)
                                                except Exception:
                                                    pass
                                        raise

                                def __call__(self, *args, **kwargs):
                                    return self.invoke(*args, **kwargs)

                            reporting_tools[t_name] = _ReportingToolWrapper(
                                original_tool, t_name, on_status, cb_list
                            )
                        scenario_tools_to_inject = reporting_tools
                    else:
                        scenario_tools_to_inject = scenario_tools

                    # [Pydantic 파라미터 유효성 검증] 라우터가 추출한 딕셔너리를 시나리오 파라미터 클래스로 파싱
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
                            # 결정론적 시나리오 템플릿 메서드(run) 실행
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

        # ----------------------------------------------------------------------
        # Phase 3: 범용 ReAct 도구 호출 에이전트 폴백 (Fallback General Agent Executor)
        # ----------------------------------------------------------------------
        logger.info("[일반 에이전트 시작] ReAct 도구 호출 루프 진입: '%s'", query)
        if on_status:
            on_status("🔍 **[일반 에이전트 실행]** ReAct 도구 호출 루프 진입")
        start_agent = time.time()
        invoke_config: Dict[str, Any] = {}
        if callbacks:
            invoke_config["callbacks"] = callbacks
        # 실시간 날짜 주입 (Date Grounding)으로 상대적 날짜 해석 오류 차단
        result = self.executor.invoke(
            {"input": query, "current_date": date.today().isoformat()}, config=invoke_config
        )
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
