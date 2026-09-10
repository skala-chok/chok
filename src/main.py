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


def main():
    parser = argparse.ArgumentParser(description="LangChain Multi-Worker Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="단일 질의 실행")
    parser.add_argument("--interactive", "-i", action="store_true", help="대화형 콘솔 모드")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="로깅 레벨 설정 (기본값: INFO)",
    )
    args = parser.parse_args()

    setup_logging(args.log_level)
    logger.info("CLI 실행 시작 (로그 레벨: %s)", args.log_level)

    try:
        registry = ModuleRegistry()
        logger.info("모듈 자동 탐색 시작: src.modules")
        registry.discover_modules("src.modules")

        enabled = registry.get_enabled_modules()
        logger.info("활성 모듈 로드 완료 (%d개): %s", len(enabled), [m.name for m in enabled])
        
        print("=" * 60)
        print("[LangChain Multi-Worker Agent] 초기화 완료")
        print(f"로드된 활성 모듈 ({len(enabled)}개): {[m.name for m in enabled]}")
        print("=" * 60)

        runner = AgentRunner(registry=registry)
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
