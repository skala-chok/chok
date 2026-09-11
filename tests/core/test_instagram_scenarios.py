# ==============================================================================
# 🟣 인스타그램 전문 시나리오 단위 테스트 & 통과 기준 검증 (test_instagram_scenarios)
# • 시나리오 1: 급상승 해시태그 실시간 감지 (통과 기준 8대 요건)
# • 시나리오 2: 경쟁사 캠페인 현황 역추적 (통과 기준 8대 요건)
# • 시나리오 3: 경쟁사 메시지 방향 변화 분석 (통과 기준 7대 요건)
# • 시나리오 레지스트리 자동 탐색 및 라우터 연동 검증
# ==============================================================================

import json
import pytest
from unittest.mock import MagicMock
from langchain_core.tools import tool

from src.core.scenario_registry import ScenarioRegistry
from src.scenarios.hashtag_surge_detection.scenario import (
    HashtagSurgeDetectionScenario,
    HashtagSurgeDetectionParams,
    HashtagSurgeDetectionReport,
)
from src.scenarios.competitor_campaign_tracking.scenario import (
    CompetitorCampaignTrackingScenario,
    CompetitorCampaignTrackingParams,
    CampaignTrackingReport,
)
from src.scenarios.competitor_message_shift.scenario import (
    CompetitorMessageShiftScenario,
    CompetitorMessageShiftParams,
    CompetitorMessageShiftReport,
)


# ------------------------------------------------------------------------------
# 🛠️ 테스트용 Mock 도구 Fixtures
# ------------------------------------------------------------------------------
@tool
def mock_search_hashtag_id(query: str) -> str:
    """해시태그 ID 검색 Mock 도구."""
    return f"[정규화 안내] 검색어 '{query}'에서 '#'과 공백을 제거하여 'q={query}'로 인스타그램 해시태그 ID를 조회합니다.\n• 해시태그 ID: ht_{query}"


@tool
def mock_get_hashtag_recent_media(hashtag_id: str) -> str:
    """최근 24시간 유입 게시물 Mock 도구."""
    # ht_판교맛집의 경우 급상승(많은 참여도, 6건)
    if "판교맛집" in hashtag_id:
        return (
            f"### [최신글 (recent_media)] 해시태그 ID: {hashtag_id}\n"
            f"• 수집 건수: 6건 (최근 24시간 윈도우 한정)\n"
            f"• 최근 24시간 평균 참여도 (좋아요+댓글): 150.0\n"
            f"1. [ID: m1] 좋아요: 120개 | 댓글: 30개 | 타입: IMAGE\n"
            f"   - 캡션: \"판교 신규 맛집 오픈! #판교맛집\"\n"
            f"   - 시간: 2026-09-11T08:00:00+0000"
        )
    # ht_분당맛집의 경우 표본 부족(2건)
    elif "분당맛집" in hashtag_id:
        return (
            f"### [최신글 (recent_media)] 해시태그 ID: {hashtag_id}\n"
            f"• 수집 건수: 2건 (최근 24시간 윈도우 한정)\n"
            f"• 최근 24시간 평균 참여도 (좋아요+댓글): 30.0\n"
            f"⚠️ [표본 유의] 24시간 내 게시물 수가 5건 미만으로 적어 통계적 급상승을 단정하기에 표본이 부족합니다."
        )
    # 일반 성남맛집
    return (
        f"### [최신글 (recent_media)] 해시태그 ID: {hashtag_id}\n"
        f"• 수집 건수: 5건 (최근 24시간 윈도우 한정)\n"
        f"• 최근 24시간 평균 참여도 (좋아요+댓글): 40.0"
    )


