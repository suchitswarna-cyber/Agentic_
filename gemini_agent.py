"""SSC on Google Gemini - used when a Google API key is saved (./add_key.sh).

Same idea as agent.py: the model calls tools, sees the results, and loops
until it has an answer. Gemini's free tier has daily limits.
"""

import os
import warnings
from concurrent.futures import ThreadPoolExecutor

# The Google libraries warn loudly about this Mac's older Python; the bot works fine.
warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402,F401  (errors is used by web.py and main.py)

from attachments import default_question  # noqa: E402
from daily import DAILY_TOOLS  # noqa: E402
from tools import LOCAL_TOOLS  # noqa: E402

# Tried in order. When one is overloaded (503), out of free quota (429) or not
# offered to this key (404), SSC moves to the next. The "-latest" names follow
# Google's newest models, so model retirements don't break SSC.
MODELS = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-flash-lite-latest"]
BUSY_CODES = (404, 429, 503)  # 404: that model isn't offered to this key any more
MAX_STEPS = 10  # stop runaway tool loops

SYSTEM_PROMPT = """You are SSC, a helpful autonomous assistant.

Work through tasks step by step. Use your tools whenever they help:
- calculator for any arithmetic
- get_current_time for dates and times
- get_weather for current weather in a city
- search_wikipedia for background on people, places, events and topics
- list_files / read_file / write_file to work with files in your workspace
- remember / recall to keep facts about the user across conversations
- set_alarm / set_timer / list_alarms / cancel_alarm for alarms, reminders and timers
- add_task / list_tasks / complete_task / remove_task for the user's to-do list
- add_note / list_notes / delete_note for quick notes
- convert_currency for money conversions (rupees are INR)
- set_home_city when the user tells you which city they live in
- get_news for headlines in India or the USA, by topic (top, current affairs, technology, business, ...)

The first message may include what you already know about the user in
brackets; use it instead of calling recall.
When you learn something lasting about the user, save it with remember.
Alarms, reminders and to-dos live in the user's browser: set them with the
tools, never just promise to remind the user. Each message starts with the
user's local date and time in brackets; use it for "today", "tomorrow" and
"in 2 hours", and don't repeat it back.
The daily briefing has its own button; if asked for one in chat, tell the user
to tap Briefing at the top.
Keep final answers clear and concise."""

# Describe our tools to Gemini using the same schemas Claude sees.
_DECLARATIONS = [
    types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.input_schema)
    for t in LOCAL_TOOLS
]
_TOOLS_BY_NAME = {t.name: t for t in LOCAL_TOOLS}
# Alarms, to-dos and notes edit this request's state, so they stay on this thread;
# the internet tools (weather, news, Wikipedia, ...) run side by side.
_STATEFUL = {t.name for t in DAILY_TOOLS} | {"remember", "write_file"}


class GeminiAgent:
    def __init__(self, on_tool_call=None, **_):
        self.client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"],
            # Fail within a minute instead of retrying for minutes; we switch models instead.
            # v1beta is where the -latest model names live; fail within a minute
            # instead of retrying for minutes, since we switch models instead.
            http_options=types.HttpOptions(api_version="v1beta", timeout=60_000,
                                           retry_options=types.HttpRetryOptions(attempts=1)),
        )
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=_DECLARATIONS)],
            # We run the tools ourselves so the page can show progress and errors.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.on_tool_call = on_tool_call
        self.reset()

    def chat(self, user_input: str, attachments=()) -> str:
        parts = []
        for a in attachments:
            if a.kind == "text":
                parts.append(types.Part.from_text(text=f"Attached file '{a.name}':\n```\n{a.text}\n```"))
            else:  # pictures, videos and PDFs: Gemini reads them directly
                parts.append(types.Part.from_bytes(data=a.data, mime_type=a.mime))
        parts.append(types.Part.from_text(text=user_input or default_question(attachments)))

        response = self._send(parts)
        for _ in range(MAX_STEPS):
            calls = response.function_calls
            if not calls:
                return _text(response) or "(no response)"

            jobs = [(call.name, dict(call.args or {})) for call in calls]
            for name, args in jobs:
                if self.on_tool_call:
                    self.on_tool_call(name, args)
            outputs = {i: _run_tool(n, a) for i, (n, a) in enumerate(jobs) if n in _STATEFUL}
            rest = [i for i, (n, _) in enumerate(jobs) if n not in _STATEFUL]
            if rest:
                with ThreadPoolExecutor(max_workers=min(8, len(rest))) as pool:
                    for i, result in zip(rest, pool.map(lambda i: _run_tool(*jobs[i]), rest)):
                        outputs[i] = result
            results = [types.Part.from_function_response(name=n, response={"result": outputs[i]})
                       for i, (n, _) in enumerate(jobs)]
            response = self._send(results)

        return "(stopped: too many tool steps)"

    def _send(self, message):
        """Send to the current model, moving down MODELS while Google is busy."""
        while True:
            index = MODELS.index(self.model)
            last = index == len(MODELS) - 1
            try:
                return self.session.send_message(message)
            except errors.APIError as e:
                if e.code not in BUSY_CODES or last:
                    raise
            except Exception as e:
                if not _is_timeout(e):
                    raise
                if last:
                    raise TimeoutError("Google took too long to answer. Try again in a minute.")
            # A failed send isn't added to the history, so the next model
            # picks up the same conversation and the same message.
            self._start(MODELS[index + 1], self.session.get_history(curated=True))

    def _start(self, model, history=None):
        self.model = model
        self.session = self.client.chats.create(model=model, config=self.config, history=history)

    def reset(self):
        self._start(MODELS[0])


def _run_tool(name: str, args: dict) -> str:
    tool = _TOOLS_BY_NAME.get(name)
    try:
        return str(tool.call(args)) if tool else f"Error: unknown tool '{name}'"
    except Exception as e:
        return f"Error: {e}"


def _is_timeout(e) -> bool:
    """True for a network time-out, whichever HTTP library Google's SDK uses."""
    return isinstance(e, TimeoutError) or "timeout" in type(e).__name__.lower()


def _text(response) -> str:
    """The reply's text, skipping thinking parts (avoids a noisy SDK warning)."""
    content = response.candidates[0].content if response.candidates else None
    parts = content.parts if content and content.parts else []
    return "".join(p.text for p in parts if p.text and not p.thought).strip()
