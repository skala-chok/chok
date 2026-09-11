# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: HTML 태그 정제(sanitize_output) 및 트렌드 조회 날짜/개수 범위 검증(validate_tool_args)을 작성합니다.
# ➔ 다음 단계: 🟡 [Step 3] tools.py 로 이동하여 쇼핑 도구를 정의하세요.
# ==============================================================================

import html
import re
from typing import Any, Dict

from src.core.base import BaseGuardrail, GuardrailResult


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
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    # 검색어 트렌드(search-trend) API와 쇼핑 인사이트(shopping-insight) API 계열은
    # 서로 다른 엔드포인트라 조회 가능 시작일 하한이 다르다 (실 API 문서 기준).
    SEARCH_TREND_MIN_DATE = "2016-01-01"
    SHOPPING_INSIGHT_MIN_DATE = "2017-08-01"

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "get_shopping_trends" or tool_name in self.SHOPPING_INSIGHT_TOOLS:
            date_regex = r"^\d{4}-\d{2}-\d{2}$"
            start_d = str(args.get("start_date", ""))
            end_d = str(args.get("end_date", ""))
            if not re.match(date_regex, start_d) or not re.match(date_regex, end_d):
                return GuardrailResult(passed=False, error_message="날짜는 YYYY-MM-DD 형식이어야 합니다.")
            min_date = self.SEARCH_TREND_MIN_DATE if tool_name == "get_shopping_trends" else self.SHOPPING_INSIGHT_MIN_DATE
            if start_d < min_date:
                return GuardrailResult(passed=False, error_message=f"start_date는 {min_date} 이후여야 합니다 (API 제공 범위).")
            if start_d > end_d:
                return GuardrailResult(passed=False, error_message="start_date는 end_date보다 이전이거나 같아야 합니다.")
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
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            clean = re.sub(r"<.*?>", "", output)
            clean = html.unescape(clean)
            # Mask email addresses / Korean phone numbers (handoff/03_guidelines.md 2절 사후 출력 정제 요건)
            clean = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_MASKED]", clean)
            clean = re.sub(r"01[016789]-?\d{3,4}-?\d{4}", "[PHONE_MASKED]", clean)
            return clean
        return output
