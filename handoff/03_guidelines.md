# 📜 3. 작성 준수 사항 및 개발 원칙 (Development Guidelines)

본 문서는 `skala-chok` 프로젝트에 신규 코드를 추가하거나 기존 모듈을 수정할 때 반드시 준수해야 하는 핵심 엔지니어링 원칙, 보안 지침 및 제약 사항을 정의합니다.

---

## 🚫 1. 모듈 간 무의존성 원칙 (Zero Cross-Module Dependency)

본 프로젝트는 여러 작업자가 각자의 도메인 모듈(Worker)을 독립적으로 개발하고 유지보수할 수 있는 멀티 작업자 환경을 지향합니다.

### 🔴 엄격 금지 사항
- **모듈 간 직접 임포트 금지**: `src/modules/A`가 `src/modules/B`의 클래스, 함수, 상수를 직접 임포트하는 행위를 엄격히 금지합니다.
  ```python
  # ❌ 절대 금지 (Cross-module dependency)
  from src.modules.naver_search.client import NaverSearchClient
  from src.modules.yt_analytics.tools import get_video_comments
  ```
- **공통 자원 분리 원칙**: 두 모듈 이상에서 공통으로 필요한 유틸리티나 인터페이스는 반드시 `src/core/` 또는 `src/config.py`로 승격시켜 공유해야 합니다.
- **결합도 최소화**: 모듈은 오직 `src/core/base.py`의 추상 인터페이스(`BaseAgentModule`, `BaseGuardrail`, `BaseContextProvider`)와 `src/config.py`의 `settings`에만 의존해야 합니다.

---

## 🛡️ 2. 가드레일 필수 구현 원칙 (Guardrail-by-Design)

모든 도메인 모듈은 안전하고 신뢰할 수 있는 실행을 위해 **반드시 1개 이상의 `BaseGuardrail` 구현체**를 제공해야 합니다.

### 필수 점검 항목:
1. **사전 인자 검증 (`validate_tool_args`)**:
   - 도구가 호출되기 전, LLM이 생성한 파라미터가 유효 범위 내에 있는지 검증해야 합니다.
   - 예: `display`가 1~10 범위를 벗어나거나, 허용되지 않은 정렬 옵션(`sort`)이 들어오면 `GuardrailResult(passed=False, error_message=...)`를 반환하여 도구 실행을 사전에 차단해야 합니다.
2. **사후 출력 정제 (`sanitize_output`)**:
   - 외부 API가 반환한 원시 데이터에 포함된 불필요한 HTML 태그(`<b>`, `<p>`), 이스케이프 문자(`&quot;`), 또는 개인정보(이메일, 휴대폰 번호)를 마스킹하거나 제거해야 합니다.
   - 정제되지 않은 원시 데이터는 LLM의 프롬프트 토큰을 낭비하고 보안 취약점을 유발합니다.
3. **사전 질의 검증 (`validate_input`)**:
   - 사용자 질의가 비어 있거나, 도메인에 명백히 부적절한 악의적 입력을 탐지하여 사전에 차단할 수 있습니다.

---

## 🔐 3. 보안 및 API 키 관리 지침 (Security & Secret Management)

1. **하드코딩 절대 금지**:
   - 코드, 테스트 코드, 주석 어디에도 실제 API 키, 시크릿 토큰을 하드코딩해서는 안 됩니다.
   - 모든 시크릿은 `.env` 파일에 기록하고, `src/config.py`의 `Settings` 객체를 통해서만 참조해야 합니다.
2. **Graceful Degradation (우아한 기능 저하)**:
   - 특정 외부 API 키가 설정되지 않은 환경에서도 전체 애플리케이션이나 테스트가 크래시되어서는 안 됩니다.
   - `module.py`의 `is_enabled()` 메서드에서 필요한 키가 없을 경우 `False`를 반환하여 해당 모듈만 안전하게 비활성화되도록 구현해야 합니다.
   ```python
   def is_enabled(self) -> bool:
       return bool(settings.YOUTUBE_API_KEY)
   ```
3. **Git 추적 방지**:
   - `.env` 파일이 실수로 Git에 커밋되지 않도록 `.gitignore`에 등록되어 있는지 수시로 확인해야 합니다.

---

## ⚠️ 4. 예외 처리 및 에러 복원력 (Error Resilience)

1. **에이전트 크래시 방지**:
   - 외부 네트워크 불안정, 타임아웃, API 할당량 초과(Quota Exceeded) 등으로 인한 예외 발생 시 프로세스가 강제 종료되면 안 됩니다.
   - `tools.py` 또는 `client.py`에서 적절한 예외 처리(`try-except`)를 수행하고, LLM이 이해할 수 있는 명확한 에러 문자열(예: `"검색 API 호출 중 오류가 발생했습니다: ..."` )을 반환하여 모델이 대안을 찾을 수 있도록 해야 합니다.
2. **타임아웃(Timeout) 필수 지정**:
   - `requests.get()` 또는 외부 HTTP 통신 시 반드시 `timeout` 파라미터(예: `timeout=5`)를 명시하여 스레드가 무한 대기하는 현상을 방지해야 합니다.
3. **OpenAPI 장애 시 폴백 목(Fallback Mock) 데이터 제공 원칙**:
   - 외부 OpenAPI(Naver, YouTube 등) 호출 실패 시 빈 값이나 단순 예외로 크래시를 유발하지 않고, 사전에 정의된 표준 스키마의 **폴백 목 데이터(Fallback Mock Data)**를 반환하여 에이전트 및 파이프라인의 비즈니스 연속성을 보장해야 합니다.
   - 세부 구현 규격 및 하네스 테스트 검증 가이드는 [`04_testing_harness.md`](./04_testing_harness.md)의 3.3절을 필수로 준수해야 합니다.

---

## 🧪 5. 테스트 무결성 유지 원칙 (Test Integrity)

1. **100% Mocking 적용 (외부 통신 격리)**:
   - 단위 테스트(`tests/modules/`) 및 코어 테스트(`tests/core/`)는 **인터넷 연결이 끊긴 환경에서도 100% 통과**해야 합니다.
   - 실제 외부 API를 직접 호출하는 라이브 테스트는 `tests/api_test.py`에 별도로 분리하고, 기본 단위/통합 테스트에서는 반드시 `unittest.mock.patch`를 통해 Mock 응답을 반환해야 합니다.
2. **테스트 파괴 금지**:
   - 신규 기능 추가 또는 리팩토링 후 기존 130개 이상의 단위 테스트가 실패해서는 안 됩니다.
   - PR 제출 전 `./venv/bin/pytest tests/modules/ tests/core/`를 실행하여 기존 테스트 스위트의 무결성을 반드시 확인해야 합니다. 

---

## 🌿 6. 브랜치 전략 및 Main 병합 거버넌스 (Branch & Merge Governance)

1. **브랜치 흐름 (Git Flow)**:
   - `feat/<feature-name>` (기능 개발) ➔ `dev` (통합 테스트 & 프리릴리스) ➔ `main` (프로덕션 릴리스)
2. **Main 병합 조건**:
   - **경로 제한**: `main` 브랜치는 **오직 `dev` 브랜치로부터의 PR만 수용**합니다. 개별 피처 브랜치에서의 직병합은 원천 차단됩니다.
   - **2인 이상 승인 필수**: PR 병합을 위해서는 **최소 2명 이상의 동료 리뷰어 승인(Approval)**이 필수입니다.
   - **CI 검증 통과**: 전체 단위/통합 테스트 전건(100% Mocking) 통과가 필수 조건입니다.
