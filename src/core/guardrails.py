import logging
import time
from typing import Any, Dict, List, Optional
from langchain_core.tools import BaseTool, StructuredTool
from .base import BaseGuardrail

logger = logging.getLogger("skala.guardrail")


def wrap_tool_with_guardrails(
    tool: BaseTool, guardrails: List[BaseGuardrail]
) -> BaseTool:
    """Wrap a LangChain BaseTool with pre-execution argument validation and post-execution output sanitization.

    Args:
        tool: The BaseTool instance to wrap.
        guardrails: List of BaseGuardrail instances applied sequentially.

    Returns:
        A guarded BaseTool (StructuredTool) or the original tool if no guardrails provided.
    """
    if not guardrails:
        return tool

    original_func = getattr(tool, "func", None)
    original_coroutine = getattr(tool, "coroutine", None)

    # Check sync and async capability
    if isinstance(tool, StructuredTool):
        has_sync = tool.func is not None
        has_async = tool.coroutine is not None
    else:
        has_sync = original_func is not None or type(tool)._run is not BaseTool._run
        has_async = (
            original_coroutine is not None or type(tool)._arun is not BaseTool._arun
        )

    def guarded_func(**kwargs: Any) -> Any:
        # 1. Pre-execution argument validation
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

        # 2. Execute underlying tool function with timing and logging
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

        # 3. Post-execution sanitization
        sanitized_output = raw_output
        for guardrail in guardrails:
            sanitized_output = guardrail.sanitize_output(tool.name, sanitized_output)

        return sanitized_output

    async def guarded_coroutine(**kwargs: Any) -> Any:
        # 1. Pre-execution argument validation
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

        # 2. Execute underlying tool coroutine with timing and logging
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

        # 3. Post-execution sanitization
        sanitized_output = raw_output
        for guardrail in guardrails:
            sanitized_output = guardrail.sanitize_output(tool.name, sanitized_output)

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
