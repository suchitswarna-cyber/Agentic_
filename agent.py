"""The agent: Claude + tools + a loop that keeps going until the task is done.

The SDK's tool runner drives the agentic loop:
    Claude thinks -> calls tools -> sees results -> calls more tools -> answers.
This class adds multi-turn conversation history and handles the cases the
runner leaves to us (paused server-tool turns, refusals).
"""

import anthropic

from attachments import default_question
from tools import ALL_TOOLS

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are SSC, a helpful autonomous assistant.

Work through tasks step by step. Use your tools whenever they help:
- calculator for any arithmetic
- get_current_time for dates and times
- get_weather for current weather in a city
- search_wikipedia for quick background on a topic
- web_search for current events or facts you are unsure of
- list_files / read_file / write_file to work with files in your workspace
- remember / recall to keep facts about the user across conversations
- set_alarm / set_timer / list_alarms / cancel_alarm for alarms, reminders and timers
- add_task / list_tasks / complete_task / remove_task for the user's to-do list

At the start of a conversation, call recall to see what you already know.
When you learn something lasting about the user, save it with remember.
Alarms, reminders and to-dos live in the user's browser: set them with the
tools, never just promise to remind the user. Each message starts with the
user's local date and time in brackets; use it for "today", "tomorrow" and
"in 2 hours", and don't repeat it back.
Keep final answers clear and concise."""


class Agent:
    def __init__(self, effort: str = "high", on_tool_call=None):
        self.client = anthropic.Anthropic()
        self.effort = effort
        self.messages: list = []
        self.on_tool_call = on_tool_call  # optional callback(name, input) for logging

    def _run_once(self):
        runner = self.client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            messages=self.messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # If a safety classifier declines, retry on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        last = None
        for message in runner:
            last = message
            # The runner keeps its own copy of history; mirror it so the next
            # user turn continues the same conversation.
            self.messages.append({"role": "assistant", "content": message.content})
            if self.on_tool_call:
                for block in message.content:
                    if block.type in ("tool_use", "server_tool_use"):
                        self.on_tool_call(block.name, block.input)
            tool_response = runner.generate_tool_call_response()
            if tool_response is not None:
                self.messages.append(tool_response)
        return last

    def chat(self, user_input: str, attachments=()) -> str:
        user_input = user_input or default_question(attachments)
        content = []
        for a in attachments:
            if a.kind == "image":
                content.append({"type": "image", "source": {"type": "base64", "media_type": a.mime, "data": a.b64}})
            elif a.kind == "pdf":
                content.append({"type": "document", "title": a.name,
                                "source": {"type": "base64", "media_type": "application/pdf", "data": a.b64}})
            else:
                content.append({"type": "text", "text": f"Attached file '{a.name}':\n```\n{a.text}\n```"})
        content.append({"type": "text", "text": user_input})
        self.messages.append({"role": "user", "content": content})

        # A long web search can pause the turn; restart the runner to resume it.
        for _ in range(5):
            last = self._run_once()
            if last is None or last.stop_reason != "pause_turn":
                break

        if last is None:
            return "(no response)"
        if last.stop_reason == "refusal":
            return "Sorry, I can't help with that request."

        text = "".join(b.text for b in last.content if b.type == "text").strip()
        if last.stop_reason == "max_tokens":
            text += "\n\n[response truncated: hit max_tokens]"
        return text or "(done)"

    def reset(self):
        self.messages = []
