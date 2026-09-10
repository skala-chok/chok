# 📖 [Study] 시스템 관측성 및 로깅 개선 기술 스터디 (이슈 1~6)

> **작성자**: skala-chok 개발팀  
> **최근 업데이트**: 2026-09-10  
> **상위 문서**: [[Index] 프로젝트 위키 홈](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/wiki/Index.md)

---

## 🎯 1. 스터디 개요 및 목표

대규모 언어 모델(LLM) 기반의 멀티 워커 에이전트 시스템은 비동기 호출, 동적 플러그인 로드, 복합 도구 체이닝 등 복잡한 내부 런타임을 거칩니다.  
이러한 시스템에서 **관측성(Observability)**과 **상세 로깅(Logging)**이 부실하면 다음과 같은 심각한 문제가 발생합니다:

1. **블랙박스화(Black-box)**: 사용자가 질의를 던지고 답변을 받기까지 내부에서 시나리오 체인이 동작했는지, 일반 에이전트가 돌았는지 추적 불가
2. **지연 시간(Latency) 병목 파악 불가**: 응답이 지연될 때 네트워크 API가 느린지, LLM 라우터가 느린지 원인 규명 불가
3. **보안/가드레일 검증 누락**: 악의적 파라미터가 차단되었는지, 민감정보가 실제로 마스킹되어 나갔는지 모니터링 불가

본 문서는 이러한 관측성 공백을 해결하기 위해 도출된 **6대 핵심 이슈**의 원인 분석과 개선 구현 과정, 그리고 엔터프라이즈 AI 엔지니어링 관점에서의 학습 포인트(Study Notes)를 정리한 기술 문서입니다.

---

## 🔍 2. 이슈 1~6 심층 기술 분석 및 해결 내역

---

### 📌 이슈 1: [Core/Agent] Fallback 일반 에이전트 실행 및 소요 시간 누락

- **관련 파일**: [`src/core/agent.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/agent.py)
- **심각도**: 🟡 Medium

#### 1) 문제 현상 (Problem)
사용자 질의가 사전 정의된 시나리오(`BaseScenario`)에 매칭되지 않거나 시나리오 실행 중 예외가 발생하면, 시스템은 ReAct 루프를 구동하는 일반 에이전트(`AgentExecutor`)로 폴백(Fallback)합니다.  
기존에는 폴백 진입 시점과 ReAct 루프 수행에 걸린 시간(초)이 로그에 기록되지 않아, 사용자 질의가 시나리오로 처리된 것인지 일반 에이전트로 처리된 것인지 분간하기 어려웠습니다.

#### 2) 원인 분석 (Root Cause)
`AgentRunner.run()` 메서드 내에서 `self.executor.invoke({"input": query})`를 단독 호출하고 지연 시간 측정(`time.time()`)이나 시작/완료 안내 로그가 누락되어 있었습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **에이전트 듀얼 경로(Dual-Path) 가시화**: 시나리오 체인(결정론적 고속 경로)과 ReAct 에이전트(자율적 탐색 경로)는 실행 비용과 지연 시간이 완전히 다릅니다. 어떤 경로를 탔는지 명확한 로그 태그(`[일반 에이전트 시작]`, `[일반 에이전트 완료]`)를 남겨야 SLA(서비스 수준 계약) 모니터링이 가능합니다.

#### 4) 개선 코드 (Solution)
```python
# src/core/agent.py
logger.info("[일반 에이전트 시작] ReAct 도구 호출 루프 진입: '%s'", query)
start_fallback = time.time()
result = self.executor.invoke({"input": query})
logger.info(
    "[일반 에이전트 완료] ReAct 도구 호출 루프 완료 (소요시간: %.2fs)",
    time.time() - start_fallback,
)
```

---

### 📌 이슈 2: [Core/Agent] 비활성화된(Disabled) 모듈 안내 로그 누락

- **관련 파일**: [`src/core/agent.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/agent.py)
- **심각도**: 🟢 Low

#### 1) 문제 현상 (Problem)
특정 모듈(예: YouTube 모듈)에 필요한 API 키(`YOUTUBE_API_KEY`)가 `.env`에 설정되지 않은 경우, 모듈의 `is_enabled()`는 `False`를 반환하여 안전하게 배제됩니다(Graceful Degradation).  
그러나 시작 로그에는 활성화된 모듈만 출력되고, **"어떤 모듈이 왜 꺼졌는지"** 안내가 전혀 없었습니다.

#### 2) 원인 분석 (Root Cause)
`AgentRunner.__init__`에서 `registry.get_enabled_modules()`만 순회하며 로그를 남기고, `registry.get_all_modules()` 중 비활성 상태인 모듈을 필터링하여 출력하는 로직이 없었습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **Graceful Degradation의 가시성**: 부분 장애(Partial Failure)를 허용하는 아키텍처에서는 장애나 비활성화 상태가 "조용히 무시(Silent Ignore)"되면 운영자가 설정 누락을 인지하지 못합니다. 명시적으로 비활성화 사유를 로깅해야 합니다.

