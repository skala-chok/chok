# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: 0원 어뷰징 상품 필터링(sanitize_output) 및 날짜 형식 검증(validate_tool_args)을 작성합니다.
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

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "get_shopping_trends" or tool_name in self.SHOPPING_INSIGHT_TOOLS:
            date_regex = r"^\d{4}-\d{2}-\d{2}$"
            start_d = str(args.get("start_date", ""))
            end_d = str(args.get("end_date", ""))
            if not re.match(date_regex, start_d) or not re.match(date_regex, end_d):
                return GuardrailResult(passed=False, error_message="날짜는 YYYY-MM-DD 형식이어야 합니다.")
            if start_d < "2017-08-01":
                return GuardrailResult(passed=False, error_message="start_date는 2017-08-01 이후여야 합니다 (쇼핑 인사이트 API 제공 범위).")
            if start_d > end_d:
                return GuardrailResult(passed=False, error_message="start_date는 end_date보다 이전이거나 같아야 합니다.")
            time_unit = args.get("time_unit")
            if time_unit is not None and time_unit not in ("date", "week", "month"):
                return GuardrailResult(passed=False, error_message="time_unit은 'date', 'week', 'month'만 가능합니다.")
        if tool_name in ("get_shopping_category_trend", "get_shopping_keyword_trend"):
            pair_field = "categories" if tool_name == "get_shopping_category_trend" else "keywords"
            max_count = 3 if tool_name == "get_shopping_category_trend" else 5
            raw = str(args.get(pair_field, ""))
            count = len([c for c in raw.split(",") if c.strip()])
            if count == 0:
                return GuardrailResult(passed=False, error_message=f"{pair_field}는 최소 1개 이상이어야 합니다.")
            if count > max_count:
                return GuardrailResult(passed=False, error_message=f"{pair_field}는 최대 {max_count}개까지만 가능합니다.")
        if tool_name == "search_naver_shopping":
            display_raw = args.get("display")
            if display_raw is None:
                display = 5
            else:
                try:
                    display = int(display_raw)
                except (ValueError, TypeError):
                    return GuardrailResult(passed=False, error_message="display는 1 이상 10 이하여야 합니다.")
            if display > 10 or display < 1:
                return GuardrailResult(passed=False, error_message="display는 1 이상 10 이하여야 합니다.")
            sort = args.get("sort")
            if sort is not None and sort not in ("sim", "date", "asc", "dsc"):
                return GuardrailResult(passed=False, error_message="sort 옵션은 'sim', 'date', 'asc', 'dsc'만 가능합니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            clean = re.sub(r"<.*?>", "", output)
            clean = html.unescape(clean)
            return clean
        return output
