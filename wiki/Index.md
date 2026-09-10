# 📚 [Index] 프로젝트 개발 & 이슈 현황 위키

> **LangChain Multi-Worker & Model-Driven Scenario Agent 시스템 위키**  
> 본 위키는 프로젝트의 핵심 아키텍처, 개발 가이드, 그리고 시스템 개선 과정에서 도출된 이슈와 기술적 분석(Study)을 체계적으로 관리합니다.

---

## 🧭 위키 내비게이션

- **[Index] (현재 페이지)**: 전체 위키 목차 및 이슈 1~6 현황 대시보드
- **[[Study] 기술 분석 및 트러블슈팅 노트](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Study.md)**: 이슈 1~6 심층 원인 분석, 학습 포인트(Best Practices), Before/After 코드
- **[메인 README 개발 가이드](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/README.md)**: 빠른 시작(Quickstart), 4대 핵심 개발 가이드, 레인보우 로드맵

---

## 📊 시스템 개선 이슈 1~6 현황 대시보드

시스템의 관측성(Observability) 및 디버깅 편의성을 위해 코어 및 CLI 전반에 걸쳐 도출되고 해결된 6대 핵심 이슈입니다.

| 번호 | 구분 / 컴포넌트 | 이슈 내용 (Problem) | 개선 조치 (Resolution) | 상태 | 관련 소스 코드 |
|:---:|:---|:---|:---|:---:|:---|
| **#1** | **Core / Agent** | Fallback 일반 에이전트 실행 및 소요 시간 누락 | ReAct 루프 진입/종료 로그 및 지연 시간(`time.time()`) 기록 | `Resolved` | [`src/core/agent.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/agent.py) |
| **#2** | **Core / Agent** | API 키 누락 등으로 비활성화된(Disabled) 모듈 안내 누락 | 초기화 시 비활성 모듈 목록 및 사유 안내 로깅 추가 | `Resolved` | [`src/core/agent.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/agent.py) |
| **#3** | **Core / Guardrails** | 출력 정제(`sanitize_output`) 실제 적용 여부 추적 불가 | 출력값 변경 감지 시 마스킹/정제 적용 내역 로깅 | `Resolved` | [`src/core/guardrails.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/guardrails.py) |
| **#4** | **Core / Router** | 시나리오 라우팅 분석 시작 및 LLM 소요 시간 누락 | 라우팅 분석 시작 로그 및 LLM 판단 지연 시간 측정 | `Resolved` | [`src/core/router.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/router.py) |
| **#5** | **Core / Registry** | 모듈 및 시나리오 자동 탐색(Auto-Discovery) 완료 통계 누락 | 동적 스캔 완료 시 총 등록 개수 통계 정보 기록 | `Resolved` | [`src/core/registry.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/registry.py) |
| **#6** | **CLI / main.py** | 질의 처리 전체 End-to-End 응답 소요 시간 누락 | 사용자 관점의 단일 질의 처리 총 소요 시간 로깅 | `Resolved` | [`src/main.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/main.py) |

> 💡 각 이슈별 상세한 원인 분석, 왜 중요한지에 대한 기술적 학습(Study), Before/After 구현 코드 및 검증 결과는 **[[Study] 문서](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Study.md)**에서 확인하실 수 있습니다.

---

## 🛠️ 모듈 및 시나리오 개발 로드맵 요약

신규 작업자(Worker)는 **레인보우(무지개색 점 🔴 ➔ 🟠 ➔ 🟡 ➔ 🟢 ➔ 🔵 ➔ 🟣)** 가이드에 따라 개발을 진행합니다.

1. 🔴 **[Step 1]** `client.py`: 외부 API 통신 클라이언트 (HTTP, 인증, 파싱)
2. 🟠 **[Step 2]** `guardrails.py`: [`BaseGuardrail`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/guardrail.py) 상속 (입력 검증 & 출력 마스킹)
3. 🟡 **[Step 3]** `tools.py`: LangChain `@tool` 선언 (Docstring & Type Hint)
4. 🟢 **[Step 4]** `context.py`: [`BaseContextProvider`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/context.py) 상속 (도메인 프롬프트 가이드)
5. 🔵 **[Step 5]** `module.py`: [`BaseAgentModule`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/module.py) 상속 (모듈 패키징 및 등록)
6. 🟣 **[Step 6]** `tests/modules/`: 100% Mock 기반 단위 테스트 검증
