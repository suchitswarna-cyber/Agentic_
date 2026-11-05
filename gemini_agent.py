"""SSC on Google Gemini - used when a Google API key is saved (./add_key.sh).

Same idea as agent.py: the model calls tools, sees the results, and loops
until it has an answer. Gemini's free tier has daily limits.
"""

import os
import warnings

# The Google libraries warn loudly about this Mac's older Python; the bot works fine.
warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from google import genai  # noqa: E402
from google.genai import errors, types  # noqa: E402,F401  (errors is used by web.py and main.py)

from attachments import default_question  # noqa: E402
from tools import LOCAL_TOOLS  # noqa: E402

MODEL = "gemini-flash-latest"  # always the current Flash model, so retirements don't break SSC
MAX_STEPS = 10  # stop runaway tool loops

SYSTEM_PROMPT = """You are SSC, a helpful autonomous assistant.

Work through tasks step by step. Use your tools whenever they help:
- calculator for any arithmetic
- get_current_time for dates and times
- get_weather for current weather in a city
- search_wikipedia for background on people, places, events and topics
- list_files / read_file / write_file to work with files in your workspace
- remember / recall to keep facts about the user across conversations

At the start of a conversation, call recall to see what you already know.
When you learn something lasting about the user, save it with remember.
Keep final answers clear and concise."""

# Describe our tools to Gemini using the same schemas Claude sees.
_DECLARATIONS = [
    types.FunctionDeclaration(name=t.name, description=t.description, parameters_json_schema=t.input_schema)
    for t in LOCAL_TOOLS
]
_TOOLS_BY_NAME = {t.name: t for t in LOCAL_TOOLS}


class GeminiAgent:
    def __init__(self, on_tool_call=None, **_):
        self.client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        self.on_tool_call = on_tool_call
        self.reset()

    def chat(self, user_input: str, attachments=()) -> str:
        parts = []
        for a in attachments:
            if a.kind == "text":
                parts.append(types.Part.from_text(text=f"Attached file '{a.name}':\n```\n{a.text}\n```"))
            else:  # pictures and PDFs: Gemini reads them directly
                parts.append(types.Part.from_bytes(data=a.data, mime_type=a.mime))
        parts.append(types.Part.from_text(text=user_input or default_question(attachments)))

        response = self.session.send_message(parts)
        for _ in range(MAX_STEPS):
            calls = response.function_calls
            if not calls:
                return (response.text or "").strip() or "(no response)"

            results = []
            for call in calls:
                name, args = call.name, dict(call.args or {})
                if self.on_tool_call:
                    self.on_tool_call(name, args)
                tool = _TOOLS_BY_NAME.get(name)
                try:
                    result = tool.call(args) if tool else f"Error: unknown tool '{name}'"
                except Exception as e:
                    result = f"Error: {e}"
                results.append(types.Part.from_function_response(name=name, response={"result": str(result)}))
            response = self.session.send_message(results)

        return "(stopped: too many tool steps)"

    def reset(self):
        self.session = self.client.chats.create(
            model=MODEL,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=_DECLARATIONS)],
                # We run the tools ourselves so the page can show progress and errors.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
