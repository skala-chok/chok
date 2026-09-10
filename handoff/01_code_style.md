# 🎨 1. 코드 스타일 및 포맷팅 규격 (Code Style Guide)

본 문서는 `skala-chok` 프로젝트에서 코드를 작성하고 유지보수할 때 준수해야 하는 공통 코드 스타일, 명명 규칙, 타입 힌팅 및 문서화 표준을 정의합니다. 하네스 엔지니어링 및 멀티 작업자 협업 환경에서 일관된 코드 품질을 유지하는 것을 목표로 합니다.

---

## 📌 1. 기본 원칙 및 개발 환경

1. **Python 버전**: Python 3.10 이상을 기본 런타임으로 사용합니다.
2. **PEP 8 표준 준수**: Python 공식 스타일 가이드(PEP 8)를 기본으로 따릅니다.
3. **최대 줄 길이**: 가독성을 위해 **100자** 이내를 권장하며, 복잡한 프롬프트나 정규식의 경우 예외를 허용합니다.
4. **들여쓰기**: 스페이스 4칸(Soft Tab)을 원칙으로 하며 탭 문자는 금지합니다.
5. **인코딩**: 모든 소스 코드는 **UTF-8**로 저장합니다.

---

## 🏷️ 2. 명명 규칙 (Naming Conventions)

| 대상 | 표기법 (Convention) | 예시 | 비고 |
| :--- | :--- | :--- | :--- |
| **모듈 및 패키지** | `snake_case` | `naver_search`, `yt_analytics` | 밑줄 사용, 소문자 |
| **클래스명** | `PascalCase` (`CamelCase`) | `NaverSearchClient`, `AgentRunner` | 명사형 사용 |
| **함수 및 메서드** | `snake_case` | `validate_input()`, `get_shopping_trends()` | 동사+명사 조합 권장 |
| **도구 함수 (@tool)** | `snake_case` | `search_youtube_videos`, `search_naver_blog` | LLM이 목적을 직관적으로 유추 가능한 명확한 이름 |
| **변수 및 속성** | `snake_case` | `user_query`, `enabled_modules` | 의미 없는 약어 지양 |
| **상수 (Constants)** | `UPPER_SNAKE_CASE` | `DEFAULT_TIMEOUT`, `PROJECT_ROOT` | 전역 또는 클래스 상수 |
| **비공개 멤버** | `_leading_underscore` | `_build_scenario_catalog()` | 내부 전용 헬퍼 함수/속성 |

---

## 🔍 3. 타입 힌팅 (Type Hinting) 표준

본 프로젝트는 런타임 안정성과 LLM Tool Calling 인자 추출의 정확도를 위해 **모든 함수와 메서드에 100% 엄격한 타입 힌팅**을 적용합니다.

### ✅ 권장 패턴
```python
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field

# 1. 함수의 인자와 반환값에 명확한 타입 선언
def fetch_user_data(user_id: str, limit: int = 5) -> Dict[str, Any]:
    ...

# 2. None이 될 수 있는 인자는 Optional 명시
def sanitize_text(text: Optional[str] = None) -> str:
    if not text:
        return ""
    return text.strip()

# 3. Pydantic 스키마 정의 시 Field(description=...) 필수 적용
class SearchParamSchema(BaseModel):
    query: str = Field(description="검색할 핵심 키워드")
    display: int = Field(default=5, ge=1, le=10, description="반환할 결과 개수 (1~10)")
```

### ❌ 지양 패턴
```python
# 인자 타입 및 반환 타입 누락 (금지)
def search_items(q, count):
    return [...]

# any 단독 남용 (불가피한 경우를 제외하고 세부 타입 명시)
def process(data: Any) -> Any:
    ...
```

---

## 📝 4. Docstring 및 주석 표준

### 4.1 일반 클래스 및 메서드 Docstring
- Google Python Style Guide를 기본으로 작성합니다.
- 함수의 목적, 인자(`Args`), 반환값(`Returns`), 발생 가능한 예외(`Raises`)를 명확히 기술합니다.

```python
def wrap_tool_with_guardrails(
    tool: BaseTool, guardrails: List[BaseGuardrail]
) -> BaseTool:
    """LangChain 도구에 사전 인자 검증 및 사후 출력 정제 가드레일을 래핑합니다.

    Args:
        tool: 래핑 대상 LangChain BaseTool 인스턴스.
        guardrails: 순차 적용될 BaseGuardrail 인스턴스 리스트.

    Returns:
        가드레일이 장착된 새로운 BaseTool 인스턴스.
    """
    ...
```

### 4.2 LangChain 도구(@tool) 전용 Docstring 규칙
LLM 모델은 도구의 Docstring을 보고 "이 도구를 호출할지 여부"와 "각 파라미터에 어떤 값을 채울지"를 결정합니다. 따라서 다음 3가지를 반드시 포함해야 합니다:
1. **도구의 명확한 역할 정의** (무엇을 하는 도구인가?)
2. **파라미터의 제약 조건 및 유효 범위** (예: YYYY-MM-DD 형식, 1~10 사이 정수 등)
3. **호출 실패 시의 동작 안내**

```python
@tool
def get_shopping_trends(keywords: str, start_date: str, end_date: str) -> str:
    """네이버 데이터랩 쇼핑 인사이트 API를 호출하여 키워드의 일별 검색 클릭 트렌드를 조회합니다.
    
    Args:
        keywords: 쉼표로 구분된 분석 대상 키워드 문자열 (예: '아이폰16, 갤럭시S24').
        start_date: 조회 시작 날짜 (형식: YYYY-MM-DD).
        end_date: 조회 종료 날짜 (형식: YYYY-MM-DD).
        
    Returns:
        일자별 상대적 검색 비율 및 트렌드 요약 텍스트.
    """
    ...
```

---

## 📦 5. 모듈 임포트 규칙 (Import Order)

임포트는 반드시 파일 최상단에 위치하며, `isort` 표준에 따라 3개 블록으로 빈 줄 하나를 두고 구분합니다:

```python
# 1. 표준 라이브러리 (Standard Library)
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

# 2. 서드파티 라이브러리 (Third-party Packages)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

# 3. 로컬 프로젝트 패키지 (Local src.*)
from src.config import settings
from src.core.base import BaseAgentModule, BaseGuardrail, GuardrailResult
```

- **절대 경로 임포트 우선**: 내부 모듈 참조 시 `from src.core.base import ...`와 같이 프로젝트 루트 기준 절대 경로를 권장합니다. (단, 동일 모듈 내 서브파일 간에는 `.client`, `.tools` 같은 상대 임포트 허용)
- **와일드카드 임포트 금지**: `from module import *`는 네임스페이스 오염을 유발하므로 엄격히 금지합니다.

---

## 🧪 6. 권장 린팅 및 검증 도구

프로젝트 코드 작성 및 커밋 전 아래 도구들을 활용하여 코드 스타일을 유지합니다:

```bash
# 린트 검사
flake8 src tests --max-line-length=100

# 포맷팅 자동 정렬
black src tests -l 100
isort src tests

# 타입 정적 분석
mypy src
```
