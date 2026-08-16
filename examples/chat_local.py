"""A minimal interactive chat loop against MEVA's local AI agent.

Usage:
    python3 examples/chat_local.py

This is a developer demo only, not a medical chatbot product. Type
'exit' or press Ctrl-C to quit.
"""

from meva.ai.agent import run_agent
from meva.ai.ollama_client import model_name


def main():
    print("MEVA Local AI")
    print(f"Model: {model_name()}\n")
    print("Type 'exit' to quit.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit"):
            break

        result = run_agent(question)

        for entry in result["log"]:
            print(f"  [tool call] {entry['tool']}({entry['arguments']}) -> {entry['result']}")

        print(f"\nMEVA:\n{result['answer']}\n")


if __name__ == "__main__":
    main()
