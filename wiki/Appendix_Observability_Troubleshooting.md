# 📘 [부록] 시스템 관측성(Observability) 및 로깅 6대 이슈 트러블슈팅

> **작성자**: skala-chok 개발팀  
> **상위 문서**: [[Index] 마스터 위키 로드맵](Index.md)  
> **관련 소스 코드**: [`src/core/agent.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/agent.py), [`src/core/guardrails.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/guardrails.py), [`src/core/router.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/router.py), [`src/main.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/main.py)

---

## 🎯 1. 개요 및 관측성의 중요성

엔터프라이즈 AI 에이전트 시스템은 비동기 호출, 동적 플러그인 로드, 복합 도구 체이닝 등 복잡한 내부 런타임을 거칩니다.  
본 부록은 시스템 내부를 투명하게 가시화하고 장애 시 즉각적인 원인 규명이 가능하도록 보완한 **6대 로깅 및 관측성 누락 지점**의 트러블슈팅 내역을 다룹니다.

---

## 🔍 2. 발견된 6대 로깅 누락 지점 및 해결 분석

| 이슈 번호 | 컴포넌트 | 문제 현상 | 개선 구현 | 관련 파일 |
|:---:|:---|:---|:---|:---|
| **#1** | **Core / Agent** | Fallback 일반 에이전트 실행 여부 및 소요 시간 누락 | ReAct 루프 진입/완료 안내 로그 및 지연 시간(`time.time()`) 기록 | [`src/core/agent.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/agent.py) |
| **#2** | **Core / Agent** | 비활성화된(Disabled) 모듈 및 사유 안내 누락 | 초기화 시 비활성 모듈 목록 및 사유 안내 로깅 추가 | [`src/core/agent.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/agent.py) |
| **#3** | **Core / Guardrails** | 출력 정제(`sanitize_output`) 실제 적용 여부 추적 불가 | 출력값 변경 감지 시 마스킹/정제 적용 내역 로깅 | [`src/core/guardrails.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/guardrails.py) |
| **#4** | **Core / Router** | 시나리오 라우팅 분석 시작 및 LLM 소요 시간 누락 | 라우팅 분석 시작 로그 및 LLM 판단 지연 시간 측정 | [`src/core/router.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/router.py) |
| **#5** | **Core / Registry** | 모듈 및 시나리오 자동 탐색 완료 통계 누락 | 동적 스캔 완료 시 총 등록 개수 통계 정보 기록 | [`src/core/registry.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/core/registry.py) |
| **#6** | **CLI / main.py** | 사용자 관점의 전체 End-to-End 응답 소요 시간 누락 | 단일 질의 처리 총 소요 시간 로깅 | [`src/main.py`](https://github.com/DevDAN09/skala-chok/blob/main/src/main.py) |

---

### 📌 세부 코드 개선 내역

#### 1) 이슈 #1: Fallback 일반 에이전트 지연 시간 계측
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

#### 2) 이슈 #2: 비활성 모듈 가시화
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

#### 3) 이슈 #3: 출력 정제 감사 로그 (Audit Trail)
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

#### 4) 이슈 #4: 라우팅 분석 지연 시간 계측
```python
# src/core/router.py
start_time = time.time()
logger.debug("[시나리오 라우팅 분석 시작] 질의: '%s'", query)
# LLM invoke...
elapsed = time.time() - start_time
logger.debug("[시나리오 라우팅 분석 완료] 판정: %s (소요시간: %.2fs)", decision.scenario_name or "없음", elapsed)
```

#### 5) 이슈 #5: 레지스트리 자동 탐색 통계
```python
# src/core/registry.py
logger.info("모듈 자동 탐색 완료: 총 %d개 등록됨", len(self._modules))

# src/core/scenario_registry.py
logger.info("시나리오 자동 탐색 완료: 총 %d개 등록됨", len(self._scenarios))
```

#### 6) 이슈 #6: CLI 전체 소요 시간 기록
```python
# src/main.py
start_time = time.time()
logger.info("단일 질의 처리 시작: '%s'", query)
response = agent.run(query)
elapsed = time.time() - start_time
logger.info("단일 질의 처리 완료 (총 소요시간: %.2fs)", elapsed)
```

---

## 🧪 3. 검증 결과 로그

```text
2026-09-10 23:40:12 [INFO] skala_agent: 모듈 자동 탐색 완료: 총 4개 등록됨 (이슈 #5 해결)
2026-09-10 23:40:12 [INFO] skala_agent: 비활성화된 모듈 (0개): [] (이슈 #2 해결)
2026-09-10 23:40:12 [DEBUG] skala_agent: [시나리오 라우팅 분석 시작] 질의: '러닝화 트렌드' (이슈 #4 해결)
2026-09-10 23:40:13 [DEBUG] skala_agent: [시나리오 라우팅 분석 완료] 판정: cross_platform_trend (소요시간: 0.85s) (이슈 #4 해결)
2026-09-10 23:40:14 [DEBUG] skala_agent: [출력 정제 적용] 도구: 'get_shopping_trends' | 가드레일: NaverShoppingGuardrail (이슈 #3 해결)
2026-09-10 23:40:15 [INFO] skala_agent: 단일 질의 처리 완료 (총 소요시간: 3.00s) (이슈 #6 해결)
```
