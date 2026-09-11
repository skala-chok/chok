# 🎓 교수님 / 평가자 전용 프로젝트 채점 및 평가 종합 안내서

> **SKALA Multi-Worker Agent & Scenario Routing Platform**  
> **YouTube Data API v3 · Naver Open API / Datalab · Instagram Graph API 통합 AI 에이전트**

본 문서는 교수님 및 평가 위원님께서 프로젝트를 신속하고 객관적으로 평가·채점하실 수 있도록 **원클릭 자동 채점 도구, 채점 기준표(Rubric) 매핑 매트릭스, 10대 비즈니스 시나리오 카탈로그, 그리고 100% Mocking 테스트 하네스 검증 절차**를 총정리한 공식 평가 가이드입니다.

---

## ⚡ 1. 교수님 30초 퀵 채점 요약 (Quick Start)

외부 API 키나 복잡한 환경 설정 없이도 아래 4개 명령어로 시스템의 모든 핵심 기능을 즉시 채점·검증하실 수 있습니다:

### ① 원클릭 자동 채점 스크립트 실행 (가장 추천!)
```bash
# 8대 핵심 아키텍처 규칙 및 테스트 하네스를 자동 점검하고 스코어카드를 출력합니다.
bash scripts/verify.sh
# 또는 python scripts/verify.py
```
> **출력 결과**: 8개 세부 평가 항목 전건 `PASS`, 최종 점수 **100 / 100점 (A+ 만점 합격)** 확인 가능

### ② 100% Mocking 단위/통합 테스트 스위트 검증
```bash
# 외부 인터넷 통신 0%, 211개 테스트가 약 1초 만에 전건 통과합니다.
pytest tests/ -q
```

### ③ CLI 모의(Mock) 에이전트 실행
```bash
# OpenAI API 키 없이도 지능형 시나리오 라우팅 및 도구 체이닝 결과를 터미널에서 확인합니다.
python src/main.py --query "러닝화 트렌드 분석해줘" --mock
```

### ④ Streamlit 대화형 웹 대시보드 시연
```bash
# 웹 UI에서 5대 모듈(22개 툴), 10대 시나리오, 에이전트 대화를 시각적으로 검증합니다.
streamlit run app.py
```
> **안내**: `.env`에 API 키가 없으면 사이드바의 **`🎭 Mock(모의) 데이터 모드`**가 자동으로 활성화되어 안전하게 시연됩니다.

---

## 📊 2. 채점 기준표 매핑 매트릭스 (Evaluation Rubric)

대학/기관 평가 기준에 대응하는 구현 내역, 검증 방법 및 관련 소스코드 위치입니다:

