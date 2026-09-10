# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: max_comments 검증(validate_tool_args) 및 댓글 내 개인정보/이메일 마스킹(sanitize_output)을 작성합니다.
# ➔ 다음 단계: 🟡 [Step 3] tools.py 로 이동하여 통계/댓글 도구를 정의하세요.
# ==============================================================================

import re
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class YouTubeAnalyticsGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "get_video_comments":
            max_c = args.get("max_comments")
            if max_c is None:
                max_c = 10
            try:
                max_c = int(max_c)
            except (ValueError, TypeError):
                return GuardrailResult(passed=False, error_message="max_comments는 정수형이어야 합니다.")
            if max_c > 50 or max_c < 1:
                return GuardrailResult(passed=False, error_message="max_comments는 1 이상 50 이하여야 합니다.")
        elif tool_name == "get_channel_stats":
            cid = args.get("channel_id", "")
            if not cid:
                return GuardrailResult(passed=False, error_message="channel_id가 누락되었습니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            # Mask Email
            output = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_MASKED]", output)
            # Mask Korean Phone numbers (010-XXXX-XXXX, etc.)
            output = re.sub(r"01[016789]-?\d{3,4}-?\d{4}", "[PHONE_MASKED]", output)
        return output