@tool
def mock_get_hashtag_top_media(hashtag_id: str) -> str:
    """누적 인기글(기준선 baseline) Mock 도구."""
    return (
        f"### [누적 인기글 (top_media - 비교 기준선)] 해시태그 ID: {hashtag_id}\n"
        f"• 수집 건수: 5건\n"
        f"• 누적 인기글 평균 참여도 기준선 (좋아요+댓글): 50.0\n"
        f"1. [ID: top_1] 좋아요: 45개 | 댓글: 5개 | 일시: 2026-08-10T10:00:00+0000\n"
        f"   - 캡션: \"성남 전통 로컬 맛집 리뷰 #성남맛집\""
    )


@tool
def mock_get_competitor_profile(username: str) -> str:
    """경쟁사 공식 프로필 Mock 도구."""
    if "재슐랭" in username:
        return (
            f"### [경쟁사 공식 프로필] @{username} (재슐랭가이드)\n"
            f"• 공식 채널 검증: Bio=\"미식 블로거 재슐랭의 인스타 공식 채널\" | Web=\"https://jaechelin.com\"\n"
            f"• 팔로워: 100,000명 | 팔로우: 50명 | 총 게시물: 500개\n"
            f"• 수집된 최근 게시물: 3건 (API 페이지네이션 범위 내 한정)\n\n"
            f"1. [ID: p1] 좋아요: 2,000개 | 댓글: 100개 | 일시: 2026-09-10T12:00:00+0000\n"
            f"   - 캡션: \"성남 맛집 1탄! 인생 파스타집 발견했습니다. #성남맛집 #파스타 #광고\"\n"
            f"2. [ID: p2] 좋아요: 1,500개 | 댓글: 80개 | 일시: 2026-09-04T10:00:00+0000\n"
            f"   - 캡션: \"분당 판교 직장인 회식 추천 리스트 대공개! #판교맛집 #회식\"\n"
            f"3. [ID: p3] 좋아요: 800개 | 댓글: 30개 | 일시: 2026-08-20T09:00:00+0000\n"
            f"   - 캡션: \"이전 아카이브: 숨은 골목 식당 탐방기 #성남맛집 #로컬맛집\"\n"
            f"• 게시물 타임스탬프 목록 (빈도 계산용): [\"2026-09-10T12:00:00+0000\", \"2026-09-04T10:00:00+0000\", \"2026-08-20T09:00:00+0000\"]\n"
            f"※ 지표 및 권한 고지: 조회수(View Count) 부재: Instagram Graph API는 타 계정 미디어 조회수를 미제공합니다."
        )
    return (
        f"### [경쟁사 공식 프로필] @{username} (미식맨)\n"
        f"• 공식 채널 검증: Bio=\"맛을 탐험하는 미식맨 공식\" | Web=\"https://misikman.kr\"\n"
        f"• 팔로워: 50,000명 | 팔로우: 120명 | 총 게시물: 200개\n"
        f"• 수집된 최근 게시물: 2건\n\n"
        f"1. [ID: m1] 좋아요: 1,000개 | 댓글: 50개 | 일시: 2026-09-09T15:00:00+0000\n"
        f"   - 캡션: \"성남 맛집 로드 투어 #성남맛집\"\n"
        f"2. [ID: m2] 좋아요: 800개 | 댓글: 40개 | 일시: 2026-09-01T10:00:00+0000\n"
        f"   - 캡션: \"분당 카페 추천 #분당카페\"\n"
        f"• 게시물 타임스탬프 목록 (빈도 계산용): [\"2026-09-09T15:00:00+0000\", \"2026-09-01T10:00:00+0000\"]"
    )


