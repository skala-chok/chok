import html
import re
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class NaverSearchGuardrail(BaseGuardrail):
    def validate_input(self, query: str) -> GuardrailResult:
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name in ("search_naver_blog", "search_naver_news"):
            display = args.get("display")
            if display is None:
                display = 5
            if display > 10 or display < 1:
                return GuardrailResult(passed=False, error_message="display 파라미터는 1 이상 10 이하여야 합니다.")
            sort = args.get("sort")
            if sort is None:
                sort = "sim"
            if sort not in ("sim", "date"):
                return GuardrailResult(passed=False, error_message="sort 옵션은 'sim' 또는 'date'만 가능합니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            # Remove HTML tags (e.g. <b>, </b>)
            clean = re.sub(r"<.*?>", "", output)
            # Decode HTML entities (e.g. &quot;, &amp;, &lt;, &gt;)
            clean = html.unescape(clean)
            return clean
        return output
