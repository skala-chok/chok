# LangChain 기반 다중 작업자 병렬 협업 에이전트 보일러플레이트 설계 명세서

- **작성일자:** 2026-09-10
- **상태:** Approved
- **목적:** 4명의 작업자가 YouTube 및 Naver Open API를 활용하여 `tool-context-guardrail-testcase` 전 영역을 Git 충돌 없이 동시에 병렬 개발할 수 있는 모듈러 플러그인 기반 보일러플레이트 아키텍처 정의.

---

## 1. 프로젝트 개요 및 배경

### 1.1 해결하고자 하는 문제
- 4명의 개발자가 단일 LLM 에이전트 프로젝트에서 동시에 각자의 도메인 API(YouTube, Naver)를 결합할 때, 중앙 코드(`agent.py`, `tools.py` 등)의 동시 수정으로 인한 빈번한 Git 충돌(Merge Conflict) 발생.
- API 키 미발급자 또는 특정 API 쿼터 소진 시 전체 에이전트 실행 및 테스트가 중단되는 의존성 결합 문제.
- 작업자마다 제각각인 도구 정의, 가드레일 누락, 일관되지 않은 프롬프트 주입으로 인한 품질 저하.

### 1.2 핵심 설계 원칙
1. **완전 격리 (Zero Merge Conflict)**: 공통 코어(`core/`)는 인터페이스를 동결하고, 작업자는 자신에게 할당된 개별 폴더(`modules/worker_*`) 및 테스트 파일만 수정.
2. **자동 탐색 및 플러그인 로딩 (Auto-Discovery)**: 모듈 폴더에 인터페이스를 구현해 두면 중앙 코드 수정 없이 런타임에서 자동으로 탐색 및 조립.
3. **Graceful Degradation**: 특정 작업자의 API 키가 설정되지 않아도(`is_enabled() == False`), 시스템이 에러 없이 해당 모듈만 안전하게 비활성화하고 가용 모듈만으로 에이전트 실행.
4. **표준 4대 컴포넌트 강제**: 모든 모듈은 반드시 `Tool`, `Context`, `Guardrail`, `TestCase`를 세트로 구비.

---

## 2. 시스템 아키텍처

### 2.1 아키텍처 다이어그램

```text
+-------------------------------------------------------------------------------+
|                                  User Query                                   |
+-------------------------------------------------------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     | Core Guardrail (validate_input)   |
                     +-----------------------------------+
                                       |
                                       v
                     +-----------------------------------+
                     |  LangChain Tool Calling Agent     |
                     |  - Base System Prompt             |
                     |  - Aggregated Context Snippets    |
                     +-----------------------------------+
                                       | (Tool Call Decision)
                                       v
                     +-----------------------------------+
                     | GuardrailedTool Wrapper           |
                     | 1. validate_tool_args(args)       |
                     | 2. execute tool(...)              |
                     | 3. sanitize_output(raw_output)    |
                     +-----------------------------------+
                       /           |             \          \
                      v            v              v          v
                 [yt_search] [yt_analytics] [naver_search] [naver_shopping]
```

### 2.2 디렉토리 구조

```text
skala-chok/
├── .env.example
├── requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py                     # CLI 진입점 (대화형 및 단일 실행 모드)
│   ├── config.py                   # 환경변수 및 설정 (Pydantic Settings)
│   ├── core/                       # 🔒 공통 코어 레이어 (수정 금지)
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseAgentModule, BaseGuardrail, BaseContextProvider
│   │   ├── agent.py                # LangChain 0.3 create_tool_calling_agent 빌더
│   │   ├── registry.py             # 모듈 자동 스캔 및 레지스트리
│   │   └── guardrails.py           # GuardrailedTool 래퍼 및 파이프라인 검증기
│   └── modules/                    # 🚀 작업자 격리 모듈 레이어
│       ├── __init__.py
│       ├── yt_search/              # 작업자 1
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── tools.py
│       │   ├── context.py
│       │   ├── guardrails.py
│       │   └── module.py
│       ├── yt_analytics/           # 작업자 2
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── tools.py
│       │   ├── context.py
│       │   ├── guardrails.py
│       │   └── module.py
│       ├── naver_search/           # 작업자 3
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── tools.py
│       │   ├── context.py
│       │   ├── guardrails.py
│       │   └── module.py
│       └── naver_shopping/         # 작업자 4
│           ├── __init__.py
│           ├── client.py
│           ├── tools.py
│           ├── context.py
│           ├── guardrails.py
│           └── module.py
└── tests/
    ├── conftest.py                 # 공통 pytest 픽스처 및 모의 객체
    ├── core/
    │   └── test_agent.py           # 레지스트리 및 코어 에이전트 빌더 테스트
    └── modules/
        ├── test_yt_search.py       # 작업자 1 단위 테스트
        ├── test_yt_analytics.py    # 작업자 2 단위 테스트
        ├── test_naver_search.py    # 작업자 3 단위 테스트
        └── test_naver_shopping.py  # 작업자 4 단위 테스트
```

---

## 3. 핵심 인터페이스 명세 (`src/core/base.py`)

### 3.1 `GuardrailResult` & `BaseGuardrail`
```python
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel

class GuardrailResult(BaseModel):
    passed: bool
    error_message: Optional[str] = None
    sanitized_input: Optional[Any] = None

class BaseGuardrail(ABC):
    def validate_input(self, query: str) -> GuardrailResult:
        """사용자 입력 쿼리 검증"""
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        """도구 실행 전 인자 검증"""
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        """도구 실행 후 결과 정제"""
        return output
```

