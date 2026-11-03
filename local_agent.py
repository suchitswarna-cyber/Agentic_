"""Free, offline version of the agent: runs a local model through Ollama.

Same idea as agent.py - the model calls tools, sees the results, and loops
until it has an answer - but we write the loop ourselves because Ollama has
no tool runner. No API key or credits needed.
"""

import ollama

from attachments import default_question
from tools import LOCAL_TOOLS

MODEL = "qwen2.5:3b"
VISION_MODEL = "moondream"  # the main model can't see pictures, so this one looks at them
MAX_STEPS = 8  # stop runaway tool loops

SYSTEM_PROMPT = """Your name is SSC. You are a helpful assistant running locally.
When someone asks who you are, introduce yourself as SSC.

You have tools. Use one only when it is needed:
- calculator: any arithmetic
- get_current_time: the current date or time
- get_weather: current weather in a city
- search_wikipedia: facts about people, places, events, and topics
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

    def chat(self, user_input: str, attachments=()) -> str:
        user_input = user_input or default_question(attachments)
        text = user_input
        for a in attachments:
            if a.kind != "image":
                text += f"\n\nAttached file '{a.name}':\n```\n{a.as_text()}\n```"

        images = [a for a in attachments if a.kind == "image"]
        if images:
            return self._look(user_input, text, images)

        self.messages.append({"role": "user", "content": text})

        for _ in range(MAX_STEPS):
            response = ollama.chat(
                model=MODEL, messages=self.messages, tools=_TOOL_SPECS, options={"num_ctx": 8192}
            )
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

    def _look(self, question: str, text: str, images) -> str:
        """Answer a question about pictures with the vision model."""
        answers = []
        for img in images:
            answer = self._see(img, question)
            if not answer:
                # moondream sometimes goes blank on short questions but can always
                # describe the picture, so let the main model answer from that.
                description = self._see(img, "Describe this picture in detail.")
                response = ollama.chat(model=MODEL, messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"A picture shows: {description}\n\n"
                                                f"Using that description, answer: {question}"},
                ])
                answer = (response.message.content or "").strip()
            answers.append(answer)

        if len(images) == 1:
            answer = answers[0]
        else:
            answer = "\n\n".join(f"**{img.name}:** {a}" for img, a in zip(images, answers))
        answer = answer or "(I couldn't make out that picture.)"

        # Keep it in the main conversation so follow-up questions have context.
        names = ", ".join(img.name for img in images)
        self.messages.append({"role": "user", "content": f"{text}\n\n[Attached picture: {names}]"})
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    @staticmethod
    def _see(img, prompt: str) -> str:
        response = ollama.chat(
            model=VISION_MODEL, messages=[{"role": "user", "content": prompt, "images": [img.data]}]
        )
        return (response.message.content or "").strip()

    def reset(self):
        self.messages = self.messages[:1]
