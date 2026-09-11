"""Streamlit UI (app.py) 헬퍼 및 콜백 단위 테스트."""

from unittest.mock import MagicMock
import streamlit as st
from app import StreamlitToolCallbackHandler, _extract_json_payload, _render_agent_message


def test_streamlit_tool_callback_handler():
    """StreamlitToolCallbackHandler의 tool_results 수집 및 record_tool_result 동작 검증."""
    mock_status = MagicMock()
    log_store = []
    handler = StreamlitToolCallbackHandler(mock_status, log_store)

    # 1. 도구 시작 및 완료 이벤트 수집 (on_tool_start -> on_tool_end)
    handler.on_tool_start({"name": "get_shopping_trends"}, "{'keywords': '러닝화'}")
    assert handler._current_tool_name == "get_shopping_trends"

    handler.on_tool_end("[러닝화]\n  - 2026-01-01: 50.0")
    assert "get_shopping_trends" in handler.tool_results
    assert "50.0" in handler.tool_results["get_shopping_trends"]

    # 2. record_tool_result 직접 기록
    handler.record_tool_result("custom_tool", "custom_result_value")
    assert handler.tool_results["custom_tool"] == "custom_result_value"


def test_extract_json_payload():
    """응답 텍스트에서 ```json ... ``` 블록이 정상 분리되는지 검증."""
    sample_with_json = "```json\n{\n  \"status\": \"success\"\n}\n```\n\n### 📊 리포트 제목\n- 결과 내용입니다."
    json_str, md_body = _extract_json_payload(sample_with_json)
    assert json_str is not None
    assert '"status": "success"' in json_str
    assert md_body == "### 📊 리포트 제목\n- 결과 내용입니다."

    # JSON 블록 없는 일반 마크다운
    sample_text = "일반적인 텍스트 응답입니다."
    json_str2, md_body2 = _extract_json_payload(sample_text)
    assert json_str2 is None
    assert md_body2 == sample_text

    # 접미사 JSON 블록
    sample_suffix_json = "### 마크다운 요약\n\n```json\n{\"id\": 123}\n```"
    json_str3, md_body3 = _extract_json_payload(sample_suffix_json)
    assert json_str3 is not None
    assert '"id": 123' in json_str3
    assert md_body3 == "### 마크다운 요약"


def test_render_agent_message_show_json_toggle(monkeypatch):
    """_render_agent_message가 show_json 토글 값에 따라 JSON expander 노출 여부를 올바르게 제어하는지 검증."""
    expander_calls = []

    class MockExpanderContext:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_expander(label, expanded=False):
        expander_calls.append((label, expanded))
        return MockExpanderContext()

    monkeypatch.setattr(st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "expander", mock_expander)
    monkeypatch.setattr(st, "json", lambda *args, **kwargs: None)
    monkeypatch.setattr(st, "code", lambda *args, **kwargs: None)

    msg_with_json = {
        "role": "assistant",
        "content": "```json\n{\"test\": 1}\n```\n\n### 분석 리포트 본문",
    }

    # 1. show_json=False (기본값): JSON expander를 렌더링하지 않음
    expander_calls.clear()
    _render_agent_message(msg_with_json, show_json=False)
    assert len(expander_calls) == 0

    # 2. show_json=True: JSON expander가 렌더링됨
    expander_calls.clear()
    _render_agent_message(msg_with_json, show_json=True)
    assert len(expander_calls) == 1
    assert "JSON" in expander_calls[0][0]
    assert expander_calls[0][1] is True
