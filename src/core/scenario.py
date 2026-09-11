"""복합 비즈니스 시나리오 추상 클래스 및 실행 프레임워크 (Scenario Framework).

[🎯 시나리오 라우팅 설계 의도 & 코드 참고사항]
1. 결정론적 도구 체이닝 vs 비결정론적 ReAct 루프:
   - 범용 에이전트의 ReAct 루프는 자유도가 높은 반면, 비즈니스 분석(크로스 플랫폼 트렌드, 경쟁사 비교 등)에서는
     불필요한 툴 호출, 무한 루프, 포맷 오류 등의 확률적 실패(Hallucination/Stochastic failure)가 발생할 수 있습니다.
   - 본 시스템은 정형화된 고품질 비즈니스 요구사항에 대해 Pydantic 스키마 기반의 '시나리오(Scenario)' 체인으로
     선제 라우팅하여 필요한 정예 도구만 결정론적으로 순차/병렬 호출하고 최고 품질의 리포트를 생성합니다.
2. 템플릿 메서드 패턴 (Template Method Pattern):
   - `BaseScenario.run()`은 시나리오 시작/종료 로깅, 소요 시간 측정, 입력 파라미터 직렬화, 예외 처리를 공통 담당하고,
   - 서브클래스는 `execute()` 메서드에서 도메인에 특화된 도구 체이닝 및 LLM 리포트 합성 로직만 집중 구현합니다.
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

logger = logging.getLogger("skala.scenario")


class ScenarioExecutionPlan(BaseModel):
    """시나리오 라우팅 결과 및 파라미터 컨테이너."""

    scenario_name: str = Field(description="실행할 시나리오 고유 식별자")
    confidence: float = Field(default=1.0, description="시나리오 매칭 신뢰도 (0.0 ~ 1.0)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="추출된 시나리오 입력 파라미터")
    reasoning: Optional[str] = Field(default=None, description="해당 시나리오를 선택한 이유")


class ScenarioResult(BaseModel):
    """시나리오 실행 결과."""

    scenario_name: str
    success: bool
    output: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseScenario(ABC):
    """N개의 복합 비즈니스 시나리오가 상속받는 추상 기본 클래스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """시나리오 고유 식별자 (예: 'cross_platform_trend')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """LLM 라우터가 시나리오 적합성을 판단하기 위한 설명."""
        pass

    @property
    @abstractmethod
    def parameters_schema(self) -> Type[BaseModel]:
        """시나리오 실행에 필요한 구조화된 파라미터 Pydantic 클래스."""
        pass

    @property
    def required_tool_names(self) -> List[str]:
        """시나리오 실행에 필요한 Tool 이름 목록.
        
        기본값은 빈 리스트이며, 구현체에서 필요한 도구 이름을 명시하면
        런타임에 ModuleRegistry로부터 해당 도구들만 주입받습니다.
        """
        return []

    def run(
        self,
        params: BaseModel,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """시나리오 전체 라이프사이클(시작, 소요 시간, 결과, 예외)을 자동 로깅하는 템플릿 메서드."""
        start_time = time.time()
        params_dict = (
            params.model_dump()
            if hasattr(params, "model_dump")
            else getattr(params, "__dict__", {})
        )
        logger.info(
            "[시나리오 시작] '%s' | 파라미터: %s | 주입 도구 (%d개): %s",
            self.name,
            params_dict,
            len(tools),
            list(tools.keys()),
        )

        try:
            output = self.execute(params=params, tools=tools, context=context)
            elapsed = time.time() - start_time
            output_len = len(output) if isinstance(output, str) else 0
            logger.info(
                "[시나리오 완료] '%s' | 소요시간: %.2fs | 결과 크기: %d자",
                self.name,
                elapsed,
                output_len,
            )
            return output
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "[시나리오 실패] '%s' | 소요시간: %.2fs | 에러: %s",
                self.name,
                elapsed,
                e,
                exc_info=True,
            )
            raise

    @abstractmethod
    def execute(
        self,
        params: BaseModel,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """시나리오 전용 툴 체인(파이프라인 또는 서브 에이전트)을 실행합니다.
        
        Args:
            params: parameters_schema로 파싱된 입력 객체
            tools: required_tool_names로 주입된 {tool_name: BaseTool} 딕셔너리
            context: 추가 런타임 컨텍스트 (LLM, 세션 정보 등)
            
        Returns:
            최종 분석 또는 실행 결과 텍스트
        """
        pass
