"""Command-line chat with the agent.

Usage:
    python main.py                 # interactive chat
    python main.py "your task"     # run a single task and exit
"""

import argparse
import json
import os

import anthropic

from agent import Agent
from local_agent import LocalAgent

DIM, CYAN, GREEN, RESET = "\033[2m", "\033[36m", "\033[32m", "\033[0m"


def log_tool(name, tool_input):
    args = json.dumps(tool_input)
    if len(args) > 120:
        args = args[:117] + "..."
    print(f"{DIM}  -> {name}({args}){RESET}")


def ask(agent, prompt: str):
    try:
        print(f"{GREEN}Atlas:{RESET} {agent.chat(prompt)}\n")
    except ConnectionError:
        print("Can't reach Ollama - open the Ollama app and try again.")
    except anthropic.AuthenticationError:
        print("Authentication failed. Set ANTHROPIC_API_KEY (see README).")
    except anthropic.RateLimitError:
        print("Rate limited - wait a moment and try again.")
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        print("Could not reach the API - check your connection.")


def main():
    parser = argparse.ArgumentParser(description="Atlas - an agentic AI bot")
    parser.add_argument("task", nargs="?", help="Run one task and exit")
    parser.add_argument("--effort", default="high",
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help="How hard the agent thinks (default: high)")
    parser.add_argument("--local", action="store_true",
                        help="Use the free local model even if an API key is set")
    args = parser.parse_args()

    # Use Claude when an API key is available, otherwise the free local model.
    if os.environ.get("ANTHROPIC_API_KEY") and not args.local:
        agent, mode = Agent(effort=args.effort, on_tool_call=log_tool), "Claude"
    else:
        agent, mode = LocalAgent(on_tool_call=log_tool), "free local model"

    if args.task:
        ask(agent, args.task)
        return

    print(f"{CYAN}Atlas agent ready ({mode}).{RESET} Commands: /reset, /quit\n")
    while True:
        try:
            user = input(f"{CYAN}You:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user in ("/quit", "/exit"):
            break
        if user == "/reset":
            agent.reset()
            print("Conversation cleared (long-term memory kept).\n")
            continue
        ask(agent, user)


if __name__ == "__main__":
    main()