# ------------------------------------------------------------------------------
# 🧪 테스트 케이스 정의
# ------------------------------------------------------------------------------
class TestScenario1HashtagSurgeDetection:
    """시나리오 1: 급상승 해시태그 실시간 감지 통과 기준 검증."""

    def test_scenario_execution_and_criteria(self):
        scen = HashtagSurgeDetectionScenario()
        tools = {
            "search_hashtag_id": mock_search_hashtag_id,
            "get_hashtag_recent_media": mock_get_hashtag_recent_media,
            "get_hashtag_top_media": mock_get_hashtag_top_media,
        }
        params = HashtagSurgeDetectionParams(
            base_keyword="성남 맛집",
            compare_hashtags=["#성남 맛집", "#분당 맛집", "#판교 맛집"],
        )

        output = scen.execute(params=params, tools=tools)

        # 1. 정규화 및 명시 검증: #성남 맛집 -> q=성남맛집
        assert "q=성남맛집" in output
        assert "q=분당맛집" in output
        assert "q=판교맛집" in output
        assert "정규화" in output

        # 2. 최신글(recent_media) vs 인기글(top_media) 분리 검증
        assert "최신글 수(24h)" in output
        assert "인기글 기준선 참여도" in output

        # 3. 급상승 판정 수치 대조 검증 (판교맛집: recent 150 vs top 50 -> 3.0배 급상승)
        assert "판교맛집" in output
        assert "급상승" in output

        # 4. 24시간 한계 및 시계열 추이 미제공 명시 검증
        assert "최근 24시간" in output
        assert "시계열 추이" in output

        # 5. 표본 부족 시 단정 방지 검증 (분당맛집: 2건으로 표본 부족)
        assert "표본이 적어" in output or "표본 부족" in output or "표본부족" in output

        # 6. 쿼터 고지 검증 (7일 롤링 30개)
        assert "30개" in output
        assert "쿼터" in output

        # 7. 작성자 정보 미포함 명시 검증
        assert "작성자" in output

        # 8. Pydantic 구조화 스키마 검증 (JSON 블록 포함)
        assert "```json" in output
        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = HashtagSurgeDetectionReport(**data)
        assert report.base_keyword == "성남 맛집"
        assert len(report.metrics) == 3
        assert report.time_window_hours == 24

    def test_scenario1_custom_hours_range(self):
        """사용자가 6시간 등 특정 시간 범위를 지정했을 때 정상 반영되는지 검증."""
        scen = HashtagSurgeDetectionScenario()
        tools = {
            "search_hashtag_id": mock_search_hashtag_id,
            "get_hashtag_recent_media": mock_get_hashtag_recent_media,
            "get_hashtag_top_media": mock_get_hashtag_top_media,
        }
        params = HashtagSurgeDetectionParams(
            base_keyword="성남 맛집",
            compare_hashtags=["#판교 맛집"],
            hours_range=6,
        )

        output = scen.execute(params=params, tools=tools)
        assert "최신글 수(6h)" in output
        assert "최근 6시간" in output

        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = HashtagSurgeDetectionReport(**data)
        assert report.time_window_hours == 6
        assert report.metrics[0].time_window_hours == 6

    def test_scenario1_hours_range_over_24_capped(self):
        """사용자가 24시간을 초과하여 지정했을 때 24시간으로 캡 적용 및 고지되는지 검증."""
        scen = HashtagSurgeDetectionScenario()
        tools = {
            "search_hashtag_id": mock_search_hashtag_id,
            "get_hashtag_recent_media": mock_get_hashtag_recent_media,
            "get_hashtag_top_media": mock_get_hashtag_top_media,
        }
        params = HashtagSurgeDetectionParams(
            base_keyword="성남 맛집",
            compare_hashtags=["#판교 맛집"],
            hours_range=48,
        )

        output = scen.execute(params=params, tools=tools)
        assert "최신글 수(24h)" in output
        assert "API 최대 한도인 24시간" in output

        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = HashtagSurgeDetectionReport(**data)
        assert report.time_window_hours == 24
        assert report.hours_notice is not None


