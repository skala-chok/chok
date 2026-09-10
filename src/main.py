import argparse
import sys
from src.core.registry import ModuleRegistry
from src.core.agent import AgentRunner


def main():
    parser = argparse.ArgumentParser(description="LangChain Multi-Worker Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="단일 질의 실행")
    parser.add_argument("--interactive", "-i", action="store_true", help="대화형 콘솔 모드")
    args = parser.parse_args()

    registry = ModuleRegistry()
    registry.discover_modules("src.modules")

    enabled = registry.get_enabled_modules()
    print("=" * 60)
    print("🚀 [LangChain Multi-Worker Agent] 초기화 완료")
    print(f"📦 로드된 활성 모듈 ({len(enabled)}개): {[m.name for m in enabled]}")
    print("=" * 60)

    runner = AgentRunner(registry=registry)

    if args.query:
        print(f"\n[질의]: {args.query}")
        ans = runner.run(args.query)
        print(f"\n[답변]:\n{ans}\n")
    elif args.interactive or len(sys.argv) == 1:
        print("대화형 모드를 시작합니다. (종료하려면 'exit' 또는 'quit' 입력)\n")
        while True:
            try:
                user_input = input("\n👤 사용자 > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit"):
                    print("종료합니다.")
                    break
                response = runner.run(user_input)
                print(f"\n🤖 에이전트 >\n{response}")
            except (KeyboardInterrupt, EOFError):
                print("\n종료합니다.")
                break


if __name__ == "__main__":
    main()
