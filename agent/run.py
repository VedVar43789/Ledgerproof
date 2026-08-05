"""CLI entry point: python3 -m agent.run "your question here"."""

import sys

from .loop import run


def main() -> None:
    if len(sys.argv) < 2:
        print('Usage: python3 -m agent.run "your question here"')
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    answer = run(question)
    print("\n" + "=" * 70)
    print(answer)


if __name__ == "__main__":
    main()