class TestScenario2CompetitorCampaignTracking:
    """시나리오 2: 경쟁사 캠페인 현황 역추적 통과 기준 검증."""

    def test_scenario_execution_and_criteria(self):
        scen = CompetitorCampaignTrackingScenario()
        tools = {"get_competitor_profile": mock_get_competitor_profile}
        params = CompetitorCampaignTrackingParams(
            competitor_usernames=["재슐랭가이드", "미식맨"],
            target_topic="성남 맛집",
        )

        output = scen.execute(params=params, tools=tools)

        # 1. 조회수 미제공 명시 및 참여율 대체 검증
        assert "조회수" in output
        assert "참여율" in output
        assert "business_discovery" in output

        # 2. 계정 username 추측 금지 명시 검증
        assert "추측" in output

        # 3. 타임스탬프 기반 실제 게시 빈도 계산 검증 (어림짐작 아님)
        assert "주당" in output
        assert "실제" in output or "실제계산" in output

        # 4. 팔로워 규모 보정 참여율 계산 검증
        assert "팔로워 보정 참여율" in output

        # 5. 광고비/유료광고 확인 불가 및 timestamp 프록시 명시 검증
        assert "광고비" in output
        assert "프록시" in output

        # 6. biography / website 공식 계정 검증
        assert "biography" in output or "Bio" in output
        assert "website" in output or "Web" in output
        assert "공식" in output

        # 7. 최근 N건 한정 명시 검증
        assert "최근 N건" in output or "최근" in output

        # 8. Pydantic 구조화 스키마 검증
        assert "```json" in output
        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = CampaignTrackingReport(**data)
        assert len(report.competitors) == 2

    def test_scenario2_non_dining_brand_keywords_exclusion(self):
        """올리브영 등 비외식 브랜드 분석 시 하드코딩된 맛집 키워드가 배제되고 동적 해시태그가 추출되는지 검증."""
        @tool
        def mock_oliveyoung_profile(username: str) -> str:
            """올리브영 프로필 Mock 도구."""
            return (
                f"### [경쟁사 공식 프로필] @{username} (올리브영)\n"
                f"• 공식 채널 검증: Bio=\"건강하고 아름다운 일상을 위한 올리브영 공식 인스타그램\" | Web=\"https://oliveyoung.co.kr\"\n"
                f"• 팔로워: 1,500,000명 | 팔로우: 10명 | 총 게시물: 2,500개\n"
                f"• 수집된 최근 게시물: 2건\n\n"
                f"1. [ID: oy1] 좋아요: 5,000개 | 댓글: 350개 | 일시: 2026-09-10T12:00:00+0000\n"
                f"   - 캡션: \"9월 올영세일 시작! 최대 70% 할인 특가 #올영세일 #올리브영 #뷰티 #할인 #광고\"\n"
                f"2. [ID: oy2] 좋아요: 3,200개 | 댓글: 120개 | 일시: 2026-09-05T10:00:00+0000\n"
                f"   - 캡션: \"가을 환절기 보습 케어 루틴 추천 #스킨케어 #보습 #올리브영추천\"\n"
                f"• 게시물 타임스탬프 목록 (빈도 계산용): [\"2026-09-10T12:00:00+0000\", \"2026-09-05T10:00:00+0000\"]\n"
                f"※ 지표 고지: 조회수(View Count) 부재."
            )

        scen = CompetitorCampaignTrackingScenario()
        tools = {"get_competitor_profile": mock_oliveyoung_profile}
        params = CompetitorCampaignTrackingParams(
            competitor_usernames=["oliveyoung_official"],
            target_topic="올영세일",
        )

        output = scen.execute(params=params, tools=tools)
        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = CampaignTrackingReport(**data)

        comp = report.competitors[0]
        # 맛집/외식 키워드가 일절 포함되지 않아야 함
        for forbidden in ["성남", "분당", "판교", "맛집", "회식", "파스타", "카페"]:
            assert forbidden not in comp.campaign_keywords_found

        # 동적으로 추출된 뷰티/세일 해시태그 및 타깃 토픽 포함 검증
        assert "올영세일" in comp.campaign_keywords_found
        assert "올리브영" in comp.campaign_keywords_found
        assert "뷰티" in comp.campaign_keywords_found
        # 광고 컴플라이언스 태그는 제외되어야 함
        assert "광고" not in comp.campaign_keywords_found



