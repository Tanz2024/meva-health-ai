"""Send one question to MEVA's local AI agent, non-interactively.

Usage:
    python3 examples/ask_local.py "What allergies are recorded for patient <id>?"

Requires a running local Ollama server (see docs/local-ai.md).
"""

import sys

from meva.ai.agent import run_agent
from meva.ai.ollama_client import model_name


def main():
    if len(sys.argv) < 2:
        print('Usage: python3 examples/ask_local.py "your question"')
        sys.exit(1)

    question = sys.argv[1]

    print("MEVA Local AI")
    print(f"Model: {model_name()}\n")
    print(f"You: {question}\n")

    result = run_agent(question)

    for entry in result["log"]:
        print(f"[tool call] {entry['tool']}({entry['arguments']}) -> {entry['result']}")

    print(f"\nMEVA:\n{result['answer']}")


if __name__ == "__main__":
    main()
