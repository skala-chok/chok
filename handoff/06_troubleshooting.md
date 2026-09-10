# 🛠️ 6. 트러블슈팅 및 운영 가이드 (Troubleshooting & Ops Guide)

본 문서는 에이전트 시스템 실행, 테스트, 운영 중 자주 마주칠 수 있는 문제 상황과 그에 대한 원인 분석 및 해결 절차를 안내합니다.

---

## 🚨 1. 빈번한 문제 상황 및 해결 가이드

### 1.1 모듈이 비활성화되어 도구가 보이지 않는 경우
- **증상**: CLI 실행 시 특정 도구가 호출되지 않고, 로그에 `비활성화된 모듈: ['yt_search'] (필수 API 키/설정 미부여)` 경고가 출력됨.
- **원인**: `.env` 파일에 해당 모듈 구동에 필요한 필수 환경변수(예: `YOUTUBE_API_KEY`)가 누락되었거나 빈 값임.
- **해결 절차**:
  1. 루트 디렉토리에 `.env` 파일이 존재하는지 확인 (`.env.example` 복사본).
  2. 필요한 API 키를 올바르게 입력.
  3. 가상환경 활성화 후 다시 실행:
     ```bash
     python -m src.main -q "테스트 질의"
     ```

---

### 1.2 가드레일 인자 검증 차단 (`[가드레일 검증 실패]`)
- **증상**: 에이전트 응답에 `[가드레일 검증 실패] display 파라미터는 1 이상 10 이하여야 합니다.` 메시지가 나타남.
- **원인**: LLM 모델이 프롬프트 해석 과정에서 도구의 파라미터 제약 범위를 초과하는 인자(예: `display=50`)를 생성하여 호출함.
- **해결 절차**:
  1. `src/modules/<module_name>/tools.py`의 Docstring에 파라미터 범위 제약 조건을 더 강하게 명시.
     ```python
     """... display: 반환할 결과 개수 (반드시 1 이상 10 이하의 정수여야 합니다)."""
     ```
  2. 도메인 프롬프트 스니펫(`context.py`)에 도구 호출 시 기본 파라미터 권장값을 추가.

---

### 1.3 가짜 LLM(`ToolCallingFakeChat`) 사용 시 라우터 출력 파싱 예외
- **증상**: 통합 테스트(`test_integration.py`) 실행 시 `ScenarioRoutingDecision` 파싱 단계에서 `Unknown tool type: 'xxx'` 에러 발생.
- **원인**: `AgentRunner` 내부에서 시나리오 라우터가 `llm.with_structured_output`을 사용하는데, 테스트용 `fake_llm`이 시나리오 판단 결과가 아닌 일반 비즈니스 도구 호출 메시지를 먼저 반환하여 파서와 불일치 발생.
- **해결 절차**:
  - `AgentRunner` 초기화 시 `router=None`을 전달하여 라우터를 비활성화하고 순수 ReAct 체인만 테스트하거나,
  - `fake_llm`의 첫 번째 응답에 `ScenarioRoutingDecision`에 해당하는 구조화된 Tool Call 메시지를 주입.

---

### 1.4 외부 API Rate Limit (429 Too Many Requests)
- **증상**: 라이브 환경에서 연속 질문 시 외부 검색 API에서 429 에러 반환.
- **원인**: 네이버 또는 유튜브의 초당 호출 제한 초과.
- **해결 절차**:
  - `client.py`에서 `time.sleep` 또는 `tenacity` 라이브러리를 활용한 Exponential Backoff 재시도 로직 적용.
  - 가드레일 단계에서 캐싱(Cache) 계층을 두어 동일 질의에 대한 외부 API 중복 호출 억제.

---

## 🔍 2. 디버깅 및 관찰성(Observability) 확보

### 2.1 디버그 로그 레벨 활성화
문제의 원인을 파악하기 위해 상세 디버그 로그를 출력합니다.
```bash
python -m src.main --log-level DEBUG -q "상세 분석이 필요한 질문"
```

### 2.2 핵심 관찰 로그 포인트:
1. `[사전 가드레일 차단]`: 악성 입력이 `validate_input`에서 걸러졌는지 확인.
2. `[시나리오 라우팅 분석]`: LLM이 시나리오를 선택한 이유(`reasoning`) 및 신뢰도(`confidence`) 확인.
3. `[도구 호출 시작] & [도구 실행 완료]`: 실제 도구로 넘어간 인자와 소요 시간(`elapsed`) 확인.
4. `[출력 정제 적용]`: PII 마스킹이나 HTML 정제가 정상적으로 수행되었는지 확인.