class TestScenario3CompetitorMessageShift:
    """시나리오 3: 경쟁사 메시지 방향 변화 분석 통과 기준 검증."""

    def test_scenario_execution_and_criteria(self):
        scen = CompetitorMessageShiftScenario()
        tools = {
            "get_competitor_profile": mock_get_competitor_profile,
            "get_hashtag_top_media": mock_get_hashtag_top_media,
        }
        params = CompetitorMessageShiftParams(
            competitor_username="재슐랭가이드",
            category_keyword="성남 맛집",
        )

        output = scen.execute(params=params, tools=tools)

        # 1. 캡션 원문 인용 검증 (실제 존재하는 문구 인용)
        assert "인생 파스타집 발견했습니다" in output
        assert "숨은 골목 식당 탐방기" in output

        # 2. 타임스탬프 기준 이전(Older) vs 이후(Newer) 대조 검증
        assert "이전 게시물" in output
        assert "이후 게시물" in output

        # 3. 4대 축 클러스터링 검증 (소구점, 후킹, CTA, 해시태그)
        assert "소구점" in output
        assert "후킹" in output
        assert "CTA" in output or "행동 유도" in output
        assert "해시태그" in output

        # 4. 참여도 상/하위 수치 대조 검증 (실제 좋아요/댓글 수치 포함)
        assert "2,000" in output or "2000" in output
        assert "800" in output

        # 5. 시각 요소 분석 미생성 고지 검증
        assert "media_type" in output
        assert "시각" in output

        # 6. 협찬/광고 표기 실제 캡션 기반 식별 검증
        assert "#광고" in output

        # 7. Pydantic 구조화 스키마 검증
        assert "```json" in output
        json_str = output.split("```json")[1].split("```")[0].strip()
        data = json.loads(json_str)
        report = CompetitorMessageShiftReport(**data)
        assert report.is_evaluable is True
        assert report.period_comparison is not None

    def test_scenario3_insufficient_sample_reports_undetermined(self):
        """표본 3건 미만 시 변화 없음이 아닌 '판단 불가'로 보고하는지 검증."""
        @tool
        def mock_single_post_profile(username: str) -> str:
            """단일 게시물 반환 Mock 도구."""
            return (
                f"### [경쟁사 공식 프로필] @{username}\n"
                f"• 수집된 최근 게시물: 1건\n"
                f"1. [ID: p1] 좋아요: 100개 | 댓글: 5개 | 일시: 2026-09-10T12:00:00+0000\n"
                f"   - 캡션: \"단일 게시물 #성남맛집\""
            )

        scen = CompetitorMessageShiftScenario()
        tools = {
            "get_competitor_profile": mock_single_post_profile,
            "get_hashtag_top_media": mock_get_hashtag_top_media,
        }
        params = CompetitorMessageShiftParams(competitor_username="미니멀계정")
        output = scen.execute(params=params, tools=tools)

        # 통과 기준: 표본 부족 시 변화 없음이 아니라 '판단 불가'로 보고
        assert "판단 불가" in output


class TestScenarioRegistryDiscovery:
    """ScenarioRegistry가 신규 인스타그램 시나리오 3종을 자동 발견하는지 검증."""

    def test_discover_all_three_instagram_scenarios(self):
        registry = ScenarioRegistry()
        registry.discover_scenarios("src.scenarios")

        all_names = [s.name for s in registry.get_all_scenarios()]
        assert "cross_platform_trend" in all_names
        assert "hashtag_surge_detection" in all_names
        assert "competitor_campaign_tracking" in all_names
        assert "competitor_message_shift" in all_names


