"""Free, offline version of the agent: runs a local model through Ollama.

Same idea as agent.py - the model calls tools, sees the results, and loops
until it has an answer - but we write the loop ourselves because Ollama has
no tool runner. No API key or credits needed.
"""

import ollama

from tools import LOCAL_TOOLS

MODEL = "qwen2.5:3b"
MAX_STEPS = 8  # stop runaway tool loops

SYSTEM_PROMPT = """You are Atlas, a helpful assistant running locally.

You have tools. Use one only when it is needed:
- calculator: any arithmetic
- get_current_time: the current date or time
- list_files, read_file, write_file: files in your workspace
- remember: ONLY when the user tells you a fact about themselves
- recall: when you need facts the user told you before

For greetings and general questions, just answer directly without tools.
For math, put the whole problem in one calculator expression and report
the result exactly as the tool returns it - do not redo the math yourself.
Keep answers short and clear."""

# Convert our tool definitions into the format Ollama expects.
_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
        },
    }
    for t in LOCAL_TOOLS
]
_TOOLS_BY_NAME = {t.name: t for t in LOCAL_TOOLS}


class LocalAgent:
    def __init__(self, on_tool_call=None, **_):
        self.messages: list = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.on_tool_call = on_tool_call

    def chat(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(MAX_STEPS):
            response = ollama.chat(model=MODEL, messages=self.messages, tools=_TOOL_SPECS)
            message = response.message
            self.messages.append(message)

            if not message.tool_calls:
                return (message.content or "").strip() or "(no response)"

            for call in message.tool_calls:
                name, args = call.function.name, dict(call.function.arguments or {})
                if self.on_tool_call:
                    self.on_tool_call(name, args)
                tool = _TOOLS_BY_NAME.get(name)
                try:
                    result = tool.call(args) if tool else f"Error: unknown tool '{name}'"
                except Exception as e:
                    result = f"Error: {e}"
                self.messages.append({"role": "tool", "tool_name": name, "content": str(result)})

        return "(stopped: too many tool steps)"

    def reset(self):
        self.messages = self.messages[:1]
