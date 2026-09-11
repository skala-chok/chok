# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: HTML 태그 정제(sanitize_output) 및 트렌드 조회 날짜/개수 범위 검증(validate_tool_args)을 작성합니다.
# ➔ 다음 단계: 🟡 [Step 3] tools.py 로 이동하여 쇼핑 도구를 정의하세요.
# ==============================================================================

import re
from typing import Any, Dict

from src.core.base import BaseGuardrail, GuardrailResult
from src.core.guardrails import sanitize_text


# ==============================================================================
# 🎯 [코드 참고사항: 네이버 쇼핑 가드레일 (Guardrail-by-Design)]
# 1. 3단계 방어선 구현 (BaseGuardrail 상속):
#    - validate_input: 빈 쿼리 사전 차단
#    - validate_tool_args: API 호출 전 파라미터 규격(정규식, 경계값, 허용치) 엄격 검증
#    - sanitize_output: API 응답 내 HTML 태그, 악성 문자열, PII 사후 정제
# 2. 엔드포인트별 API 스펙 경계값 방어:
#    - 검색어 트렌드(search-trend): 2016-01-01 이후 데이터만 제공
#    - 쇼핑 인사이트(shopping-insight): 2017-08-01 이후 데이터만 제공
#    - 잘못된 날짜 요청 시 400 Bad Request가 발생하기 전에 가드레일에서 즉각 방어
# ==============================================================================


class NaverShoppingGuardrail(BaseGuardrail):
    SHOPPING_INSIGHT_TOOLS = (
        "get_shopping_category_trend",
        "get_shopping_category_gender_trend",
        "get_shopping_category_age_trend",
        "get_shopping_keyword_trend",
        "get_shopping_keyword_gender_trend",
        "get_shopping_keyword_age_trend",
    )

    def validate_input(self, query: str) -> GuardrailResult:
        """[사전 방어 1단계] 사용자 입력 질의 공백/누락 검증."""
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    # 검색어 트렌드(search-trend) API와 쇼핑 인사이트(shopping-insight) API 계열은
    # 서로 다른 엔드포인트라 조회 가능 시작일 하한이 다르다 (실 API 문서 기준).
    SEARCH_TREND_MIN_DATE = "2016-01-01"
    SHOPPING_INSIGHT_MIN_DATE = "2017-08-01"

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        """[사전 방어 2단계] 도구 호출 파라미터의 정규식 포맷, 날짜 역전, 개수 제한 검증."""
        if tool_name == "get_shopping_trends" or tool_name in self.SHOPPING_INSIGHT_TOOLS:
            # 1. 날짜 포맷 YYYY-MM-DD 정규식 검증
            date_regex = r"^\d{4}-\d{2}-\d{2}$"
            start_d = str(args.get("start_date", ""))
            end_d = str(args.get("end_date", ""))
            if not re.match(date_regex, start_d) or not re.match(date_regex, end_d):
                return GuardrailResult(passed=False, error_message="날짜는 YYYY-MM-DD 형식이어야 합니다.")
            # 2. 엔드포인트별 최소 시작일 경계값 검증
            min_date = self.SEARCH_TREND_MIN_DATE if tool_name == "get_shopping_trends" else self.SHOPPING_INSIGHT_MIN_DATE
            if start_d < min_date:
                return GuardrailResult(passed=False, error_message=f"start_date는 {min_date} 이후여야 합니다 (API 제공 범위).")
            # 3. 시작일 > 종료일 역전 검증
            if start_d > end_d:
                return GuardrailResult(passed=False, error_message="start_date는 end_date보다 이전이거나 같아야 합니다.")
            # 4. 단위 열거형(Enum) 화이트리스트 검증
            time_unit = args.get("time_unit")
            if time_unit is not None and time_unit not in ("date", "week", "month"):
                return GuardrailResult(passed=False, error_message="time_unit은 'date', 'week', 'month'만 가능합니다.")
        if tool_name == "get_shopping_trends":
            raw = str(args.get("keywords", ""))
            count = len([c for c in raw.split(",") if c.strip()])
            if count == 0:
                return GuardrailResult(passed=False, error_message="keywords는 최소 1개 이상이어야 합니다.")
            if count > 5:
                return GuardrailResult(passed=False, error_message="keywords는 최대 5개까지만 가능합니다 (검색어 트렌드 API 제약).")
        if tool_name in ("get_shopping_category_trend", "get_shopping_keyword_trend"):
            pair_field = "categories" if tool_name == "get_shopping_category_trend" else "keywords"
            max_count = 3 if tool_name == "get_shopping_category_trend" else 5
            raw = str(args.get(pair_field, ""))
            count = len([c for c in raw.split(",") if c.strip()])
            if count == 0:
                return GuardrailResult(passed=False, error_message=f"{pair_field}는 최소 1개 이상이어야 합니다.")
            if count > max_count:
                return GuardrailResult(passed=False, error_message=f"{pair_field}는 최대 {max_count}개까지만 가능합니다.")
        # category_code / keyword는 단일 문자열 파라미터라 위 콤마-개수 검증 대상이 아니므로
        # 빈 값이 그대로 실제 API까지 넘어가지 않도록 별도로 검증한다.
        if tool_name in (
            "get_shopping_category_gender_trend",
            "get_shopping_category_age_trend",
            "get_shopping_keyword_trend",
            "get_shopping_keyword_gender_trend",
            "get_shopping_keyword_age_trend",
        ):
            if not str(args.get("category_code", "")).strip():
                return GuardrailResult(passed=False, error_message="category_code가 비어 있습니다.")
        if tool_name in ("get_shopping_keyword_gender_trend", "get_shopping_keyword_age_trend"):
            if not str(args.get("keyword", "")).strip():
                return GuardrailResult(passed=False, error_message="keyword가 비어 있습니다.")
        if tool_name == "find_naver_category_code":
            if not str(args.get("keyword", "")).strip():
                return GuardrailResult(passed=False, error_message="keyword가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        """[사후 방어 3단계] 도구 실행 결과 문자열 내 HTML 태그 및 개인정보 정제."""
        return sanitize_text(output) if isinstance(output, str) else output