class TestScenarioParameterCoercion:
    """시나리오 파라미터 스키마의 문자열/리스트 유연한 파싱 및 PydanticUndefined 방어 검증."""

    def test_hashtag_surge_detection_params_coercion(self):
        # 1. PydanticUndefined 문자열 전달 시 기본값 리스트로 안전 복구
        p1 = HashtagSurgeDetectionParams(compare_hashtags="PydanticUndefined")
        assert p1.compare_hashtags == ["#성남 맛집", "#분당 맛집", "#판교 맛집"]

        # 2. 쉼표 구분 문자열 전달 시 리스트로 자동 변환
        p2 = HashtagSurgeDetectionParams(compare_hashtags="#강남 맛집, #서초 맛집, #송파 맛집")
        assert p2.compare_hashtags == ["#강남 맛집", "#서초 맛집", "#송파 맛집"]

        # 3. JSON 문자열 전달 시 정상 파싱
        p3 = HashtagSurgeDetectionParams(compare_hashtags='["#판교맛집", "#분당맛집"]')
        assert p3.compare_hashtags == ["#판교맛집", "#분당맛집"]

        # 4. 일반 리스트 전달 시 정상 유지
        p4 = HashtagSurgeDetectionParams(compare_hashtags=["#A", "#B"])
        assert p4.compare_hashtags == ["#A", "#B"]

        # 5. None 또는 빈 문자열 전달 시 기본값 유지
        p5 = HashtagSurgeDetectionParams(compare_hashtags="")
        assert p5.compare_hashtags == ["#성남 맛집", "#분당 맛집", "#판교 맛집"]

        # 6. hours_range 파싱 및 기본값 24시간 검증
        # 6-1. 사용자 미언급 시 기본값 24
        p6 = HashtagSurgeDetectionParams()
        assert p6.hours_range == 24

        # 6-2. 문자열 형태(예: '6시간', '12') 전달 시 숫자로 자동 변환
        p7 = HashtagSurgeDetectionParams(hours_range="6시간")
        assert p7.hours_range == 6

        p8 = HashtagSurgeDetectionParams(hours_range="12")
        assert p8.hours_range == 12

        # 6-3. None / 빈 문자열 / PydanticUndefined 시 기본값 24
        p9 = HashtagSurgeDetectionParams(hours_range="PydanticUndefined")
        assert p9.hours_range == 24

        p10 = HashtagSurgeDetectionParams(hours_range=None)
        assert p10.hours_range == 24

        # 6-4. 음수나 0 입력 시 기본값 24로 방어
        p11 = HashtagSurgeDetectionParams(hours_range=-3)
        assert p11.hours_range == 24

    def test_competitor_campaign_tracking_params_coercion(self):
        # 1. PydanticUndefined 문자열 전달 시 기본값 리스트로 안전 복구
        p1 = CompetitorCampaignTrackingParams(competitor_usernames="PydanticUndefined")
        assert p1.competitor_usernames == ["재슐랭가이드", "미식맨"]

        # 2. 쉼표 구분 문자열 전달 시 리스트로 자동 변환
        p2 = CompetitorCampaignTrackingParams(competitor_usernames="맛집탐정, 푸드파이터")
        assert p2.competitor_usernames == ["맛집탐정", "푸드파이터"]

        # 3. JSON 문자열 전달 시 정상 파싱
        p3 = CompetitorCampaignTrackingParams(competitor_usernames='["user1", "user2"]')
        assert p3.competitor_usernames == ["user1", "user2"]

        # 4. 일반 리스트 전달 시 정상 유지
        p4 = CompetitorCampaignTrackingParams(competitor_usernames=["user_a", "user_b"])
        assert p4.competitor_usernames == ["user_a", "user_b"]

        # 5. 빈 문자열 전달 시 기본값 유지
        p5 = CompetitorCampaignTrackingParams(competitor_usernames="")
        assert p5.competitor_usernames == ["재슐랭가이드", "미식맨"]

