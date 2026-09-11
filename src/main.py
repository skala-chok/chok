import argparse
import logging
import sys
import time
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가하여 직접 스크립트 실행(python src/main.py) 지원
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner

logger = logging.getLogger("skala_agent")


def setup_logging(log_level: str = "INFO") -> None:
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _create_mock_runner(registry: ModuleRegistry) -> AgentRunner:
    """외부 API 키 없이도 CLI 파이프라인 및 시나리오 체이닝을 검증할 수 있는 Mock 러너 생성."""
    from langchain_core.messages import AIMessage
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from src.core.scenario import ScenarioExecutionPlan
    from src.core.scenario_registry import ScenarioRegistry
    from src.config import settings

    # 모의 환경변수 주입 (전체 5개 모듈 활성화)
    settings.OPENAI_API_KEY = settings.OPENAI_API_KEY or "mock-openai-key"
    settings.YOUTUBE_API_KEY = settings.YOUTUBE_API_KEY or "mock-yt-key"
    settings.NAVER_CLIENT_ID = settings.NAVER_CLIENT_ID or "mock-naver-id"
    settings.NAVER_CLIENT_SECRET = settings.NAVER_CLIENT_SECRET or "mock-naver-sec"
    settings.INSTAGRAM_ACCESS_TOKEN = settings.INSTAGRAM_ACCESS_TOKEN or "mock-ig-token"
    settings.INSTAGRAM_USER_ID = settings.INSTAGRAM_USER_ID or "mock-ig-uid"

    registry.discover_modules("src.modules")
    scen_registry = ScenarioRegistry()
    scen_registry.discover_scenarios("src.scenarios")

    class CliMockRouter:
        def __init__(self, scens):
            self.scens = scens

        def route(self, query: str):
            q = query.lower()
            if "해시태그" in q or "인스타" in q:
                return ScenarioExecutionPlan(
                    scenario_name="hashtag_surge_detection",
                    confidence=0.98,
                    parameters={"base_keyword": "성남맛집", "compare_hashtags": ["#성남맛집", "#판교맛집"], "hours_range": 12},
                    reasoning="[Mock] 인스타그램 해시태그 급상승 분석 라우팅",
                )
            if "캠페인" in q:
                return ScenarioExecutionPlan(
                    scenario_name="competitor_campaign_tracking",
                    confidence=0.95,
                    parameters={"target_username": "nike", "post_count": 5},
                    reasoning="[Mock] 인스타그램 캠페인 추적 라우팅",
                )
            if "메시지" in q or "소구점" in q:
                return ScenarioExecutionPlan(
                    scenario_name="competitor_message_shift",
                    confidence=0.95,
                    parameters={"target_username": "nike", "older_sample_size": 3, "newer_sample_size": 3},
                    reasoning="[Mock] 인스타그램 메시지 변화 분석 라우팅",
                )
            if "유튜브" in q or "채널" in q:
                return ScenarioExecutionPlan(
                    scenario_name="youtube_competitor_comparison",
                    confidence=0.95,
                    parameters={"channel_1": "Google Developers", "channel_2": "Android Developers"},
                    reasoning="[Mock] 유튜브 경쟁 채널 비교 라우팅",
                )
            if "성별" in q or "연령" in q or "타겟" in q:
                return ScenarioExecutionPlan(
                    scenario_name="naver_target_audience_validation",
                    confidence=0.95,
                    parameters={"category_name": "패션의류", "target_gender": "f", "target_ages": ["20", "30"]},
                    reasoning="[Mock] 네이버 쇼핑 타겟 오디언스 검증 라우팅",
                )
            clean_kw = query.strip() or "러닝화"
            return ScenarioExecutionPlan(
                scenario_name="cross_platform_trend",
                confidence=0.96,
                parameters={"keyword": clean_kw, "start_date": "2026-01-01", "end_date": "2026-03-01"},
                reasoning="[Mock] 크로스 플랫폼 트렌드 종합 분석 라우팅",
            )

    class CliMockChat(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    mock_chat = CliMockChat(responses=[AIMessage(content="### [Mock 분석 리포트]\n시나리오 도구 체이닝 및 다각도 분석이 성공적으로 완료되었습니다.")])
    return AgentRunner(
        registry=registry,
        scenario_registry=scen_registry,
        router=CliMockRouter(scen_registry),
        llm=mock_chat,
    )


def main():
    parser = argparse.ArgumentParser(description="LangChain Multi-Worker Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="단일 질의 실행")
    parser.add_argument("--interactive", "-i", action="store_true", help="대화형 콘솔 모드")
    parser.add_argument(
        "--mock",
        "-m",
        action="store_true",
        help="외부 API 키 없이 모의(Mock) LLM/라우터 모드로 실행 (교수님 채점 및 테스트용)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로깅 레벨 설정 (기본값: INFO)",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info("CLI 실행 시작 (로그 레벨: %s, Mock 모드: %s)", args.log_level, args.mock)

    try:
        registry = ModuleRegistry()
        if args.mock:
            runner = _create_mock_runner(registry)
        else:
            logger.info("모듈 자동 탐색 시작: src.modules")
            registry.discover_modules("src.modules")
            runner = AgentRunner(registry=registry)

        enabled = registry.get_enabled_modules()
        logger.info("활성 모듈 로드 완료 (%d개): %s", len(enabled), [m.name for m in enabled])

        print("=" * 60)
        mode_str = " [🎭 Mock 모드 동작 중]" if args.mock else ""
        print(f"[LangChain Multi-Worker Agent]{mode_str} 초기화 완료")
        print(f"로드된 활성 모듈 ({len(enabled)}개): {[m.name for m in enabled]}")
        print("=" * 60)

        scenarios = runner.scenario_registry.get_all_scenarios()
        logger.info("활성 시나리오 로드 완료 (%d개): %s", len(scenarios), [s.name for s in scenarios])
        if scenarios:
            print(f"로드된 활성 시나리오 ({len(scenarios)}개): {[s.name for s in scenarios]}")
            print("=" * 60)
        logger.info("AgentRunner 초기화 완료")
    except Exception as e:
        logger.critical("초기화 중 치명적 오류 발생: %s", e, exc_info=True)
        print(f"[오류] 시스템 초기화 중 문제가 발생했습니다: {e}", file=sys.stderr)
        sys.exit(1)

    if args.query:
        print(f"\n[질의]: {args.query}")
        logger.info("단일 질의 처리 시작: %s", args.query)
        start_q = time.time()
        try:
            ans = runner.run(args.query)
            elapsed_q = time.time() - start_q
            logger.info("단일 질의 처리 완료 (총 소요시간: %.2fs)", elapsed_q)
            print(f"\n[답변]:\n{ans}\n")
        except Exception as e:
            logger.error("질의 처리 중 오류 발생: %s", e, exc_info=True)
            print(f"\n[오류] 질의 처리 중 문제가 발생했습니다: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.interactive or len(sys.argv) == 1:
        print("대화형 모드를 시작합니다. (종료하려면 'exit' 또는 'quit' 입력)\n")
        logger.info("대화형 세션 시작")
        while True:
            try:
                user_input = input("\n사용자 > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    print("종료합니다.")
                    logger.info("사용자 요청으로 대화형 세션 종료")
                    break

                logger.debug("사용자 질의 수신: %s", user_input)
                start_turn = time.time()
                try:
                    response = runner.run(user_input)
                    elapsed_turn = time.time() - start_turn
                    logger.info("응답 생성 완료 (총 소요시간: %.2fs)", elapsed_turn)
                    print(f"\n에이전트 >\n{response}")
                except Exception as e:
                    logger.error("에이전트 응답 생성 실패: %s", e, exc_info=True)
                    print(f"\n[오류] 응답 생성 중 문제가 발생했습니다: {e}")
            except (KeyboardInterrupt, EOFError):
                print("\n종료합니다.")
                logger.info("인터럽트 신호로 대화형 세션 종료")
                break
            except Exception as e:
                logger.critical("대화형 루프 중 예기치 않은 예외 발생: %s", e, exc_info=True)
                print(f"\n[치명적 오류] 예기치 않은 오류가 발생했습니다: {e}", file=sys.stderr)
                break


if __name__ == "__main__":
    main()
