"""CLI (main.py) 실행 및 인자 파싱 단위 테스트."""

import sys
from unittest.mock import patch
import pytest

import src.main


def test_main_cli_query_mode(capsys):
    test_args = ["main.py", "--query", "날씨 알려줘"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="날씨는 맑음입니다."):
                src.main.main()

    captured = capsys.readouterr().out
    assert "로드된 활성 모듈" in captured
    assert "[질의]: 날씨 알려줘" in captured
    assert "날씨는 맑음입니다." in captured


def test_main_cli_interactive_mode_quit(capsys):
    test_args = ["main.py", "--interactive"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch("builtins.input", side_effect=["", "quit"]):
                src.main.main()

    captured = capsys.readouterr().out
    assert "대화형 모드를 시작합니다." in captured
    assert "종료합니다." in captured


def test_main_cli_interactive_mode_execution_and_eof(capsys):
    test_args = ["main.py", "-i"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="답변입니다"):
                with patch("builtins.input", side_effect=["안녕", EOFError()]):
                    src.main.main()

    captured = capsys.readouterr().out
    assert "에이전트 >\n답변입니다" in captured
    assert "종료합니다." in captured


def test_main_cli_query_exception_handling(capsys):
    test_args = ["main.py", "--query", "에러유발"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", side_effect=RuntimeError("테스트 실행 에러")):
                with pytest.raises(SystemExit) as exc_info:
                    src.main.main()
                assert exc_info.value.code == 1

    captured = capsys.readouterr().err
    assert "[오류] 질의 처리 중 문제가 발생했습니다" in captured


def test_main_cli_initialization_exception_handling(capsys):
    test_args = ["main.py", "--query", "안녕"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules", side_effect=Exception("모듈 탐색 실패")):
            with pytest.raises(SystemExit) as exc_info:
                src.main.main()
            assert exc_info.value.code == 1

    captured = capsys.readouterr().err
    assert "[오류] 시스템 초기화 중 문제가 발생했습니다" in captured


def test_main_cli_setup_logging_level():
    test_args = ["main.py", "--log-level", "DEBUG", "--query", "테스트"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.ModuleRegistry, "discover_modules"):
            with patch.object(src.main.AgentRunner, "run", return_value="응답"):
                with patch("src.main.setup_logging") as mock_setup:
                    src.main.main()
                    mock_setup.assert_called_once_with("DEBUG")
