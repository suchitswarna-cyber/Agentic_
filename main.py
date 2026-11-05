"""Command-line chat with the agent.

Usage:
    python main.py                 # interactive chat
    python main.py "your task"     # run a single task and exit
"""

import argparse
import json

import anthropic

from gemini_agent import errors as genai_errors
from providers import make_agent

DIM, CYAN, GREEN, RESET = "\033[2m", "\033[36m", "\033[32m", "\033[0m"
CLEAR_LINE = "\r\033[K"

HELP = f"""{CYAN}Things to try:{RESET}
  What's the weather in Hyderabad?
  Tell me about the Eiffel Tower.
  What's 15% of 2,340?
  What time is it in New York?
  My name is Sam - remember that.
  Write a shopping list to list.md
{CYAN}Commands:{RESET} /help  /reset (clear chat)  /quit
"""


def thinking():
    print(f"{DIM}  thinking...{RESET}", end="", flush=True)


def log_tool(name, tool_input):
    args = json.dumps(tool_input)
    if len(args) > 120:
        args = args[:117] + "..."
    print(f"{CLEAR_LINE}{DIM}  -> {name}({args}){RESET}")
    thinking()


def ask(agent, prompt: str):
    thinking()
    try:
        print(f"{CLEAR_LINE}{GREEN}SSC:{RESET} {agent.chat(prompt)}\n")
    except KeyboardInterrupt:
        print(f"{CLEAR_LINE}(stopped)\n")
    except anthropic.AuthenticationError:
        print(f"{CLEAR_LINE}Authentication failed. Run ./add_key.sh again (see README).")
    except anthropic.RateLimitError:
        print(f"{CLEAR_LINE}Rate limited - wait a moment and try again.")
    except anthropic.APIStatusError as e:
        print(f"{CLEAR_LINE}API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        print(f"{CLEAR_LINE}Could not reach the API - check your connection.")
    except genai_errors.APIError as e:
        if e.code == 429:
            print(f"{CLEAR_LINE}Google's free limit is used up for now - wait a bit and try again.")
        else:
            print(f"{CLEAR_LINE}Google API error {e.code}: {e.message} (run ./add_key.sh if your key is wrong)")


def main():
    parser = argparse.ArgumentParser(description="SSC - an agentic AI bot")
    parser.add_argument("task", nargs="?", help="Run one task and exit")
    parser.add_argument("--effort", default="high",
                        choices=["low", "medium", "high", "xhigh", "max"],
                        help="How hard the agent thinks (default: high)")
    args = parser.parse_args()

    agent, mode = make_agent(effort=args.effort, on_tool_call=log_tool)

    if args.task:
        ask(agent, args.task)
        return

    print(f"{CYAN}SSC agent ready ({mode}).{RESET} Type /help for ideas.\n")
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
        if user == "/help":
            print(HELP)
            continue
        if user == "/reset":
            agent.reset()
            print("Conversation cleared (long-term memory kept).\n")
            continue
        ask(agent, user)


if __name__ == "__main__":
    main()