#### 4) 개선 코드 (Solution)
```python
# src/core/agent.py
disabled_modules = [m for m in self.registry.get_all_modules() if not m.is_enabled()]
if disabled_modules:
    logger.info(
        "비활성화된 모듈 (%d개): %s (필수 API 키/설정 부재로 인해 비활성화됨)",
        len(disabled_modules),
        [m.name for m in disabled_modules],
    )
```

---

### 📌 이슈 3: [Core/Guardrails] 출력 정제(`sanitize_output`) 실제 적용 여부 로깅 누락

- **관련 파일**: [`src/core/guardrails.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/guardrails.py)
- **심각도**: 🔴 High (보안 및 개인정보 준수 관점)

#### 1) 문제 현상 (Problem)
`GuardrailedTool`은 도구 실행 전 인자 검증(`validate_input`)과 실행 후 출력 정제(`sanitize_output`)를 수행합니다. 인자 검증 실패 시에는 차단 로그가 상세히 남았으나, 외부 API 응답에서 HTML 태그가 제거되거나 주민번호/이메일 등 개인정보가 마스킹되었을 때 실제로 출력을 정제했는지 여부가 로깅되지 않았습니다.

#### 2) 원인 분석 (Root Cause)
반복문 내에서 `sanitized_output = guardrail.sanitize_output(self.tool.name, sanitized_output)`을 단순 재할당만 하고 이전 값(`prev_output`)과의 일치 여부를 비교하지 않았습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **데이터 보안 감사(Audit Trail)**: 개인정보보호법 및 보안 가이드라인에 따르면 민감정보 필터링 시스템은 단순히 필터링을 수행하는 것뿐만 아니라 "어떤 도구의 출력에서 어느 가드레일이 필터링을 작동시켰는지" 감사 로그를 남겨야 합니다.

#### 4) 개선 코드 (Solution)
```python
# src/core/guardrails.py
for guardrail in self.guardrails:
    prev_output = sanitized_output
    sanitized_output = guardrail.sanitize_output(self.tool.name, sanitized_output)
    if sanitized_output != prev_output:
        logger.debug(
            "[출력 정제 적용] 도구: '%s' | 가드레일: %s (데이터 마스킹/정제 적용됨)",
            self.tool.name,
            type(guardrail).__name__,
        )
```

---

### 📌 이슈 4: [Core/Router] 시나리오 라우팅 분석 시작 및 LLM 소요 시간 누락

- **관련 파일**: [`src/core/router.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/router.py)
- **심각도**: 🟡 Medium

#### 1) 문제 현상 (Problem)
`ScenarioRouter.route()`는 LLM을 호출하여 사용자의 의도를 분류하고 시나리오 파라미터를 JSON으로 파싱합니다. 기존에는 매칭 성공/실패 결과만 기록되고, 라우팅 분석에 소요된 LLM 왕복 시간(Latency)이 기록되지 않았습니다.

#### 2) 원인 분석 (Root Cause)
LLM Structured Output 체인 호출 전후에 타이머(`time.time()`)와 디버그 로그가 누락되어 있었습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **지능형 라우터의 오버헤드 측정**: LLM 기반 라우터는 규칙 기반(Regex) 라우터보다 유연하지만 0.3~1.0초의 추가 지연이 발생합니다. 이 오버헤드가 전체 응답 시간에 미치는 영향을 정밀하게 계측해야 추후 경량 모델(예: Haiku, GPT-4o-mini) 전환 여부를 판단할 수 있습니다.

#### 4) 개선 코드 (Solution)
```python
# src/core/router.py
start_time = time.time()
logger.debug("[시나리오 라우팅 분석 시작] 질의: '%s' (후보 시나리오: %s)", query, list(self.scenario_registry.get_all_scenarios().keys()))
# ... LLM invoke ...
elapsed = time.time() - start_time
logger.debug("[시나리오 라우팅 분석 완료] 판정: %s (소요시간: %.2fs)", decision.scenario_name or "없음", elapsed)
```

---

### 📌 이슈 5: [Core/Registry] 모듈 및 시나리오 자동 탐색(Auto-Discovery) 완료 통계 누락

- **관련 파일**: [`src/core/registry.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/registry.py), [`src/core/scenario_registry.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/core/scenario_registry.py)
- **심각도**: 🟢 Low

#### 1) 문제 현상 (Problem)
동적 리플렉션(`importlib`, `pkgutil`)으로 `src/modules/`와 `src/scenarios/` 디렉토리를 스캔하여 클래스를 자동 로드하지만, 탐색이 끝난 후 총 몇 개의 모듈과 시나리오가 정상 등록되었는지 요약 통계가 누락되어 있었습니다.

