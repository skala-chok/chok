# ==============================================================================
# 🟠 [Step 2 - 주황점] Instagram 모듈 가드레일 계층
# • 역할: 도구 인자 사전 검증(공백/특수문자 정제 확인) 및 출력 토큰/개인정보 마스킹
# ==============================================================================

import re
from typing import Any, Dict
from src.core.base import BaseGuardrail, GuardrailResult


class InstagramGuardrail(BaseGuardrail):
    """인스타그램 Graph API 도구 실행 전후의 파라미터 유효성 검증 및 출력 정제."""

    def validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> GuardrailResult:
        if tool_name == "search_hashtag_id":
            raw_query = str(args.get("query", "")).strip()
            if not raw_query:
                return GuardrailResult(
                    passed=False,
                    error_message="검색할 해시태그 키워드가 비어 있습니다.",
                )
            cleaned = raw_query.lstrip("#").replace(" ", "")
            if len(cleaned) == 0:
                return GuardrailResult(
                    passed=False,
                    error_message="해시태그 키워드는 공백과 '#'을 제외한 1글자 이상의 문자열이어야 합니다.",
                )

        elif tool_name in ("get_hashtag_recent_media", "get_hashtag_top_media"):
            hashtag_id = str(args.get("hashtag_id", "")).strip()
            if not hashtag_id:
                return GuardrailResult(
                    passed=False,
                    error_message="해시태그 고유 ID(hashtag_id)가 제공되지 않았습니다.",
                )

        elif tool_name == "get_competitor_profile":
            username = str(args.get("username", "")).strip().lstrip("@")
            if not username:
                return GuardrailResult(
                    passed=False,
                    error_message="경쟁사 계정 핸들(username)이 비어 있습니다.",
                )
            if " " in username:
                return GuardrailResult(
                    passed=False,
                    error_message=f"인스타그램 계정명에는 공백이 포함될 수 없습니다: '{username}'",
                )

        return GuardrailResult(passed=True)

    def sanitize_output(self, tool_name: str, output: Any) -> Any:
        if isinstance(output, str):
            # 액세스 토큰 패턴 마스킹 (EAA... 또는 access_token=...)
            output = re.sub(r"access_token=[a-zA-Z0-9_-]+", "access_token=[PROTECTED_TOKEN]", output)
            output = re.sub(r"EAAG[a-zA-Z0-9]+", "[PROTECTED_TOKEN]", output)
        return output