### 3.2 `BaseContextProvider`
```python
class BaseContextProvider(ABC):
    @abstractmethod
    def get_system_prompt_snippet(self) -> str:
        """에이전트 시스템 프롬프트에 결합될 도메인 지침"""
        pass

    def get_dynamic_context(self, user_query: str) -> Optional[str]:
        """쿼리에 따라 런타임에 동적 주입할 컨텍스트"""
        return None
```

### 3.3 `BaseAgentModule`
```python
from typing import List
from langchain_core.tools import BaseTool

class BaseAgentModule(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def is_enabled(self) -> bool:
        """환경변수 및 설정 유효성 검사"""
        pass

    @abstractmethod
    def get_tools(self) -> List[BaseTool]:
        pass

    @abstractmethod
    def get_guardrails(self) -> List[BaseGuardrail]:
        pass

    @abstractmethod
    def get_context_provider(self) -> BaseContextProvider:
        pass
```

---

## 4. 4개 도메인 모듈 세부 역할 분담

### 4.1 작업자 1: `yt_search` (동영상 검색 및 자막 추출)
- **도구 목록**:
  - `search_youtube_videos(query: str, max_results: int = 5)`: YouTube v3 search API
  - `get_video_transcript(video_id: str, languages: list = ['ko', 'en'])`: 자막 텍스트 파싱
- **가드레일**:
  - `max_results`를 1~10 범위로 제한
  - 비어있는 video_id 또는 잘못된 형식 차단
  - 자막 미지원 시 안전한 에러 메시지 반환
- **컨텍스트**:
  - 검색 시점 및 관련성 정렬 팁 안내
  - 자막 분석을 통한 영상 핵심 요약 가이드

### 4.2 작업자 2: `yt_analytics` (채널 통계 및 댓글 분석)
- **도구 목록**:
  - `get_channel_stats(channel_id: str)`: 구독자수, 총 조회수, 총 동영상 수
  - `get_video_comments(video_id: str, max_comments: int = 20)`: 최신 댓글 수집
- **가드레일**:
  - 댓글 수집 개수 상한 설정(최대 50개)으로 API 쿼터 보호
  - 수집된 댓글 내 이메일/전화번호 등 개인정보 마스킹(Regex)
- **컨텍스트**:
  - 채널 분석 지표 해석 기준 가이드
  - 댓글 여론/반응 분석 프롬프트 팁

### 4.3 작업자 3: `naver_search` (블로그 및 뉴스 검색)
- **도구 목록**:
  - `search_naver_blog(query: str, display: int = 5, sort: str = 'sim')`: 네이버 블로그 검색
  - `search_naver_news(query: str, display: int = 5, sort: str = 'sim')`: 실시간 뉴스 검색
- **가드레일**:
  - 네이버 API 응답에 포함된 HTML 태그(`<b>`, `</b>`) 및 엔티티(`&quot;`, `&amp;`) 자동 제거
  - `display` 개수를 1~10으로 제한
- **컨텍스트**:
  - 한국 로컬 정보 및 최신 이슈 검색 시 활용 권장 지침
  - 블로그 후기 및 뉴스 기사의 신뢰도 비교 가이드

### 4.4 작업자 4: `naver_shopping` (쇼핑 최저가 및 트렌드 분석)
- **도구 목록**:
  - `search_naver_shopping(query: str, display: int = 5, sort: str = 'sim')`: 상품 가격 및 쇼핑몰 정보
  - `get_shopping_trends(category_id: str, start_date: str, end_date: str)`: 데이터랩 쇼핑인사이트
- **가드레일**:
  - 가격 0원 등 어뷰징 상품 필터링
  - 날짜 형식(YYYY-MM-DD) 유효성 검사
- **컨텍스트**:
  - 쇼핑몰 가격 비교 및 최저가(lprice) 판단 가이드
  - 트렌드 데이터를 바탕으로 한 상품 수요 분석 팁

---

## 5. 테스트 및 품질 보증 전략

### 5.1 단위 테스트 원칙
- 모든 외부 API 호출(`requests.get`, `googleapiclient` 등)은 `unittest.mock`으로 Mocking하여 쿼터 소모 및 외부 종속성을 완전히 제거.
- 각 작업자는 `pytest tests/modules/test_<worker_module>.py` 단일 명령어만으로 본인 모듈의 모든 기능을 1초 내에 검증 가능.

### 5.2 검증 항목
1. **Tool 실행 검증**: 정상 파라미터 전달 시 기대하는 포맷의 결과가 반환되는지 확인.
2. **Guardrail 검증**: 비정상 인자 입력 시 `passed=False` 반환 및 에러 메시지 확인, 결과물 HTML/민감정보 정제 확인.
3. **Context 검증**: 프롬프트 스니펫이 정상적으로 생성되는지 확인.
4. **Module 활성화 상태 검증**: API 키 유무에 따른 `is_enabled()` 반환값 검증.

---

## 6. 협업 및 개발 워크플로우

1. **초기 설정**:
   - `pip install -r requirements.txt`
   - `cp .env.example .env` (본인이 사용할 API 키만 입력 가능)
2. **브랜치 규칙**:
   - 작업자 1: `feature/yt-search`
   - 작업자 2: `feature/yt-analytics`
   - 작업자 3: `feature/naver-search`
   - 작업자 4: `feature/naver-shopping`
3. **Merge 검증**:
   - PR 제출 전 전체 테스트 통과 필수: `pytest`
   - 작업자 폴더 외 파일 수정 여부 검사 (Core 변경 방지)
