import html
import re
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class NaverShoppingGuardrail(BaseGuardrail):
    def validate_input(self, query: str) -> GuardrailResult:
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "get_shopping_trends":
            date_regex = r"^\d{4}-\d{2}-\d{2}$"
            start_d = str(args.get("start_date", ""))
            end_d = str(args.get("end_date", ""))
            if not re.match(date_regex, start_d) or not re.match(date_regex, end_d):
                return GuardrailResult(passed=False, error_message="날짜는 YYYY-MM-DD 형식이어야 합니다.")
        elif tool_name == "search_naver_shopping":
            display = args.get("display")
            if display is None:
                display = 5
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
