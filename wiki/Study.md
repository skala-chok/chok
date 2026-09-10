# 📖 [Study] 생성형 AI 서비스 개발 교재 챕터별 심층 스터디 허브

> **교재**: `(교재)AI캠퍼스_생성형AI_5.생성형 AI 서비스 개발_이미애.pdf`  
> **상위 문서**: [[Index] 마스터 위키 로드맵](Index.md)

본 문서는 교재의 1장부터 5장까지의 핵심 이론, 실습 코드, 엔터프라이즈 아키텍처를 상세하게 정리한 챕터별 심층 스터디 가이드로 연결되는 중앙 허브입니다.

---

## 📚 챕터별 심층 스터디 문서 바로가기

### 1. [Chapter 1. Introduction](Chapter_1_Introduction.md)
- **부제**: AI Application 패러다임과 AI Agent 거버넌스
- **핵심 내용**: 전통 SW vs AI Agent 4단계 패러다임 비교, Luke Wroblewski 6단계 진화 모델, ReAct 루프 구조도, 에이전트 역전 현상(RentAHuman.ai), OWASP Top 10 for LLM / NIST AI RMF / EU AI Act 글로벌 보안 규제, 8대 엔터프라이즈 체크리스트

### 2. [Chapter 2. LLM Foundations](Chapter_2_LLM_Foundations.md)
- **부제**: 오픈소스·상용 파운데이션 모델 활용과 API 제어
- **핵심 내용**: 다음 토큰 예측 원리와 생성 제어 하이퍼파라미터(Temperature, top_p, top_k), LLM 태생적 한계를 극복하는 6대 핵심 기술, 2025~2026 글로벌 파운데이션 모델 비교표, 3대 SDK 실습(Hugging Face Pipeline, Google GenAI SDK, OpenAI SDK)

### 3. [Chapter 3. LangChain](Chapter_3_LangChain.md)
- **부제**: 핵심 컴포넌트, LCEL 파이프라인 및 Tool Calling
- **핵심 내용**: LangChain 4대 추상화 계층, Messages 4대 계층과 tool_call_id 1:1 매핑, Pydantic 기반 Structured Output 강제, LCEL 파이프라인 및 고급 Runnable(`RunnableParallel`, `RunnableBranch`), 커스텀 도구(`@tool`) 작성 4대 수칙

### 4. [Chapter 4. Basic Agent](Chapter_4_Basic_Agent.md)
- **부제**: 도구 바인딩, 단기 메모리(Checkpointer)와 구조화된 출력
- **핵심 내용**: Agent 7단계 순환 라이프사이클 시퀀스, 단기 메모리 Checkpointer(`InMemorySaver`)와 `thread_id` 세션 격리 아키텍처, `ToolStrategy` 비즈니스 파이프라인 연계, `LLMToolEmulator` 가상 모킹 철학

### 5. [Chapter 5. Advanced Agent](Chapter_5_Advanced_Agent.md)
- **부제**: 런타임 상태 제어, 미들웨어, 가드레일 및 장기 메모리
- **핵심 내용**: Runtime Context 주입 및 `@wrap_model_call` 동적 프롬프트 제어, 빌트인/커스텀 미들웨어(HITL, PII 마스킹, ToDoList, Summarization), Before/Tool/After 3단계 다계층 가드레일, Store 기반 장기 메모리 네임스페이스 아키텍처

### 6. [부록: 시스템 관측성 및 로깅 6대 이슈 트러블슈팅](Appendix_Observability_Troubleshooting.md)
- **부제**: 실무 프로덕션 관측성(Observability) 강화 리포트
- **핵심 내용**: Fallback 에이전트 지연 시간 계측, 비활성 모듈 가시화, 출력 정제 감사 로그, 라우팅 분석 레이턴시 계측, 자동 탐색 통계, CLI 전체 응답 시간 로깅
