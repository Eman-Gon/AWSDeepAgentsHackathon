"""
CLI entry point for the Commons investigation agent.

Usage:
  python -m agent.cli "Investigate Recology's city contracts"
  python -m agent.cli --verbose "Who are the biggest city contractors?"
  python -m agent.cli --interactive    # interactive REPL mode
"""

import argparse
import sys

from agent.investigator import investigate


def main():
    parser = argparse.ArgumentParser(
        description="Commons Investigation Agent — powered by Gemini Flash"
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Investigation query (e.g. 'Investigate Recology')",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print each tool call as it happens",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive REPL mode — keep asking questions",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=15,
        help="Max LLM ↔ tool rounds per query (default 15)",
    )

    args = parser.parse_args()

    if args.interactive:
        # Interactive REPL mode
        print("=== Commons Investigation Agent ===")
        print("Type your investigation queries. Type 'quit' to exit.\n")
        while True:
            try:
                query = input("🔍 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break

            print("\n⏳ Investigating...\n")
            result = investigate(query, verbose=args.verbose, max_turns=args.max_turns)
            print(result)
            print("\n" + "=" * 60 + "\n")

    elif args.query:
        # Single-query mode
        if args.verbose:
            print(f"⏳ Investigating: {args.query}\n")
        result = investigate(args.query, verbose=args.verbose, max_turns=args.max_turns)
        print(result)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
