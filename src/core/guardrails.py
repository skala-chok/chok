"""도구 실행 파이프라인 가드레일 래퍼 및 데이터 정제 엔진 (Guardrails Execution Engine).

[🛡️ 설계 패턴 & 코드 참고사항]
- 데코레이터 / 프록시 패턴 (Decorator / Proxy Pattern):
  도구(BaseTool) 내부의 핵심 비즈니스 로직을 전혀 수정하지 않고, 도구 실행 전후에
  인자 유효성 검사(pre-validation)와 출력물 정제(post-sanitization)를 일관되게 주입합니다.
- 동기 / 비동기 투명성:
  LangChain의 동기 `func` 및 비동기 `coroutine` 인터페이스를 모두 자동 감지하여
  일관된 가드레일 정책 체인을 적용합니다.
"""

import html
import logging
import re
import time
from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool, StructuredTool
from .base import BaseGuardrail

logger = logging.getLogger("skala.guardrail")

_EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
_PHONE_RE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")
_HTML_TAG_RE = re.compile(r"<.*?>")


def sanitize_text(text: str) -> str:
    """공통 사후 출력 정제 (3차 방어선).
    
    1. 정규식 기반 HTML 태그 제거 (<script>, <p> 등 태그 주입 방어)
    2. HTML 엔티티 언이스케이프 (&amp; -> &, &lt; -> < 등 정규화)
    3. 개인정보(PII) 마스킹:
       - 이메일: admin@company.com -> [EMAIL_MASKED]
       - 전화번호: 010-1234-5678 -> [PHONE_MASKED]
    """
    clean = _HTML_TAG_RE.sub("", text)
    clean = html.unescape(clean)
    clean = _EMAIL_RE.sub("[EMAIL_MASKED]", clean)
    return _PHONE_RE.sub("[PHONE_MASKED]", clean)


