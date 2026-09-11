# 🤖 AGENTS.md - Agent & Developer Harness Rules

이 파일은 `skala-chok` (LangChain Multi-Worker Agent & Scenario Routing Platform) 프로젝트에서 작업하는 모든 AI 코딩 어시스턴트(Antigravity, Codex 등)와 개발자가 준수해야 하는 **엔지니어링 규칙 및 테스트 하네스 룰**을 정의합니다.

---

## 🎯 1. 핵심 하네스 룰 (Harness Rules)

### 🚨 [Rule 1-1] OpenAPI 장애 대응 폴백 목(Fallback Mock) 데이터 원칙 (CRITICAL)
외부 OpenAPI(Naver Search, Naver Shopping, YouTube Data API 등)와 통신하는 모든 클라이언트 및 도구는 외란(네트워크 장애, 서버 5xx, Quota 초과, Timeout 등) 발생 시 **절대 프로세스를 비정상 종료(Crash)시키지 않고 사전 정의된 표준 폴백 목 데이터를 반환**해야 합니다.

1. **Graceful Fallback**:
   - `requests.get/post` 호출부를 `try-except requests.exceptions.RequestException`으로 감싸고, 실패 시 경고 로그(`logger.warning`)를 출력한 뒤 표준 구조의 폴백 목 데이터를 반환합니다.
2. **Data Contract 준수**:
   - 반환되는 폴백 목 데이터는 정상 OpenAPI 응답과 동일한 딕셔너리 키 및 구조(예: `items`, `total` 등)를 유지하여 가드레일, LLM, 시나리오 분석 파이프라인에서 `KeyError`가 발생하지 않도록 합니다.
   - 목 데이터 항목 제목/설명 등에 `[Fallback Mock]` 표식을 부여하여 시스템/사용자가 오프라인 폴백 상태임을 명확히 인지할 수 있도록 합니다.
3. **하네스 테스트 필수 작성**:
   - OpenAPI 클라이언트/도구 작업 시, `mock_get.side_effect = requests.exceptions.RequestException` 등으로 외부 API 장애를 시뮬레이션하고, 실패 시 폴백 목 데이터가 정상 반환되는지 검증하는 단위 테스트 케이스를 반드시 추가해야 합니다.

### 🧪 [Rule 1-2] 100% Mocking 단위 테스트 원칙
- `tests/modules/` 및 `tests/core/`의 모든 단위/통합 테스트는 외부 인터넷 연결 없이 1~2초 내에 완료되어야 합니다.
- 실제 외부 API 키나 네트워크 호출 없이 `unittest.mock.patch` 및 `ToolCallingFakeChat`을 활용해 100% 격리된 환경에서 검증되어야 합니다.

### 🌿 [Rule 1-3] 브랜치 전략 및 Main 병합 보호 하네스 룰 (Branch Protection & Merge Governance) (CRITICAL)
`main` 브랜치는 실제 프로덕션 릴리스 전용 브랜치이므로 엄격한 병합 거버넌스를 준수해야 합니다:
1. **단일 병합 경로 원칙 (Only from `dev`)**:
   - `main` 브랜치로의 병합(PR 및 Merge)은 **오직 `dev` 브랜치를 통해서만 가능**합니다.
   - 개별 작업 브랜치(`feat/*`, `fix/*` 등)에서 `main`으로 직접 PR을 생성하거나 직접 병합하는 행위를 엄격히 금지합니다.
2. **최소 2인 이상 승인 필수 (2 Reviewer Approvals Required)**:
   - `dev -> main` PR을 병합하기 위해서는 **반드시 최소 2명 이상의 동료 개발자/코드 리뷰어의 정식 승인(`Approve`)**이 있어야만 병합할 수 있습니다. (1인 승인 또는 승인 없는 강제 병합 원천 차단)
3. **전체 테스트 스위트 통과 필수**:
   - `main` 병합 전 100% Mocking 단위/통합 테스트(`pytest tests/modules/ tests/core/ tests/test_integration.py`)가 전건 통과해야 합니다.

---

## 🏗️ 2. 아키텍처 및 코드 작성 규칙 (Architecture & Code Rules)

### 🚫 [Rule 2-1] 모듈 간 무의존성 (Zero Cross-Module Dependency)
- `src/modules/A`가 `src/modules/B`를 직접 임포트하는 행위를 엄격히 금지합니다.
- 모듈은 오직 `src/core/base.py` 추상 클래스(`BaseAgentModule`, `BaseGuardrail` 등)와 `src/config.py`의 `settings`에만 의존해야 합니다.
- 공통 기능이 필요할 경우 `src/core/`로 승격하여 분리합니다.

### 🛡️ [Rule 2-2] 가드레일 필수 구현 (Guardrail-by-Design)
- 모든 모듈은 `BaseGuardrail`을 상속한 가드레일을 제공해야 합니다:
  - **사전 인자 검증 (`validate_tool_args`)**: 잘못된 파라미터 범위를 사전 차단
  - **사후 출력 정제 (`sanitize_output`)**: 불필요한 HTML 태그, 특수문자, 개인정보 마스킹

### 🔐 [Rule 2-3] 보안 및 시크릿 관리 (Secret Management)
- 코드나 테스트에 실제 API 키를 절대 하드코딩하지 않습니다.
- 키 부재 시 모듈이 안전하게 비활성화되도록 `is_enabled()` 메서드를 구현합니다.

---

## 🏃 3. 회귀 검증 명령어 (Verification Commands)

코드 및 테스트 수정 후 반드시 아래 테스트 스위트를 실행하여 회귀(Regression)가 없음을 증명해야 합니다:

```bash
# 전체 모듈 및 코어 단위 테스트 일괄 실행 (인터넷 통신 제로, 100% Mock)
pytest tests/modules/ tests/core/ -q
```

---

## 📚 4. 인수인계 상세 문서 (Handoff References)

세부 아키텍처 및 엔지니어링 표준은 아래 문서를 참조하십시오:
- [🎨 코드 스타일 가이드](handoff/01_code_style.md)
- [🏛️ 시스템 아키텍처 구조](handoff/02_architecture.md)
- [📜 작성 준수 사항 및 가이드라인](handoff/03_guidelines.md)
- [🧪 테스트 및 하네스 엔지니어링 가이드](handoff/04_testing_harness.md)
- [🚀 신규 모듈/시나리오 확장 가이드](handoff/05_extension_guide.md)
- [🛠️ 트러블슈팅 및 운영 가이드](handoff/06_troubleshooting.md)
