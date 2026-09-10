# ==============================================================================
# 🟠 [Step 2 - 주황점] 가드레일 & 데이터 정제 계층
# • 역할: max_results 범위(1~10) 및 video_id 유효성 검증을 작성합니다.
# ➔ 다음 단계: 🟡 [Step 3] tools.py 로 이동하여 유튜브 도구를 정의하세요.
# ==============================================================================

from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class YouTubeSearchGuardrail(BaseGuardrail):
    def validate_input(self, query: str) -> GuardrailResult:
        if not query or not query.strip():
            return GuardrailResult(passed=False, error_message="검색 쿼리가 비어 있습니다.")
        return GuardrailResult(passed=True)

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "search_youtube_videos":
            max_r = args.get("max_results")
            if max_r is None:
                max_r = 5
            try:
                max_r = int(max_r)
            except (ValueError, TypeError):
                return GuardrailResult(passed=False, error_message="max_results는 정수형이어야 합니다.")
            if max_r > 10 or max_r < 1:
                return GuardrailResult(passed=False, error_message="max_results는 최소 1개, 최대 10개까지 가능합니다.")
        elif tool_name == "get_video_transcript":
            vid = args.get("video_id", "")
            if not vid or len(vid) < 3:
                return GuardrailResult(passed=False, error_message="유효하지 않은 YouTube video_id입니다.")
        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        return output