def wrap_tool_with_guardrails(
    tool: BaseTool, guardrails: List[BaseGuardrail]
) -> BaseTool:
    """LangChain BaseTool에 가드레일(사전 인자 검증 및 사후 출력 정제)을 투명하게 래핑합니다.

    [실행 흐름]
    1. Pre-execution: `guardrail.validate_tool_args(tool.name, kwargs)` 호출
       - 위반 시 도구 실행을 즉시 중단하고 에러 메시지를 반환하여 외부 API 자원 낭비 차단.
    2. Execution: 원본 도구 함수 실행 및 호출 시간(Latency), 입출력 로깅.
    3. Post-execution: `guardrail.sanitize_output(tool.name, raw_output)` 호출
       - 민감정보 마스킹 및 HTML 정제 후 LLM 컨텍스트로 안전하게 전달.

    Args:
        tool: 래핑 대상 LangChain BaseTool 인스턴스.
        guardrails: 순차 적용할 BaseGuardrail 인스턴스 리스트.

    Returns:
        가드레일이 적용된 새로운 StructuredTool 또는 원본 도구.
    """
    if not guardrails:
        return tool

    original_func = getattr(tool, "func", None)
    original_coroutine = getattr(tool, "coroutine", None)

    # 동기 및 비동기 지원 여부 확인
    if isinstance(tool, StructuredTool):
        has_sync = tool.func is not None
        has_async = tool.coroutine is not None
    else:
        has_sync = original_func is not None or type(tool)._run is not BaseTool._run
        has_async = (
            original_coroutine is not None or type(tool)._arun is not BaseTool._arun
        )

    def guarded_func(**kwargs: Any) -> Any:
        # 1. [사전 방어] 도구 인자 유효성 검증
        for guardrail in guardrails:
            val_result = guardrail.validate_tool_args(tool.name, kwargs)
            if not val_result.passed:
                err_msg = val_result.error_message or "유효하지 않은 인자입니다."
                logger.warning(
                    "[가드레일 차단] 도구: '%s' | 가드레일: %s | 사유: %s | 인자: %s",
                    tool.name,
                    type(guardrail).__name__,
                    err_msg,
                    kwargs,
                )
                return f"[가드레일 검증 실패] {err_msg}"

        # 2. 원본 도구 함수 실행 (소요 시간 측정 및 로깅)
        start_time = time.time()
        logger.debug("[도구 호출 시작] 도구: '%s' | 인자: %s", tool.name, kwargs)
        try:
            if original_func is not None:
                raw_output = original_func(**kwargs)
            else:
                raw_output = tool.invoke(kwargs)
            elapsed = time.time() - start_time
            logger.info(
                "[도구 실행 완료] 도구: '%s' | 소요시간: %.2fs",
                tool.name,
                elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "[도구 실행 예외] 도구: '%s' | 소요시간: %.2fs | 에러: %s",
                tool.name,
                elapsed,
                e,
                exc_info=True,
            )
            raise

        # 3. [사후 정제] 출력 데이터 살균 및 개인정보 마스킹
        sanitized_output = raw_output
        for guardrail in guardrails:
            prev_out = sanitized_output
            sanitized_output = guardrail.sanitize_output(tool.name, sanitized_output)
            if sanitized_output != prev_out:
                logger.debug(
                    "[출력 정제 적용] 도구: '%s' | 가드레일: %s (데이터 정제/마스킹됨)",
                    tool.name,
                    type(guardrail).__name__,
                )

        return sanitized_output

    async def guarded_coroutine(**kwargs: Any) -> Any:
        # 1. [사전 방어] 도구 인자 유효성 검증
        for guardrail in guardrails:
            val_result = guardrail.validate_tool_args(tool.name, kwargs)
            if not val_result.passed:
                err_msg = val_result.error_message or "유효하지 않은 인자입니다."
                logger.warning(
                    "[가드레일 차단] 도구: '%s' | 가드레일: %s | 사유: %s | 인자: %s",
                    tool.name,
                    type(guardrail).__name__,
                    err_msg,
                    kwargs,
                )
                return f"[가드레일 검증 실패] {err_msg}"

        # 2. 원본 도구 코루틴 비동기 실행 (소요 시간 측정 및 로깅)
        start_time = time.time()
        logger.debug("[비동기 도구 호출 시작] 도구: '%s' | 인자: %s", tool.name, kwargs)
        try:
            if original_coroutine is not None:
                raw_output = await original_coroutine(**kwargs)
            else:
                raw_output = await tool.ainvoke(kwargs)
            elapsed = time.time() - start_time
            logger.info(
                "[비동기 도구 실행 완료] 도구: '%s' | 소요시간: %.2fs",
                tool.name,
                elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "[비동기 도구 실행 예외] 도구: '%s' | 소요시간: %.2fs | 에러: %s",
                tool.name,
                elapsed,
                e,
                exc_info=True,
            )
            raise

        # 3. [사후 정제] 출력 데이터 살균 및 개인정보 마스킹
        sanitized_output = raw_output
        for guardrail in guardrails:
            prev_out = sanitized_output
            sanitized_output = guardrail.sanitize_output(tool.name, sanitized_output)
            if sanitized_output != prev_out:
                logger.debug(
                    "[출력 정제 적용] 도구: '%s' | 가드레일: %s (데이터 정제/마스킹됨)",
                    tool.name,
                    type(guardrail).__name__,
                )

        return sanitized_output

    args_schema = tool.args_schema or tool.get_input_schema()
    return_direct = getattr(tool, "return_direct", False)
    response_format = getattr(tool, "response_format", "content")

    guarded_tool = StructuredTool.from_function(
        func=guarded_func if has_sync else None,
        coroutine=guarded_coroutine if has_async else None,
        name=tool.name,
        description=tool.description,
        args_schema=args_schema,
        return_direct=return_direct,
        response_format=response_format,
    )
    return guarded_tool
