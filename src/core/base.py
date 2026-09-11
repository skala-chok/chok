"""공통 코어 추상 인터페이스 정의 (Core Abstract Interfaces).

[🏛️ 아키텍처 설계 원칙 & 코드 참고사항]
1. 개방-폐쇄 원칙 (Open-Closed Principle, OCP):
   - 본 `src/core/` 레이어는 동결(Frozen) 인터페이스로 설계되었습니다.
   - 새로운 외부 플랫폼(예: 신규 SNS, 쇼핑몰 등) 연동 시 코어 코드를 전혀 수정하지 않고
     `BaseAgentModule`을 상속받는 패키지를 `src/modules/`에 추가하기만 하면
     `ModuleRegistry`에 의해 런타임에 동적으로 자동 탐색 및 주입됩니다.
2. 인터페이스 분리 원칙 (Interface Segregation Principle, ISP):
   - 모듈 메타데이터(`BaseAgentModule`), 3대 방어선 가드레일(`BaseGuardrail`),
     동적 프롬프트 주입(`BaseContextProvider`)의 책임을 분리하여
     각 도메인 개발자가 독립적이고 모듈화된 코드를 작성할 수 있도록 지원합니다.
3. 모듈 간 무의존성 (Zero Cross-Module Dependency - Rule 2-1):
   - 모든 도메인 모듈은 오직 본 파일의 추상 기반 클래스와 전역 설정(`config.py`)에만 의존합니다.
   - 모듈 간 교차 임포트를 원천 차단하여 대규모 팀 협업 시 Git 병합 충돌을 방지합니다.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from langchain_core.tools import BaseTool


class GuardrailResult(BaseModel):
    """가드레일 검증 결과 데이터 컨테이너.
    
    Attributes:
        passed (bool): 가드레일 검증 통과 여부 (True: 통과, False: 차단).
        error_message (Optional[str]): 차단 시 사용자 또는 시스템에 전달할 상세 사유.
        sanitized_input (Optional[Any]): 정제된 입력 데이터 (필요 시 수정된 값 전달).
    """
    passed: bool
    error_message: Optional[str] = None
    sanitized_input: Optional[Any] = None


class BaseGuardrail(ABC):
    """엔터프라이즈 3대 방어선 가드레일 추상 기본 클래스 (Defense-in-Depth).
    
    [🛡️ 3대 방어선 설계 구조]
    1. 1차 사전 방어 (validate_input):
       - 사용자 자연어 질의가 에이전트 두뇌에 도달하기 전 악성 인젝션, 비속어, 빈 입력을 차단.
    2. 2차 도구 인자 방어 (validate_tool_args):
       - LLM이 도구 인자를 잘못 생성한 경우(날짜 포맷 불일치, 범위 초과 등) 실제 API 호출 전 사전 차단.
    3. 3차 사후 출력 방어 (sanitize_output):
       - 외부 API 호출 결과물에서 HTML 악성 태그를 제거하고 개인정보(이메일, 전화번호)를 자동 마스킹.
    """

    def validate_input(self, query: str) -> GuardrailResult:
        """에이전트 실행 전 사용자 원시 질의를 검증합니다 (1차 방어선)."""
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        """도구 실행 전 LLM이 생성한 파라미터 유효성을 검증합니다 (2차 방어선)."""
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        """도구 실행 완료 후 LLM에 결과를 반환하기 전 출력을 정제/마스킹합니다 (3차 방어선)."""
        return output


class BaseContextProvider(ABC):
    """도메인 지식 및 시스템 프롬프트 컨텍스트 주입 인터페이스.
    
    각 도메인 모듈의 도구 사용 팁, 제약 사항, 예시 질의 등을 에이전트의
    전역 시스템 프롬프트에 동적으로 결합(Composition)합니다.
    """

    @abstractmethod
    def get_system_prompt_snippet(self) -> str:
        """에이전트 시스템 프롬프트에 주입될 도메인 가이드 스니펫을 반환합니다."""
        pass

    def get_dynamic_context(self, user_query: str) -> Optional[str]:
        """사용자 질의에 따라 런타임에 동적으로 주입할 추가 컨텍스트(Few-shot 등)를 반환합니다."""
        return None


class BaseAgentModule(ABC):
    """각 도메인 워커(Worker)가 구현해야 하는 표준 플러그인 인터페이스.
    
    [🔌 플러그인 생명주기 및 Graceful Degradation]
    - `is_enabled()`: 필요한 API 키나 환경설정이 없을 경우 모듈을 안전하게 비활성화하여
      일부 키가 누락되어도 시스템 전체가 크래시되지 않고 가용한 기능만 안전하게 동작하도록 보장합니다.
    - `get_tools()`: LangChain 호환 BaseTool 리스트를 반환하여 에이전트 또는 시나리오 체인에 공급합니다.
    - `get_guardrails()`: 모듈에 특화된 가드레일 인스턴스를 반환하여 도구 전후 처리에 자동 체이닝합니다.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """모듈의 고유 식별자 (예: 'naver_shopping', 'yt_analytics', 'instagram')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """모듈의 역할 및 제공 기능에 대한 설명 (에이전트 라우팅 참고용)."""
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """필수 환경변수(API 키 등) 존재 여부를 확인하여 모듈 활성화 여부를 결정합니다."""
        pass

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        """모듈이 제공하는 LangChain BaseTool 인스턴스 목록을 반환합니다."""
        pass

    @abstractmethod
    def get_guardrails(self) -> List[BaseGuardrail]:
        """모듈에 적용할 BaseGuardrail 인스턴스 목록을 반환합니다."""
        pass

    @abstractmethod
    def get_context_provider(self) -> BaseContextProvider:
        """모듈의 시스템 프롬프트 컨텍스트 프로바이더 인스턴스를 반환합니다."""
        pass
