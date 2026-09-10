from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool


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