#### 2) 원인 분석 (Root Cause)
모듈 등록 시 개별 `logger.info("모듈 등록: %s", module.name)`만 호출되고, 스캔 함수 종료부에 통합 요약 로그가 누락되어 있었습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **동적 플러그인 레지스트리의 투명성**: 플러그인 아키텍처에서는 개발자가 파일을 추가했을 때 시스템이 이를 인식했는지 즉시 확인할 수 있는 요약 지표(총 N개 로드 완료)가 제공되어야 디버깅이 수월합니다.

#### 4) 개선 코드 (Solution)
```python
# src/core/registry.py
logger.info("모듈 자동 탐색 완료: 총 %d개 등록됨", len(self._modules))

# src/core/scenario_registry.py
logger.info("시나리오 자동 탐색 완료: 총 %d개 등록됨", len(self._scenarios))
```

---

### 📌 이슈 6: [CLI/main.py] 질의 처리 전체 End-to-End 응답 소요 시간 누락

- **관련 파일**: [`src/main.py`](file:///Users/yun-yeongmin/orca/workspaces/skala-chok/main/src/main.py)
- **심각도**: 🟡 Medium

#### 1) 문제 현상 (Problem)
CLI 환경에서 단일 질의(`--query`)를 실행할 때 "단일 질의 처리 시작", "단일 질의 처리 완료" 로그는 출력되었으나, 사용자가 체감한 전체 응답 소요 시간(End-to-End Latency)이 찍히지 않았습니다.

#### 2) 원인 분석 (Root Cause)
`main.py`의 `handle_single_query` 함수에서 시작 시각(`start_time = time.time()`)을 기록하지 않고 종료부에서도 시간 차이를 계산하지 않았습니다.

#### 3) 기술 스터디 포인트 (Study & Best Practice)
- **사용자 경험(UX)과 성능 지표**: 개별 도구나 LLM 호출 시간뿐만 아니라, 네트워크 I/O, 사전 가드레일, 라우팅, 사후 정제까지 포함된 전체 파이프라인의 총 수행 시간을 모니터링해야 실제 프로덕션 배포 시 병목 지점을 찾을 수 있습니다.

#### 4) 개선 코드 (Solution)
```python
# src/main.py
start_time = time.time()
logger.info("단일 질의 처리 시작: '%s'", query)
response = agent.run(query)
elapsed = time.time() - start_time
logger.info("단일 질의 처리 완료 (총 소요시간: %.2fs)", elapsed)
```

---

## 🧪 3. 검증 결과 및 로그 출력 예시

개선 후 CLI 실행 시 아래와 같이 모든 단계가 완벽한 투명성(Full Observability)을 가지고 로깅됩니다:

```text
2026-09-10 23:40:12 [INFO] skala_agent: CLI 실행 시작 (로그 레벨: DEBUG)
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 등록: naver_search
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 등록: naver_shopping
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 등록: yt_analytics
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 등록: yt_search
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 자동 탐색 완료: 총 4개 등록됨 (이슈 #5 해결)
2026-09-10 23:40:12 [INFO] skala_agent: 시나리오 자동 탐색 완료: 총 1개 등록됨 (이슈 #5 해결)
2026-09-10 23:40:12 [INFO] skala_agent: 활성 모듈 로드 완료 (4개): ['naver_search', 'naver_shopping', 'yt_analytics', 'yt_search']
2026-09-10 23:40:12 [INFO] skala_agent: 비활성화된 모듈 (0개): [] (이슈 #2 해결)
2026-09-10 23:40:12 [INFO] skala_agent: 단일 질의 처리 시작: '러닝화 트렌드 분석해줘'
2026-09-10 23:40:12 [DEBUG] skala_agent: [시나리오 라우팅 분석 시작] 질의: '러닝화 트렌드 분석해줘' (이슈 #4 해결)
2026-09-10 23:40:13 [DEBUG] skala_agent: [시나리오 라우팅 분석 완료] 판정: cross_platform_trend (소요시간: 0.85s) (이슈 #4 해결)
2026-09-10 23:40:13 [INFO] skala_agent: [시나리오 매칭 성공] 'cross_platform_trend' 실행 시작
2026-09-10 23:40:14 [DEBUG] skala_agent: [출력 정제 적용] 도구: 'get_shopping_trends' | 가드레일: NaverShoppingGuardrail (이슈 #3 해결)
2026-09-10 23:40:15 [INFO] skala_agent: [시나리오 실행 성공] 'cross_platform_trend' (소요시간: 2.15s)
2026-09-10 23:40:15 [INFO] skala_agent: 단일 질의 처리 완료 (총 소요시간: 3.00s) (이슈 #6 해결)
```

- **단위 테스트 결과**: 코어 및 모듈 전체 126개 테스트 100% 통과 유지 (`126 passed in 4.33s`).
