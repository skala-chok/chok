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


def test_main_cli_mock_mode(capsys):
    test_args = ["main.py", "--query", "러닝화 트렌드 분석해줘", "--mock"]
    with patch.object(sys, "argv", test_args):
        with patch.object(src.main.AgentRunner, "run", return_value="[Mock 답변] 트렌드 분석 결과"):
            src.main.main()

    captured = capsys.readouterr().out
    assert "Mock 모드 동작 중" in captured
    assert "[질의]: 러닝화 트렌드 분석해줘" in captured
    assert "[Mock 답변] 트렌드 분석 결과" in captured


def test_main_cli_mock_runner_factory():
    from src.core.registry import ModuleRegistry
    from src.main import _create_mock_runner

    reg = ModuleRegistry()
    runner = _create_mock_runner(reg)
    assert runner is not None
    assert runner.router is not None
    # Check mock router routing branches
    plan1 = runner.router.route("성남맛집 인스타 해시태그")
    assert plan1.scenario_name == "hashtag_surge_detection"

    plan2 = runner.router.route("경쟁사 캠페인 분석")
    assert plan2.scenario_name == "competitor_campaign_tracking"

    plan3 = runner.router.route("소구점 메시지 변화")
    assert plan3.scenario_name == "competitor_message_shift"

    plan4 = runner.router.route("유튜브 채널 분석")
    assert plan4.scenario_name == "youtube_competitor_comparison"

    plan5 = runner.router.route("성별 연령 타겟 검증")
    assert plan5.scenario_name == "naver_target_audience_validation"

    plan6 = runner.router.route("러닝화 트렌드")
    assert plan6.scenario_name == "cross_platform_trend"