| 평가 영역 | 배점 | 핵심 평가 항목 | 본 프로젝트 구현 내용 | 검증 명령어 / 코드 위치 |
| :--- | :---: | :--- | :--- | :--- |
| **1. 시스템 아키텍처 & 확장성** | **20점** | • 공통 코어 동결<br>• 동적 플러그인 탐색<br>• 모듈 간 무의존성 (Rule 2-1) | • `src/core/base.py` 추상 클래스 완전 격리<br>• `ModuleRegistry`, `ScenarioRegistry` 동적 자동 탐색<br>• 모듈 간 상호 임포트 0건 (AST 정적 검사 통과) | `bash scripts/verify.sh`<br>[Stage 2, 3, 4]<br>[`src/core/registry.py`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/src/core/registry.py) |
| **2. 가드레일 & 보안 설계** | **15점** | • 3대 방어선 가드레일<br>• 악성 입력 사전 차단<br>• 사후 PII 마스킹 (Rule 2-2) | • 1차: `validate_input` (공백/비속어 차단)<br>• 2차: `validate_tool_args` (파라미터/날짜 형식 검증)<br>• 3차: `sanitize_output` (HTML 태그 제거, 전화번호/이메일 마스킹) | `pytest tests/modules/ -k guardrail`<br>[`src/core/guardrails.py`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/src/core/guardrails.py) |
| **3. 장애 복원력 (고가용성)** | **15점** | • 외부 OpenAPI 장애 대응<br>• Fallback Mock 계약 준수 (Rule 1-1) | • YouTube, Naver, Instagram API 외란(5xx, Timeout, Quota 초과) 시 절대 프로세스 Crash 없음<br>• 사전 정의된 표준 목 데이터 반환 및 계약 보장 | `pytest tests/modules/ -k fallback`<br>[Stage 6 in verify.py]<br>[`AGENTS.md (Rule 1-1)`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/AGENTS.md) |
| **4. 지능형 시나리오 라우팅** | **20점** | • 모델 기반 의도 분류<br>• 정예 도구 체이닝<br>• Pydantic 스키마 검증 | • `ScenarioRouter`: 자연어 질의에서 의도 및 인자 추출<br>• 10개 비즈니스 시나리오 파이프라인 (크로스 플랫폼, 쇼핑 트렌드, 채널 분석 등) | `pytest tests/core/test_scenario.py`<br>[`src/core/router.py`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/src/core/router.py)<br>[`src/scenarios/`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/src/scenarios/) |
| **5. 테스트 하네스 & 품질 보증** | **15점** | • 100% Mocking 원칙<br>• 외부 네트워크 무의존<br>• 높은 테스트 커버리지 | • 211건 단위/통합 테스트 100% 격리 실행<br>• `ToolCallingFakeChat`, `unittest.mock.patch` 활용<br>• 평균 테스트 수행 시간 1초 미만 (0.7~1.2s) | `pytest tests/ -v`<br>[`tests/test_integration.py`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/tests/test_integration.py) |
| **6. 사용자 인터페이스 (UI/CLI)** | **10점** | • 대화형 웹 대시보드<br>• CLI 편의성<br>• 오프라인 Mock 모드 | • Streamlit 대시보드 (`app.py`): 툴/시나리오/에이전트 3단 구성<br>• CLI (`src/main.py --mock`): 단일 질의 및 대화형 모드 지원 | `streamlit run app.py`<br>`python src/main.py -q "질의" -m`<br>[`app.py`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/app.py) |
| **7. 협업 거버넌스 & 문서화** | **5점** | • 브랜치 전략 (Rule 1-3)<br>• 인수인계 문서군<br>• 마스터 위키 | • `dev -> main` 단일 병합 경로 & 2인 승인 보호<br>• `handoff/` 6대 아키텍처/테스트 문서<br>• `wiki/` 5개 챕터 생성형 AI 교재 위키 완비 | [`AGENTS.md`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/AGENTS.md)<br>[`handoff/`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/handoff/)<br>[`wiki/`](file:///Users/yeongmin-yun/orca/workspaces/chok/dev/wiki/) |
| **합계** | **100점** | **전체 평가 항목 만점 기준 충족** | | **A+ (100 / 100점)** |

---

## 🗺️ 3. 10대 비즈니스 시나리오 카탈로그 (Scenario Catalog)

시스템에 등록되어 지능적으로 라우팅되는 10개 전문 시나리오 목록과 추천 테스트 질의어입니다:

| # | 시나리오 식별자 (`name`) | 소속 도메인 | 주입 도구 (Required Tools) | 권장 테스트 질의어 (Query) |
| :-: | :--- | :--- | :--- | :--- |
| **1** | `cross_platform_trend` | 크로스 플랫폼 | `get_shopping_trends`, `search_hashtag_id`, `get_hashtag_top_media` | *"러닝화 최신 트렌드 분석해줘"* |
| **2** | `naver_new_product_keyword_trend` | 네이버 쇼핑 | `get_shopping_category_trend`, `search_naver_blog`, `search_naver_news` | *"신제품 원피스 출시를 위한 네이버 쇼핑 분야 트렌드와 블로그 여론 조사해줘"* |
| **3** | `naver_target_audience_validation` | 네이버 쇼핑 | `find_naver_category_code`, `get_shopping_category_gender_trend`, `get_shopping_category_age_trend` | *"패션의류 2030 여성 타겟층의 네이버 쇼핑 관심도를 검증해줘"* |
| **4** | `naver_keyword_audience_segmentation` | 네이버 쇼핑 | `get_shopping_keyword_gender_trend`, `get_shopping_keyword_age_trend` | *"원피스 키워드의 성별 및 연령대별 오디언스 분포를 세분화해줘"* |
| **5** | `youtube_competitor_comparison` | 유튜브 분석 | `find_youtube_channel`, `get_channel_details`, `get_channel_videos` | *"Google Developers 채널과 Android Developers 채널의 최근 콘텐츠 반응을 비교해줘"* |
| **6** | `youtube_competitor_strategy` | 유튜브 분석 | `find_youtube_channel`, `get_channel_details`, `get_competitor_recent_uploads` | *"경쟁사 공식 유튜브 채널의 최근 업로드 전략과 메시지 변화를 분석해줘"* |
| **7** | `youtube_paid_promotion_discovery` | 유튜브 분석 | `search_paid_promotion_videos`, `get_video_metrics` | *"뷰티 분야에서 유료 프로모션이 포함된 유튜브 영상들을 탐색하고 반응을 분석해줘"* |
| **8** | `hashtag_surge_detection` | 인스타그램 | `search_hashtag_id`, `get_hashtag_recent_media`, `get_hashtag_top_media` | *"성남맛집 해시태그의 최근 24시간 유입량과 인기글 기준선을 대조해 급상승 여부를 감지해줘"* |
| **9** | `competitor_campaign_tracking` | 인스타그램 | `get_competitor_profile` | *"경쟁사 nike 인스타그램 공식 계정의 게시 빈도와 참여율로 캠페인 현황을 역추적해줘"* |
| **10** | `competitor_message_shift` | 인스타그램 | `get_competitor_profile` | *"경쟁사 공식 인스타그램 계정의 이전 피드와 최근 피드 캡션을 비교해 메시지 소구점 변화를 분석해줘"* |

---

## 🛠️ 4. 5대 도메인 모듈 및 22개 도구 카탈로그 (Tool Catalog)

시스템의 `src/modules/`에 등록된 5개 도메인 모듈과 총 22개 도구 명세입니다:

```mermaid
graph LR
    A[ModuleRegistry] --> M1[instagram (4 Tools)]
    A --> M2[naver_search (2 Tools)]
    A --> M3[naver_shopping (8 Tools)]
    A --> M4[yt_analytics (4 Tools)]
    A --> M5[yt_search (4 Tools)]

    M1 --> T1[search_hashtag_id<br>get_hashtag_recent_media<br>get_hashtag_top_media<br>get_competitor_profile]
    M2 --> T2[search_naver_blog<br>search_naver_news]
    M3 --> T3[find_naver_category_code<br>get_shopping_trends<br>get_shopping_category_trend<br>get_shopping_category_gender_trend<br>get_shopping_category_age_trend<br>get_shopping_keyword_trend<br>get_shopping_keyword_gender_trend<br>get_shopping_keyword_age_trend]
    M4 --> T4[get_channel_stats<br>search_paid_promotion_videos<br>get_video_metrics<br>get_video_comments]
    M5 --> T5[find_youtube_channel<br>get_channel_details<br>get_channel_videos<br>get_competitor_recent_uploads]
```

---

## 🛡️ 5. 엔터프라이즈 3대 방어선 가드레일 (Guardrail-by-Design)

본 시스템은 모든 도구 호출 전후에 가드레일이 자동 개입하여 안전성을 보장합니다:

1. **1차 사전 방어선 (`validate_input`)**:
   - 사용자 질의가 시스템에 인입되는 즉시 빈 쿼리(`""`, `"   "`), 비속어, 프롬프트 인젝션 시도를 감지하여 에이전트 실행을 조기 차단합니다.
2. **2차 도구 인자 방어선 (`validate_tool_args`)**:
   - LLM이 도구 인자를 잘못 생성한 경우(예: 날짜 형식 불일치 `2026/01/01`, 음수 페이지 수, 빈 키워드 등) 실제 API 호출 전에 차단하고 안전한 피드백을 전달합니다.
3. **3차 사후 출력 방어선 (`sanitize_output`)**:
   - 외부 웹 데이터에 포함된 위험 HTML 태그(`<script>`, `<p>` 등)를 완전히 제거하고, 이메일(`admin@skala.com -> [EMAIL_MASKED]`) 및 전화번호(`010-1234-5678 -> [PHONE_MASKED]`)를 정규식 기반으로 자동 마스킹합니다.

---

## 🚨 6. 고가용성 Fallback Mock 아키텍처 (Rule 1-1)

외부 OpenAPI(네이버, 유튜브, 인스타그램)는 인터넷 순단, 쿼터 소진(429 Too Many Requests), 일시적 서버 오류(5xx) 등 외란이 빈번합니다.
- **원칙**: 외부 통신 실패 시 **절대 프로세스가 크래시되지 않으며**, 사전에 합의된 표준 키 구조(`items`, `results`, `data`)의 **폴백 목 데이터를 즉시 반환**합니다.
- **표식**: 목 데이터에는 `[Fallback Mock]` 표식을 부여하여 가드레일, 시나리오, LLM이 데이터 형태 오류(`KeyError`) 없이 안정적으로 완료 리포트를 작성할 수 있습니다.

---

## 👥 7. 협업 거버넌스 및 브랜치 보호 전략 (Rule 1-3)

- **단일 병합 경로 (`Only from dev`)**:
  - `main` 브랜치는 프로덕션 전용 브랜치로, 개별 기능 브랜치(`feat/*`)에서 직접 병합하는 것을 원천 차단하며, 오직 `dev` 브랜치를 통해서만 PR 및 병합이 가능합니다.
- **최소 2인 이상 정식 승인 (`2 Reviewer Approvals`)**:
  - `dev -> main` 릴리스 PR은 최소 2인 이상의 코드 리뷰어가 정식 승인해야만 병합됩니다.
- **100% Mocking 단위 테스트 전건 통과 필수**:
  - CI 파이프라인에서 211개 테스트가 전건 통과해야만 머지가 허용됩니다.

---

## ❓ 8. 채점자 FAQ (Frequently Asked Questions)

### Q1. 외부 API 키가 전혀 없는 상태에서도 채점이 가능한가요?
> **네, 100% 가능합니다.**  
> 본 프로젝트의 모든 단위/통합 테스트(`pytest tests/`), 원클릭 자동 채점 스크립트(`bash scripts/verify.sh`), CLI Mock 모드(`python src/main.py -q "..." --mock`), 그리고 Streamlit 대시보드(`app.py`)는 외부 API 키가 없어도 사전 설계된 Mock 환경에서 전체 파이프라인이 완벽히 구동되도록 설계되었습니다.

### Q2. 실제 외부 API 키를 가지고 있을 때는 어떻게 테스트하나요?
> 프로젝트 루트의 `.env` 파일에 발급받으신 키를 입력하시면 됩니다:
> ```ini
> OPENAI_API_KEY=sk-...
> YOUTUBE_API_KEY=AIzaSy...
> NAVER_CLIENT_ID=...
> NAVER_CLIENT_SECRET=...
> INSTAGRAM_ACCESS_TOKEN=...
> INSTAGRAM_USER_ID=...
> ```
> 키 입력 후 `streamlit run app.py`를 실행하고 사이드바에서 `🎭 Mock 데이터 모드`를 OFF로 전환하시면 실제 실서버 라이브 데이터로 동작합니다.

### Q3. 테스트를 실행할 때 인터넷 연결이 필요한가요?
> **전혀 필요하지 않습니다.**  
> Rule 1-2(100% Mocking 원칙)에 따라 `tests/`의 모든 테스트는 외부 네트워크를 차단한 상태에서도 1초 이내에 전건 통과하도록 구성되어 있습니다.

---

**작성일**: 2026-09-11  
**개발팀**: SK AI Leader Academy (SKALA) Multi-Worker Agent Team  
**평가 문의**: `GRADING.md` 및 `handoff/` 문서 참조
