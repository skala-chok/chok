"""YouTube Analytics 인자 검증 및 Agent 경계의 개인정보 정제."""

import html
import re
from datetime import datetime
from typing import Any, Dict

from src.core.base import BaseGuardrail, GuardrailResult

B_TOOLS = {
    "search_paid_promotion_videos",
    "get_video_metrics",
    "get_video_comments",
}


def parse_timestamp(value: str) -> datetime:
    """시간대가 있는 RFC3339 날짜를 검증한다. 원문을 예외에 포함하지 않는다."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})",
        value,
    ):
        raise ValueError("시간대가 있는 RFC3339 날짜를 입력하세요.")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("시간대가 있는 RFC3339 날짜를 입력하세요.") from None


def _valid_video_id(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not re.search(r"[\s,]", value)


class YouTubeAnalyticsGuardrail(BaseGuardrail):
    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        message = None
        if tool_name == "search_paid_promotion_videos":
            keyword = args.get("keyword")
            if not isinstance(keyword, str) or not keyword.strip():
                message = "keyword는 비어 있을 수 없습니다."
            if args.get("published_after") is not None:
                try:
                    parse_timestamp(args["published_after"])
                except ValueError:
                    message = "시간대가 있는 RFC3339 날짜를 입력하세요."
        elif tool_name == "get_video_metrics":
            ids = args.get("video_ids")
            if not isinstance(ids, list) or not all(_valid_video_id(value) for value in ids):
                message = "video_ids는 비어 있지 않은 단일 영상 ID들의 목록이어야 합니다."
        elif tool_name == "get_video_comments":
            if not _valid_video_id(args.get("video_id")):
                message = "video_id는 비어 있지 않은 단일 영상 ID여야 합니다."
            if args.get("order", "relevance") not in ("relevance", "time"):
                message = "order는 relevance 또는 time이어야 합니다."
            # 기존 호출자의 max_comments(1~50) 계약은 유지한다.
            max_comments = args.get("max_comments")
            if max_comments is not None:
                if type(max_comments) is not int:
                    message = "max_comments는 정수형이어야 합니다."
                elif not 1 <= max_comments <= 50:
                    message = "max_comments는 1 이상 50 이하여야 합니다."
        elif tool_name == "get_channel_stats":
            if not args.get("channel_id", ""):
                message = "channel_id가 누락되었습니다."
        if tool_name in {"search_paid_promotion_videos", "get_video_comments"}:
            if "max_results" in args and type(args["max_results"]) is not int:
                message = "max_results는 정수형이어야 합니다."
            # max_results의 API 상하한은 client가 제한한다.
        return GuardrailResult(passed=message is None, error_message=message)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            if tool_name in B_TOOLS:
                output = re.sub(r"<[^>]*>", "", html.unescape(output))
            output = re.sub(r"[\w\.-]+@[\w\.-]+\.\w+", "[EMAIL_MASKED]", output)
            return re.sub(r"01[016789]-?\d{3,4}-?\d{4}", "[PHONE_MASKED]", output)
        if tool_name not in B_TOOLS:
            return output
        if isinstance(output, list):
            return [self.sanitize_output(tool_name, value) for value in output]
        if isinstance(output, dict):
            # 근거 URL과 식별자는 마스킹으로 손상시키지 않는다.
            preserved = {"url", "thumbnail", "video_id", "channel_id", "comment_id"}
            return {
                key: value if key in preserved else self.sanitize_output(tool_name, value)
                for key, value in output.items()
            }
        return output
