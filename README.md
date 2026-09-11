# LangChain Multi-Worker & Model-Driven Scenario Agent 보일러플레이트

> **여러 명의 개발자가 Git 충돌(Merge Conflict) 없이 독립적으로 도구(Tool), 가드레일, 컨텍스트, 시나리오를 병렬 개발할 수 있는 모듈러 플러그인 아키텍처**

본 프로젝트는 **YouTube Data API v3**, **Naver Search/Datalab Open API**, **Instagram Graph API** 등을 활용하는 엔터프라이즈급 AI 에이전트 시스템입니다.  
공통 코어 인터페이스를 엄격히 동결하고 동적 플러그인 자동 탐색(Auto-Discovery), 독립 가드레일(Guardrails), 프롬프트 컨텍스트 주입, 그리고 **모델 기반 지능형 시나리오 라우팅(Scenario-driven Tool Chaining)**을 적용하여 대규모 팀에서도 코드 간섭 없이 확장할 수 있도록 설계되었습니다.

---

## 📑 목차
1. [시스템 아키텍처](#-시스템-아키텍처)
2. [디렉토리 구조](#-디렉토리-구조)
3. [빠른 시작 가이드 (Quickstart)](#-빠른-시작-가이드-quickstart)
4. [CLI 실행 가이드](#-cli-실행-가이드)
5. [초보자도 바로 만드는 4대 핵심 개발 가이드](#-초보자도-바로-만드는-4대-핵심-개발-가이드)
   - [💡 시작하기 전에: 왜 Base 추상 클래스를 상속받아야 할까요?](#-시작하기-전에-왜-base-추상-클래스를-상속받아야-할까요)
   - [① Tool 개발 가이드](#1-tool-도구-개발-가이드)
   - [② Context 개발 가이드](#2-context-프롬프트-컨텍스트-개발-가이드)
   - [③ 가드레일(Guardrail) 개발 가이드](#3-가드레일guardrail-개발-가이드)
   - [④ 시나리오(Scenario) 개발 가이드](#4-시나리오scenario-개발-가이드)
6. [작업자(Worker) 역할 분담 및 협업 원칙](#-작업자worker-역할-분담-및-협업-원칙)
7. [테스트 및 품질 검증 가이드](#-테스트-및-품질-검증-가이드)
8. [프로젝트 위키 (Index & Study)](#-프로젝트-위키-index--study)
9. [하네스 엔지니어링 Handoff 센터 (handoff/index.md)](#-하네스-엔지니어링-handoff-센터-handoffindexmd)

---

## 🏛️ 시스템 아키텍처

본 시스템은 **사용자 질의 인입 → 사전 가드레일 검사 → 모델 기반 시나리오 라우팅 → 정예 도구 체인(또는 일반 에이전트 폴백) → 도구별 인자 검증 및 출력 정제**로 이어지는 유기적 파이프라인으로 구동됩니다.

```mermaid
flowchart TD
    UserQuery([사용자 질의 입력]) --> CoreGuardrail["🛡️ 1차 가드레일: BaseGuardrail.validate_input\n(비속어, 프롬프트 인젝션 차단)"]
    CoreGuardrail -->|차단 시| BlockResponse[가드레일 차단 안내 반환]
    CoreGuardrail -->|통과| Router["🧭 ScenarioRouter (LLM 의도 분류 & 파라미터 추출)"]

    Router -->|시나리오 A 매칭| ScenA["시나리오 A: 크로스 플랫폼 트렌드\n(정예 Tool 순차 체이닝)"]
    Router -->|시나리오 B 매칭| ScenB["시나리오 B: 경쟁사 채널 분석\n(정예 Tool 병렬 체이닝)"]
    Router -->|매칭 시나리오 없음| FallbackAgent["🤖 일반 에이전트 (Fallback)\n(AgentExecutor ReAct 루프)"]

    subgraph ToolExecutionPipeline ["도구 실행 파이프라인 (GuardrailedTool)"]
        direction TB
        ArgCheck["🛡️ 2차 가드레일: validate_tool_args\n(파라미터 범위 및 날짜 형식 검증)"]
        ToolCall["⚙️ 도구 원본 실행 (API 호출)"]
        Sanitize["🛡️ 3차 가드레일: sanitize_output\n(HTML 태그 제거, 개인정보 마스킹)"]
        ArgCheck -->|검증 성공| ToolCall --> Sanitize
        ArgCheck -->|검증 실패| ArgFail["에러 메시지 반환"]
    end

    ScenA -.->|정예 도구 호출| ToolExecutionPipeline
    ScenB -.->|정예 도구 호출| ToolExecutionPipeline
    FallbackAgent -.->|전체 도구 호출| ToolExecutionPipeline

    Sanitize --> FinalResult([최종 분석 리포트 / 응답])
```

---

## 📁 디렉토리 구조

```text
skala-chok/
├── app.py                           # 🤖 Streamlit 대화형 테스트 대시보드
├── .env.example                     # 환경변수 템플릿
├── requirements.txt                 # 전체 의존성 목록
├── pytest.ini                       # Pytest 실행 설정
├── README.md                        # 본 개발자 가이드
├── handoff/                         # 🧭 하네스 엔지니어링 및 인수인계 문서군
│   ├── index.md                     # Handoff 중앙 라우팅 허브
│   ├── 01_code_style.md             # 코드 스타일 및 린트 규격
│   ├── 02_architecture.md           # 현재 시스템 아키텍처 구조
│   ├── 03_guidelines.md             # 작성 준수 사항 및 개발 원칙
│   ├── 04_testing_harness.md        # 테스트 및 하네스 엔지니어링 가이드
│   ├── 05_extension_guide.md        # 신규 모듈/시나리오 확장 가이드
│   └── 06_troubleshooting.md        # 트러블슈팅 및 운영 가이드
├── wiki/                            # 📚 생성형 AI 서비스 개발 교재 마스터 위키
│   ├── Index.md                     # [Index] 교재 전체 로드맵 & 아키텍처 점검표
│   ├── Study.md                     # [Study] 챕터별 심층 스터디 중앙 허브
│   ├── Chapter_1_Introduction.md    # [Ch 1] 패러다임 진화, ReAct, 에이전트 거버넌스
│   ├── Chapter_2_LLM_Foundations.md # [Ch 2] 토큰 예측, 6대 기술, 3대 SDK 제어
│   ├── Chapter_3_LangChain.md       # [Ch 3] 4대 추상화, Structured Output, LCEL
│   ├── Chapter_4_Basic_Agent.md     # [Ch 4] 7단계 루프, Checkpointer, Mocking
│   ├── Chapter_5_Advanced_Agent.md  # [Ch 5] Runtime Context, 미들웨어, 가드레일
│   ├── Appendix_Observability_Troubleshooting.md # [부록] 관측성/로깅 트러블슈팅
│   └── _Sidebar.md                  # GitHub Wiki 표준 사이드바
├── src/
│   ├── main.py                      # CLI 엔트리포인트 (로깅, 예외처리 포함)
│   ├── config.py                    # 전역 설정 (Pydantic Settings)
│   ├── core/                        # 🔒 공통 코어 레이어 (수정 금지 - Frozen)
│   │   ├── base.py                  # 모듈/가드레일/컨텍스트 추상 인터페이스
│   │   ├── registry.py              # 모듈 동적 탐색 (ModuleRegistry)
│   │   ├── guardrails.py            # GuardrailedTool 래퍼
│   │   ├── scenario.py              # 시나리오 기본 추상 클래스 (BaseScenario)
│   │   ├── scenario_registry.py     # 시나리오 동적 탐색 (ScenarioRegistry)
│   │   ├── router.py                # 지능형 시나리오 라우터 (ScenarioRouter)
│   │   └── agent.py                 # 통합 AgentRunner
│   ├── modules/                     # 🚀 1. 도메인 모듈 개발 영역 (단일 Tool 공급)
│   │   ├── yt_search/               # YouTube 영상 검색 & 자막
│   │   ├── yt_analytics/            # YouTube 통계 & 댓글 수집
│   │   ├── naver_search/            # 네이버 블로그 & 뉴스 검색
│   │   └── naver_shopping/          # 네이버 쇼핑 데이터랩 트렌드 (분야/키워드 x 전체/성별/연령)
│   └── scenarios/                   # 🚀 2. 복합 시나리오 개발 영역 (Tool 체이닝)
│       └── cross_platform_trend/    # [예시] 네이버 트렌드 + 유튜브 크로스 분석 시나리오
└── tests/                           # 테스트 스위트 (100% Mock 격리)
    ├── core/                        # 코어 및 시나리오 단위 테스트
    ├── modules/                     # 모듈별 단위 테스트
    └── api_test.py                  # 19개 API 엔드포인트 명세 및 라이브 검증 테스트
```

---

## ⚡ 빠른 시작 가이드 (Quickstart)

```bash
# 1. 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY, YOUTUBE_API_KEY, NAVER_CLIENT_ID 등을 입력합니다.
```

---

## 🌐 Streamlit 대화형 테스트 대시보드 (`app.py`)

개발한 커스텀 도구(@tool), 가드레일, 비즈니스 시나리오(Scenario), 통합 에이전트 라우팅을 웹 UI에서 시각적으로 테스트하고 검증할 수 있는 대화형 대시보드를 제공합니다.

```bash
# Streamlit 웹 대시보드 실행
streamlit run app.py
```

### 🌟 주요 기능
1. **🛠️ 단일 툴 테스트 (Tool Playground)**:
   - 등록된 모든 도구(`yt_search`, `yt_analytics`, `naver_search`, `naver_shopping`)를 선택하고 파라미터를 입력하여 실시간 호출 및 가드레일 입력/출력 검증
2. **🎬 복합 시나리오 테스트 (Scenario Playground)**:
   - Pydantic 스키마(`CrossPlatformTrendParams`) 기반 입력 폼 동적 렌더링
   - 필수 도구 체이닝 및 LLM 종합 크로스 분석 리포트 생성
3. **💬 통합 에이전트 대화 (Agent & Router)**:
   - 자연어 입력 시 라우터의 의도 분류 및 시나리오 자동 매칭/ReAct 폴백 과정 시각화
   - 원클릭 퀵 테스트 질문 및 가드레일 차단 테스트 제공
4. **🎭 Mock 모드 지원**:
   - 외부 API 키가 없거나 쿼터를 아끼고 싶을 때 사이드바의 **Mock 데이터 모드**를 켜면 즉시 모의 데이터로 전체 파이프라인 검증 가능

---

## 💻 CLI 실행 가이드

`src/main.py`는 깔끔한 텍스트 기반 콘솔 프롬프트, 상세 `logging` 모듈, 단계별 예외 처리가 적용되어 있습니다.

### 1. 단일 질의 실행 (`--query` / `-q`)
```bash
python src/main.py --query "러닝화 트렌드 분석해줘"
```

### 2. 로깅 레벨 지정 (`--log-level`)
디버깅 시 상세 통신 로그를 확인할 수 있습니다. (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
```bash
python src/main.py --query "러닝화 트렌드" --log-level DEBUG
```

### 3. 대화형 콘솔 모드 (`--interactive` / `-i`)
```bash
python src/main.py --interactive
```
실행 화면:
```text
2026-09-10 23:04:54 [INFO] skala_agent: CLI 실행 시작 (로그 레벨: INFO)
2026-09-10 23:04:54 [INFO] skala_agent: 활성 모듈 로드 완료 (4개): ['naver_search', 'naver_shopping', 'yt_analytics', 'yt_search']
2026-09-10 23:04:54 [INFO] skala_agent: 활성 시나리오 로드 완료 (1개): ['cross_platform_trend']
============================================================
[LangChain Multi-Worker Agent] 초기화 완료
로드된 활성 모듈 (4개): ['naver_search', 'naver_shopping', 'yt_analytics', 'yt_search']
로드된 활성 시나리오 (1개): ['cross_platform_trend']
============================================================
대화형 모드를 시작합니다. (종료하려면 'exit' 또는 'quit' 입력)

사용자 > 러닝화 최신 트렌드 분석해줘
에이전트 >
... (시나리오 체인이 동작하여 생성된 종합 리포트 출력) ...

사용자 > quit
종료합니다.
```

---

## 🛠️ 초보자도 바로 만드는 4대 핵심 개발 가이드

이 프로젝트를 처음 접하는 개발자도 아래 4가지 컴포넌트만 이해하면 즉시 새로운 기능을 추가할 수 있습니다.

```
┌────────────────────────────────────────────────────────┐
│ 1. Tool: "LLM이 손발처럼 호출하는 단일 기능 함수"         │
│ 2. Context: "LLM에게 도구 사용법과 배경 지식을 알려주는 설명서"  │
│ 3. Guardrail: "잘못된 입력과 API 오류, 개인정보를 막는 방패"│
│ 4. Scenario: "여러 Tool을 엮어 하나의 비즈니스 목적을 달성하는 체인" │
```

---

### 💡 시작하기 전에: 왜 Base 추상 클래스를 상속받아야 할까요?

처음 코드를 작성할 때 *"그냥 내 마음대로 파이썬 함수나 클래스를 만들면 안 되나? 왜 굳이 `BaseAgentModule`, `BaseGuardrail`, `BaseContextProvider`, `BaseScenario` 같은 코어 클래스를 반드시 상속(`Inheritance`)받아야 하지?"* 라는 의문이 들 수 있습니다.

본 프로젝트에서 `Base` 클래스를 상속받는 것은 단순한 코딩 스타일이 아니라, **시스템이 정상적으로 동작하기 위한 필수 아키텍처 규칙**입니다:

#### 1. Zero-Config 자동 탐색(Auto-Discovery)의 유일한 식별 기준
`ModuleRegistry`와 `ScenarioRegistry`는 개발자가 일일이 수동으로 모듈을 등록하지 않아도 폴더 안의 모든 파이썬 파일을 스캔하여 자동으로 에이전트에 장착합니다.  
이때 레지스트리는 파이썬의 리플렉션을 사용하여 **"이 클래스가 `BaseAgentModule`(또는 `BaseScenario`)의 자식 클래스인가?" (`issubclass(cls, Base...)`)**를 검사합니다.
- ❌ **상속받지 않은 클래스**: 레지스트리가 아예 인식하지 못하고 무시하므로 에이전트에 등록되지 않습니다.
- ✅ **상속받은 클래스**: 파일만 만들어 두면 실행 시 자동으로 발견되어 즉시 활성화됩니다.

#### 2. 필수 메서드 누락 방지 (엄격한 인터페이스 계약, Contract)
`Base` 클래스들은 파이썬의 ABC(Abstract Base Class)와 `@abstractmethod`로 정의되어 있습니다.  
에이전트 엔진이 정상적으로 도구를 실행하고, 가드레일을 씌우고, 파라미터를 파싱하려면 정해진 규격(`name`, `get_tools()`, `execute()` 등)이 반드시 존재해야 합니다.
- 만약 필수 프로퍼티나 메서드를 빼먹고 구현하면, **파이썬 인터프리터가 클래스를 인스턴스화하는 즉시 에러(`TypeError: Can't instantiate abstract class with abstract methods...`)를 발생**시켜 조기에 버그를 알려줍니다.

#### 3. 코어 동결(Core Freeze)과 Git 무충돌(Zero Merge Conflict)의 기반
에이전트 중앙 엔진([`AgentRunner`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/agent.py))은 여러분이 만든 클래스가 유튜브 모듈인지, 네이버 모듈인지 구체적인 내용을 전혀 알 필요가 없습니다(DIP, 의존 역전 원칙).  
오직 `BaseAgentModule`과 `BaseScenario`라는 **공통 표준 규격**만을 바라보고 동작하므로:
- 중앙 코드를 한 줄도 수정하지 않고도 신규 모듈과 시나리오를 N개씩 무한히 확장(OCP, 개방-폐쇄 원칙)할 수 있습니다.
- 4명의 개발자가 각자의 폴더에서 병렬 개발해도 `git merge` 충돌이 근본적으로 발생하지 않습니다.

| 구분 | ❌ Base 미상속 (자유 작성) | ✅ Base 상속 (표준 준수) |
|---|---|---|
| **자동 탐색 (Auto-Discovery)** | 레지스트리가 컴포넌트로 인식 불가 (누락) | `src/modules/`, `src/scenarios/`에 파일만 두면 자동 로드 |
| **안전성 (Contract)** | 필수 메서드 누락 시 런타임 중간에 예기치 않게 Crash | 인스턴스화 즉시 필수 구현 누락을 감지하여 조기 방어 |
| **중앙 코드 간섭** | 신규 기능 추가 시 `agent.py`나 `main.py`를 직접 수정해야 함 | 코어(`src/core/`) 수정 제로, 완벽한 Git 무충돌 |
| **IDE 지원** | 메서드명 오타나 반환형 실수를 잡기 어려움 | IDE 자동 완성과 타입 힌트가 구현할 목록을 친절히 안내 |

---

### 🌈 신규 작업자를 위한 레인보우(무지개색 점) Step-by-Step 로드맵

신규 작업자(Worker)가 코드를 처음 작성할 때 무엇부터 시작해야 할지 헤매지 않도록, **무지개색 순서(🔴 ➔ 🟠 ➔ 🟡 ➔ 🟢 ➔ 🔵 ➔ 🟣)**로 파일 상단 주석과 개발 순서가 일관되게 구조화되어 있습니다.

#### 1. 에이전트 도구 모듈(`src/modules/<모듈명>/`) 개발 로드맵
```
 🔴 client.py    ➔ 🟠 guardrails.py ➔ 🟡 tools.py      ➔ 🟢 context.py    ➔ 🔵 module.py    ➔ 🟣 tests/
 (외부 API 클라이언트) (인자검증/정제 방패)  (LangChain @tool) (프롬프트 도메인가이드) (모듈 통합 등록)  (격리 단위테스트)
```

| 단계 | 색상 및 대상 파일 | 담당 역할 및 개발 내용 |
|:---:|:---|:---|
| **Step 1** | 🔴 `client.py` | **외부 API 통신 클라이언트**: 순수 HTTP 통신, API 키 인증 헤더, JSON 파싱, 기본 네트워크 예외 처리 구현 |
| **Step 2** | 🟠 `guardrails.py` | **가드레일 방패**: [`BaseGuardrail`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/guardrail.py) 상속. LLM이 넘긴 파라미터 유효성 검증(`validate_input`) 및 민감정보 마스킹/출력 정제(`sanitize_output`) |
| **Step 3** | 🟡 `tools.py` | **LangChain 도구 정의**: `@tool` 데코레이터 적용. LLM이 도구 선택 기준으로 삼는 Docstring과 Type Hint 명확히 작성, 클라이언트와 가드레일 결합 |
| **Step 4** | 🟢 `context.py` | **도메인 컨텍스트 제공자**: [`BaseContextProvider`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/context.py) 상속. LLM에게 해당 도메인의 핵심 키워드, 도구 사용 시 주의사항을 시스템 프롬프트 조각으로 전달 |
| **Step 5** | 🔵 `module.py` | **에이전트 모듈 패키징**: [`BaseAgentModule`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/module.py) 상속. 도구 리스트, 가드레일, 컨텍스트를 하나로 묶어 레지스트리가 자동 로드(`Auto-Discovery`)할 수 있도록 등록 |
| **Step 6** | 🟣 `tests/modules/test_xxx.py` | **100% Mock 단위 테스트**: 외부 실 API 호출 없이 `unittest.mock`으로 클라이언트 응답을 모킹하여 도구 및 모듈 정상 동작 검증 |

#### 2. 복합 시나리오 체인(`src/scenarios/<시나리오명>/`) 개발 로드맵
```
 🔴 Pydantic 스키마 ➔ 🟠 BaseScenario 선언 ➔ 🟡 execute() 도구 체이닝 ➔ 🟢 LLM 크로스 리포트 ➔ 🔵 단위 테스트 검증
```

| 단계 | 색상 및 대상 위치 | 담당 역할 및 개발 내용 |
|:---:|:---|:---|
| **Step 1** | 🔴 `scenario.py` 상단 | **입력 파라미터 스키마**: Pydantic `BaseModel`로 질의에서 추출할 필수/선택 파라미터 선언 |
| **Step 2** | 🟠 `scenario.py` 클래스 | **시나리오 선언**: [`BaseScenario`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/scenario.py) 상속 및 메타데이터(`name`, `description`, `required_tools`) 정의 |
| **Step 3** | 🟡 `execute()` 내부 | **정예 도구 순차 체이닝**: `tools.get(...)`으로 필요한 도구들을 단계별로 호출하고 중간 결과 데이터 축적 |
| **Step 4** | 🟢 `execute()` 하단 | **LLM 크로스 리포트 생성**: `ChatPromptTemplate \| llm` 파이프라인으로 멀티 플랫폼 데이터를 융합 분석하고 예외 시 Fallback 데이터 반환 |
| **Step 5** | 🔵 `tests/core/test_scenario.py` | **시나리오 단위 테스트**: Mock 도구 및 Mock LLM으로 체인 전체 흐름 및 Fallback 정상 동작 검증 |

---

### 1. Tool (도구) 개발 가이드

#### Q. Tool이란 무엇인가요?
LLM은 텍스트 생성만 할 수 있을 뿐 실제 인터넷 검색이나 데이터 조회를 직접 하지 못합니다. **Tool**은 LLM이 외부 세상(네이버 API, 유튜브 API, 데이터베이스 등)과 상호작용할 수 있도록 제공하는 파이썬 함수입니다.

#### 💡 개발 핵심 원칙: "Docstring과 Type Hint가 생명입니다"
LLM은 함수의 **내부 소스 코드를 읽지 못합니다**. 오직 함수의 **이름(Name)**, **인자 타입(Type Hint)**, 그리고 **함수 설명(Docstring)**만을 읽고 어떤 도구를 호출할지 판단합니다.
- Docstring이 모호하면 LLM이 엉뚱한 도구를 호출하거나 필요한 인자를 빠뜨립니다.
- 반환값은 항상 **문자열(`str`)** 형태여야 LLM이 답변에 활용할 수 있습니다.
- 예외(Exception)가 발생하면 시스템이 다운되지 않도록 `try-except`로 감싸고 친절한 에러 안내 문자열을 반환하세요.

#### 📝 표준 코드 템플릿 (`src/modules/<모듈명>/tools.py`)
```python
# src/modules/sample_module/tools.py
from langchain_core.tools import tool
import requests

@tool
def search_company_info(company_name: str, detail_level: int = 1) -> str:
    """특정 기업의 기본 정보 및 최신 현황을 조회하는 도구입니다.

    Args:
        company_name (str): 조회를 원하는 회사명 (예: '삼성전자', '카카오').
        detail_level (int): 조회 상세 수준 (1: 기본 정보, 2: 재무 및 뉴스 포함). 기본값은 1.

    Returns:
        str: 조회된 기업 정보 텍스트 (실패 시 에러 설명 문자열).
    """
    try:
        # 1. 파라미터 전처리 및 외부 API 호출
        if not company_name.strip():
            return "회사명이 올바르지 않습니다. 빈 문자열이 아닌 유효한 회사명을 입력하세요."

        # 실제 API 호출 로직 (예시)
        response_text = f"[{company_name}] 기업 정보 조회 완료 (상세레벨: {detail_level})"
        return response_text

    except Exception as e:
        # LLM에게 오류 사실을 알림으로써 LLM이 다른 인자로 재시도할 수 있게 함
        return f"기업 정보 조회 실패: {str(e)}"
```

#### 🔌 모듈 등록 방법 (필수 2단계)
새로운 `@tool`을 작성했다면, 같은 폴더의 `module.py`에서 `get_tools()` 리스트에 등록해야 에이전트가 인식합니다:
```python
# src/modules/sample_module/module.py
from .tools import search_company_info  # 1. import 추가

class SampleModule(BaseAgentModule):
    ...
    def get_tools(self) -> List[BaseTool]:
        return [search_company_info]     # 2. 반환 리스트에 추가
```

---

### 2. Context (프롬프트 컨텍스트) 개발 가이드

#### Q. Context Provider는 왜 필요한가요?
여러 개발자가 하나의 거대한 시스템 프롬프트를 함께 수정하다 보면 Git 충돌이 빈번하게 발생합니다.  
`BaseContextProvider`를 사용하면 각 모듈 개발자가 **자신이 담당하는 도구의 사용 요령, 페르소나, 주의사항**을 자신의 폴더(`context.py`)에 격리하여 정의할 수 있으며, 런타임에 에이전트의 시스템 프롬프트에 자동으로 합쳐집니다.

#### 💡 개발 핵심 원칙: "명확한 지침과 불릿 포인트를 제공하세요"
- 어떤 상황에서 이 모듈의 도구를 써야 하는지(Trigger Condition) 명시합니다.
- 도구 호출 결과 데이터를 해석할 때 지켜야 할 가이드라인을 적습니다.

#### 📝 표준 코드 템플릿 (`src/modules/<모듈명>/context.py`)
```python
# src/modules/sample_module/context.py
from src.core.base import BaseContextProvider

class SampleContextProvider(BaseContextProvider):
    """샘플 도메인 전용 프롬프트 컨텍스트 공급자."""

    def get_system_prompt_snippet(self) -> str:
        """에이전트 시스템 프롬프트에 자동 병합될 도메인 지침"""
        return (
            "- 기업 분석 질의 인입 시 'search_company_info' 도구를 우선적으로 호출하십시오.\n"
            "- 기본 분석 시 detail_level=1을 사용하고, 심층 리포트 요청 시 detail_level=2를 사용하십시오.\n"
            "- 조회된 데이터 중 수치(매출, 영업이익 등)는 변경하지 말고 원본 그대로 인용하십시오."
        )
```

---

### 3. 가드레일(Guardrail) 개발 가이드

#### Q. 가드레일은 왜 필요한가요?
LLM은 때때로 API가 허용하지 않는 잘못된 파라미터(예: 음수 페이지, 미래 날짜, 0원 상품)를 전달하거나, API 응답에 HTML 태그, 광고성 스팸, 주민번호/전화번호 등 개인정보(PII)가 포함되어 있을 수 있습니다.  
가드레일은 이를 **사전 차단하거나 사후 정제**하여 시스템의 안정성과 보안을 보장합니다.

#### 🛡️ 3중 가드레일 방어선 구조
1. **1차: 입력 가드레일 (`validate_input`)**: 사용자 질문 자체를 LLM에 전달하기 전에 차단 (비속어, 탈옥 시도 등)
2. **2차: 도구 인자 가드레일 (`validate_tool_args`)**: LLM이 도구를 실행하기 직전에 파라미터 범위 및 타입 검증 (API 쿼터 낭비 및 400 에러 방지)
3. **3차: 출력 정제 가드레일 (`sanitize_output`)**: 도구 실행 결과에서 HTML 태그 제거, 개인정보 마스킹, 어뷰징 데이터 필터링

#### 📝 표준 코드 템플릿 (`src/modules/<모듈명>/guardrails.py`)
```python
# src/modules/sample_module/guardrails.py
import re
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult

class SampleGuardrail(BaseGuardrail):
    """샘플 도메인 가드레일 구현체."""

    def validate_input(self, query: str) -> GuardrailResult:
        """1단계: 사용자 질의 사전 검증"""
        banned_keywords = ["시스템삭제", "DROP TABLE", "비속어예시"]
        for word in banned_keywords:
            if word in query:
                return GuardrailResult(
                    passed=False,
                    error_message=f"질의에 허용되지 않는 단어('{word}')가 포함되어 있습니다."
                )
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        """2단계: 도구 실행 직전 파라미터 검증"""
        if tool_name == "search_company_info":
            detail_level = args.get("detail_level", 1)
            # detail_level이 1이나 2가 아니면 실행 거부
            if detail_level not in (1, 2):
                return GuardrailResult(
                    passed=False,
                    error_message=f"detail_level은 1 또는 2여야 합니다. (입력값: {detail_level})"
                )
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        """3단계: 도구 실행 직후 결과 정제"""
        if isinstance(output, str):
            # 1) 불필요한 HTML 태그 제거: <b>삼성전자</b> -> 삼성전자
            clean_text = re.sub(r"<.*?>", "", output)
            # 2) 전화번호(PII) 마스킹 처리 (010-XXXX-XXXX)
            clean_text = re.sub(r"01[016789]-\d{3,4}-\d{4}", "[전화번호 마스킹]", clean_text)
            return clean_text
        return output
```

---

### 4. 시나리오(Scenario) 개발 가이드

#### Q. 시나리오는 왜 필요한가요? (Tool과의 결정적 차이)
- **단일 Tool**: `search_youtube_videos`(유튜브 검색 1회), `get_shopping_trends`(트렌드 조회 1회) 같은 **단일 기능 단위**입니다.
- **시나리오**: "경쟁사 동향 리포트 작성", "신제품 크로스 트렌드 분석"처럼 **여러 개의 Tool을 순서대로 호출(Tool Chain)하고 결과를 종합해야 하는 복합 업무 단위**입니다.

도구가 20~30개로 늘어나면 단일 LLM 에이전트는 환각(Hallucination)에 빠져 툴을 엉뚱한 순서로 호출하거나 중요한 단계를 건너뜁니다.  
**시나리오 아키텍처**를 사용하면:
1. `ScenarioRouter`가 사용자의 질문을 보고 가장 적합한 시나리오를 자동 선택하고 파라미터를 추출합니다.
2. 해당 시나리오에 필요한 **정예 도구(3~4개)**만 선별 주입하여 안전한 순차 체인 파이프라인을 실행합니다.

#### 💡 개발 핵심 원칙: "파일 1개만 만들면 끝납니다 (Zero-Config)"
`src/scenarios/<시나리오명>/scenario.py` 파일을 만들고 `BaseScenario`를 상속받으면, `ScenarioRegistry`가 자동으로 스캔하여 등록하므로 별도의 등록 코드가 전혀 필요하지 않습니다.

#### 📝 표준 코드 템플릿 (`src/scenarios/<시나리오명>/scenario.py`)
```python
# src/scenarios/competitor_analysis/scenario.py
import logging
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from src.core.scenario import BaseScenario

logger = logging.getLogger(__name__)

# 1. 시나리오에 필요한 입력 파라미터를 Pydantic으로 정의합니다.
class CompetitorAnalysisParams(BaseModel):
    brand_name: str = Field(description="분석 대상 경쟁사 브랜드명 (예: '나이키', '아디다스')")
    period_days: int = Field(default=30, description="분석 대상 기간(일). 기본값은 30")


# 2. BaseScenario를 상속받아 시나리오 클래스를 구현합니다.
class CompetitorAnalysisScenario(BaseScenario):
    @property
    def name(self) -> str:
        """시나리오 고유 식별자 (영어 소문자/언더스코어)"""
        return "competitor_analysis"

    @property
    def description(self) -> str:
        """라우터가 사용자의 질문과 매칭할 때 읽는 상세 설명 (중요!)"""
        return "경쟁사 브랜드의 최신 유튜브 영상 반응과 대중 평가를 심층 분석하는 전문 시나리오"

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        """위에서 정의한 파라미터 모델을 지정합니다."""
        return CompetitorAnalysisParams

    @property
    def required_tool_names(self) -> List[str]:
        """이 시나리오에서 사용할 정예 Tool 이름들을 명시합니다. (필요한 도구만 주입받음)"""
        return ["search_youtube_videos", "get_video_comments"]

    def execute(
        self,
        params: CompetitorAnalysisParams,
        tools: Dict[str, BaseTool],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """실제 도구들을 순서대로 엮어서 실행하는 파이프라인(Chain)을 작성합니다."""
        logger.info("[시나리오 실행: %s] 대상 브랜드: %s", self.name, params.brand_name)
        llm = context.get("llm") if context else None

        # Step 1: 유튜브 영상 검색 도구 호출
        yt_tool = tools.get("search_youtube_videos")
        video_search_result = yt_tool.invoke({"query": params.brand_name, "max_results": 3})

        # Step 2: 댓글 수집 등 추가 체인 실행 (필요 시)
        # comments_tool = tools.get("get_video_comments")
        # comments_result = comments_tool.invoke(...)

        # Step 3: 수집된 결과를 LLM을 통해 종합 비즈니스 리포트로 변환
        if llm:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "당신은 브랜드 전략 컨설턴트입니다. 수집 데이터를 바탕으로 경쟁사 분석 리포트를 작성하세요."),
                ("human", "브랜드: {brand}\n수집 데이터:\n{data}")
            ])
            chain = prompt | llm
            response = chain.invoke({"brand": params.brand_name, "data": video_search_result})
            return response.content if hasattr(response, "content") else str(response)

        # LLM이 없을 경우 원본 결과 반환 (폴백)
        return f"### [{params.brand_name}] 분석 결과\n\n{video_search_result}"
```

---

## 👥 작업자(Worker) 역할 분담 및 협업 원칙

| 작업자 | 전담 디렉토리 | 도메인 | 보유 도구 (`@tool`) | 주요 가드레일 & 정제 규칙 |
| :--- | :--- | :--- | :--- | :--- |
| **Worker 1** | `src/modules/yt_search` | YouTube 영상/자막 | `search_youtube_videos`<br>`get_video_transcript` | • `max_results` (1~10) 제한<br>• 비어있거나 부적절한 `video_id` 검증 |
| **Worker 2** | `src/modules/yt_analytics` | YouTube 통계/댓글 | `get_channel_stats`<br>`get_video_comments` | • `max_comments` (1~50) 제한<br>• 댓글 내 이메일/전화번호(PII) 마스킹 정제 |
| **Worker 3** | `src/modules/naver_search` | 네이버 블로그/뉴스 | `search_naver_blog`<br>`search_naver_news` | • `display` (1~10), `sort` ('sim'/'date') 검증<br>• 응답 내 HTML 태그(`<b>` 등) 제거 |
| **Worker 4** | `src/modules/naver_shopping` | 네이버 쇼핑 데이터랩 트렌드 | `find_naver_category_code`<br>`get_shopping_trends`<br>`get_shopping_category_trend`<br>`get_shopping_category_gender_trend`<br>`get_shopping_category_age_trend`<br>`get_shopping_keyword_trend`<br>`get_shopping_keyword_gender_trend`<br>`get_shopping_keyword_age_trend` | • 날짜(YYYY-MM-DD) 형식 및 범위(2017-08-01~) 검증<br>• 분야 최대 3개 / 키워드 최대 5개 제한<br>• `time_unit` 값 검증<br>• `category_code` 미보유 시 로컬 카테고리 코드표(5,002건) 키워드 검색으로 자동 조회 |
| **Worker 5** | `src/modules/instagram` | 인스타그램 그래프 API | `search_hashtag_id`<br>`get_hashtag_recent_media`<br>`get_hashtag_top_media`<br>`get_competitor_profile` | • 해시태그 특수문자 정제<br>• target_username 및 ID 유효성 사전 검증<br>• 캡션 내 이메일/전화번호 마스킹 |

### Git 브랜치 전략 및 Main 병합 보호 룰 (Branch Protection Rules)
1. **단일 병합 경로 (Only from `dev`)**:
   - `main` 브랜치는 프로덕션 배포 전용 브랜치입니다.
   - `main` 브랜치로의 병합은 **오직 `dev` 브랜치를 통해서만 가능**하며, 개별 피처 브랜치(`feat/*`, `fix/*` 등)에서 `main`으로 직접 생성된 PR이나 직접 푸시는 원천 차단됩니다.
2. **2인 이상 승인 필수 (2 Reviewer Approvals Required)**:
   - `dev ➔ main` PR을 병합하려면 **반드시 최소 2명 이상의 동료 리뷰어 승인(Approval)**을 받아야 합니다.
3. **CI/테스트 100% 통과 필수**:
   - 병합 전 100% Mock 격리 단위/통합 테스트(`pytest tests/modules/ tests/core/`) 전건 통과가 필수입니다.

### Git 무충돌(Zero Merge Conflict) 원칙
1. **코어 동결 (Core Freeze)**: `src/core/` 디렉토리는 허가 없이 수정하지 않습니다.
2. **디렉토리 배타성**: 본인 전담 폴더(`src/modules/<worker>` 또는 `src/scenarios/<scenario>`) 안에서만 작업합니다.
3. **Graceful Degradation (우아한 기능 저하)**: 특정 API 키가 없어도 에러 없이 실행되며, 존재하는 키에 해당하는 도구만 자동으로 활성화됩니다.

---

## 🧪 테스트 및 품질 검증 가이드

본 프로젝트는 모든 외부 API 호출에 대해 Mocking이 100% 완비되어 있어 **API 쿼터 소모나 네트워크 환경에 구애받지 않고 2초 이내에 전체 테스트가 통과**합니다.

```bash
# 1. 전체 단위 테스트 일괄 실행 (124개 항목)
pytest tests/core tests/modules -v

# 2. 시나리오 및 라우터 단위 테스트만 실행
pytest tests/core/test_scenario.py -v

# 3. 본인 작업 모듈만 집중 테스트
pytest tests/modules/test_yt_search.py -v
```

---

## 📚 생성형 AI 서비스 개발 교재 마스터 위키 (`wiki/`)

교재 `(교재)AI캠퍼스_생성형AI_5.생성형 AI 서비스 개발_이미애.pdf`의 전 챕터(1~5장) 핵심 이론, 실습 코드, 그리고 본 프로젝트 소스 코드와의 심층 매핑 내역은 [`wiki/`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/) 디렉토리에 체계적으로 구축되어 있습니다.

- **[[Index] 마스터 위키 로드맵 & 아키텍처 점검표](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Index.md)**: 전체 5개 챕터 로드맵, 핵심 토픽 및 본 프로젝트 반영 점검표
- **[[Study] 챕터별 심층 스터디 허브](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Study.md)**: 챕터 1~5 심층 분석 및 실습 코드 중앙 허브
  - [📘 Ch 1. Introduction (패러다임 진화, ReAct, 거버넌스 8대 체크리스트)](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Chapter_1_Introduction.md)
  - [📘 Ch 2. LLM Foundations (토큰 예측, 6대 기술, 3대 SDK 제어)](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Chapter_2_LLM_Foundations.md)
  - [📘 Ch 3. LangChain (4대 추상화, Structured Output, LCEL, Tool Calling)](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Chapter_3_LangChain.md)
  - [📘 Ch 4. Basic Agent (7단계 라이프사이클, Checkpointer, Mocking 철학)](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Chapter_4_Basic_Agent.md)
  - [📘 Ch 5. Advanced Agent (Runtime Context, 미들웨어, 다계층 가드레일, 장기 기억)](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Chapter_5_Advanced_Agent.md)
  - [📘 [부록] 시스템 관측성 & 로깅 6대 이슈 트러블슈팅](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Appendix_Observability_Troubleshooting.md)


---

## 🧭 하네스 엔지니어링 Handoff 센터 (`handoff/index.md`)

신규 작업자 온보딩, 코드 스타일, 아키텍처 구조 및 하네스 엔지니어링 가이드는 [`handoff/`](handoff/index.md) 디렉토리에 구축되어 있습니다.

- [🎨 1. 코드 스타일 가이드 (`handoff/01_code_style.md`)](handoff/01_code_style.md)
- [🏛️ 2. 현재 아키텍처 구조 (`handoff/02_architecture.md`)](handoff/02_architecture.md)
- [📜 3. 작성 준수 사항 (`handoff/03_guidelines.md`)](handoff/03_guidelines.md)
- [🧪 4. 테스트 및 하네스 엔지니어링 (`handoff/04_testing_harness.md`)](handoff/04_testing_harness.md)
- [🚀 5. 신규 모듈/시나리오 확장 가이드 (`handoff/05_extension_guide.md`)](handoff/05_extension_guide.md)
- [🛠️ 6. 트러블슈팅 및 운영 가이드 (`handoff/06_troubleshooting.md`)](handoff/06_troubleshooting.md)

---

## 📜 라이선스
MIT License


