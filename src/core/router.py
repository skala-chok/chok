import json
import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from src.config import settings
from .scenario import ScenarioExecutionPlan
from .scenario_registry import ScenarioRegistry

logger = logging.getLogger(__name__)


class ScenarioRoutingDecision(BaseModel):
    """LLM이 판단한 시나리오 선택 결과 및 파라미터."""

    scenario_name: Optional[str] = Field(
        default=None,
        description="가장 적합한 시나리오 이름 (등록된 시나리오 중 하나). 적합한 시나리오가 없으면 null.",
    )
    confidence: float = Field(
        default=0.0,
        description="시나리오 적합도 및 신뢰도 (0.0 ~ 1.0). 확신이 없으면 0.5 미만으로 지정.",
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="해당 시나리오의 파라미터 스키마에 맞춰 추출한 키-값 인자 딕셔너리",
    )
    reasoning: Optional[str] = Field(
        default=None,
        description="해당 시나리오를 선택했거나 일반 질의로 판단한 근거",
    )


class ScenarioRouter:
    """사용자 질의를 분석하여 최적의 비즈니스 시나리오를 식별하고 파라미터를 추출하는 라우터."""

    def __init__(
        self,
        registry: ScenarioRegistry,
        llm: Optional[BaseChatModel] = None,
        confidence_threshold: float = 0.6,
    ) -> None:
        self.registry = registry
        self.confidence_threshold = confidence_threshold

        if llm is not None:
            self.llm = llm
        else:
            self.llm = ChatOpenAI(
                model=settings.MODEL_NAME,
                api_key=settings.OPENAI_API_KEY or "dummy-key",
                temperature=0.0,
            )

    def _build_scenario_catalog(self) -> str:
        """등록된 시나리오들의 이름, 설명, 파라미터 필드 정보를 텍스트 카탈로그로 조합합니다."""
        catalog_lines = []
        for scen in self.registry.get_all_scenarios():
            schema = scen.parameters_schema
            fields_desc = []
            if hasattr(schema, "model_fields"):  # Pydantic v2
                for fname, finfo in schema.model_fields.items():
                    fields_desc.append(f"    - {fname}: {finfo.description or finfo.annotation}")
            elif hasattr(schema, "__fields__"):  # Pydantic v1
                for fname, finfo in schema.__fields__.items():
                    fields_desc.append(f"    - {fname}: {finfo.field_info.description or finfo.type_}")

            fields_str = "\n".join(fields_desc) if fields_desc else "    (추가 파라미터 없음)"
            catalog_lines.append(
                f"- 시나리오명: '{scen.name}'\n"
                f"  설명: {scen.description}\n"
                f"  요구 파라미터:\n{fields_str}"
            )
        return "\n\n".join(catalog_lines)

    def route(self, query: str) -> Optional[ScenarioExecutionPlan]:
        """사용자 질의에 맞는 시나리오를 결정하고 실행 계획을 생성합니다.

        Args:
            query: 사용자 입력 텍스트

        Returns:
            매칭 성공 시 ScenarioExecutionPlan, 적합한 시나리오가 없거나 신뢰도가 낮으면 None.
        """
        all_scenarios = self.registry.get_all_scenarios()
        if not all_scenarios:
            logger.debug("등록된 시나리오가 없어 일반 에이전트로 진행합니다.")
            return None

        catalog_text = self._build_scenario_catalog()

        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "당신은 사용자의 요청을 분석하여 사전에 등록된 최적의 전문 시나리오를 판별하는 지능형 라우터입니다.\n\n"
                "아래는 사용 가능한 전문 시나리오 카탈로그입니다:\n"
                "----------------------------------------\n"
                "{catalog}\n"
                "----------------------------------------\n\n"
                "[판단 가이드라인]\n"
                "1. 사용자의 요청이 특정 시나리오의 목적 및 요구 파라미터와 명확히 일치할 때만 해당 scenario_name을 선택하십시오.\n"
                "2. 단순 인사, 일반 지식 질문, 또는 어떤 시나리오에도 명확히 부합하지 않는 요청은 반드시 scenario_name을 null로 지정하고 confidence를 낮추십시오.\n"
                "3. 시나리오를 선택한 경우 질의에서 파라미터를 정확히 추출하여 parameters에 담으십시오.",
            ),
            ("human", "사용자 요청: {query}"),
        ])

        try:
            structured_llm = self.llm.with_structured_output(ScenarioRoutingDecision)
            chain = prompt | structured_llm
            decision: ScenarioRoutingDecision = chain.invoke({
                "catalog": catalog_text,
                "query": query,
            })

            if not decision.scenario_name:
                logger.info("시나리오 미매칭 (일반 질의로 처리). 이유: %s", decision.reasoning)
                return None

            if decision.scenario_name not in self.registry:
                logger.warning(
                    "LLM이 존재하지 않는 시나리오를 반환함: %s", decision.scenario_name
                )
                return None

            if decision.confidence < self.confidence_threshold:
                logger.info(
                    "시나리오 매칭 신뢰도 부족 (신뢰도: %.2f < 기준: %.2f) -> 일반 에이전트 폴백",
                    decision.confidence,
                    self.confidence_threshold,
                )
                return None

            logger.info(
                "시나리오 매칭 성공: '%s' (신뢰도: %.2f, 파라미터: %s)",
                decision.scenario_name,
                decision.confidence,
                decision.parameters,
            )

            return ScenarioExecutionPlan(
                scenario_name=decision.scenario_name,
                confidence=decision.confidence,
                parameters=decision.parameters,
                reasoning=decision.reasoning,
            )

        except Exception as e:
            logger.warning("시나리오 라우팅 중 오류 발생 -> 일반 에이전트 폴백: %s", e, exc_info=True)
            return None
