# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: max_results 범위(1~10) 및 video_id 유효성 검증을 작성합니다.
# ➔ 다음 단계: 🟡 [Step 3] tools.py 로 이동하여 유튜브 도구를 정의하세요.
# ==============================================================================

from datetime import datetime
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class YouTubeSearchGuardrail(BaseGuardrail):
    def validate_input(self, query: str) -> GuardrailResult:
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name in {
            "get_channel_videos", "get_competitor_recent_uploads",
        }:
            max_r = args.get("max_results")
            if max_r is None:
                max_r = 5
            try:
                max_r = int(max_r)
            except (ValueError, TypeError):
                return GuardrailResult(passed=False, error_message="max_results는 정수형이어야 합니다.")
            max_allowed = 50
            if max_r > max_allowed or max_r < 1:
                return GuardrailResult(passed=False, error_message=f"max_results는 최소 1개, 최대 {max_allowed}개까지 가능합니다.")
        if tool_name in {"get_channel_details", "get_channel_videos", "get_competitor_recent_uploads"}:
            if not args.get("channel_id", "").strip():
                return GuardrailResult(passed=False, error_message="channel_id가 누락되었습니다.")
        if tool_name == "get_channel_videos":
            date_value = args.get("published_after")
            try:
                datetime.fromisoformat(str(date_value).replace("Z", "+00:00"))
            except ValueError:
                return GuardrailResult(passed=False, error_message="날짜는 ISO-8601 형식이어야 합니다.")
        return GuardrailResult(passed=True)
