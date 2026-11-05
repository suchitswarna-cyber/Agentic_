# SSC — an agentic AI bot

A small, readable agentic AI project built on Claude (`claude-opus-5-5`).
SSC doesn't just answer — it **plans, calls tools, looks at the results, and keeps going** until the task is done.

## How it works

```
 you ──► Agent.chat()
           │
           ▼
   ┌─────────────── agentic loop (SDK tool runner) ───────────────┐
   │  Claude thinks ─► picks a tool ─► tool runs ─► result back ─┐ │
   │       ▲                                                     │ │
   │       └─────────────────────────────────────────────────────┘ │
   │  ...repeats until Claude has a final answer                   │
   └───────────────────────────────────────────────────────────────┘
           │
           ▼
        answer
```

| File | Role |
|---|---|
| `agent.py` | Claude agent: model, system prompt, conversation history, the loop |
| `tools.py` | The tools Claude can use (each is a plain Python function) |
| `attachments.py` | Reads files and pictures you attach in the webpage |
| `main.py`  | Command-line chat interface |
| `web.py` + `static/index.html` | Chat webpage at http://localhost:8000 |

### Built-in tools

| Tool | What it does |
|---|---|
| `calculator` | Exact arithmetic (safe parser, no `eval`) |
| `get_current_time` | Current date/time in any timezone |
| `get_weather` | Live weather for any city (Open-Meteo, free) |
| `search_wikipedia` | Wikipedia summaries for facts and topics |
| `web_search` | Live web search |
| `list_files` / `read_file` / `write_file` | File access, sandboxed to `./workspace` |
| `remember` / `recall` | Long-term memory saved to `memory.json`, kept across runs |

## Setup

SSC runs on Claude, so you need a Claude API key from [console.anthropic.com](https://console.anthropic.com). Usage is billed per request.

```bash
git clone https://github.com/suchitswarna-cyber/Agentic_.git
cd Agentic_
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./add_key.sh        # paste your key when asked; it's saved to .env (never committed)
```

## Run it

### In your browser

```bash
./run_web.sh
```

Then open **http://localhost:8000**.

Click 📎 (or drag a file onto the page, or paste a screenshot) to ask about a file or picture:

- **Text files** (TXT, MD, CSV, JSON, code): Claude reads the whole file.
- **PDFs**: Claude reads the pages directly, including tables and charts.
- **Pictures** (PNG, JPG, GIF, WebP): Claude looks at them directly.
- Up to 10 MB per file.

### In the terminal

```bash
./run.sh
```

Or give it a single task:

```bash
./run.sh "What's 18% tip on $247.60, split 3 ways?"
```

Try prompts that need several steps:

- "My name is Sam and I like Python. Remember that."
- "What's 18% tip on $247.60, split 3 ways?"
- "What time is it in Tokyo and London right now?"
- "Write a study plan for learning agentic AI to plan.md, then read it back to me."

Use `--effort low` for faster, cheaper answers or `--effort xhigh` for harder tasks.
Chat commands: `/help` shows ideas, `/reset` clears the conversation, `/quit` exits.

## Add your own tool

Write a function in `tools.py`, decorate it with `@beta_tool`, give it type hints and a docstring, and add it to `ALL_TOOLS`:

```python
@beta_tool
def roll_dice(sides: int = 6) -> str:
    """Roll a die.

    Args:
        sides: Number of sides on the die.
    """
    import random
    return str(random.randint(1, sides))
```

That's it — the SDK turns the signature and docstring into the tool schema Claude sees.

## Ideas to extend it

- Hook it to Slack/Discord/Telegram instead of the terminal
- Add a tool that queries your database or calls your own API
- Connect MCP servers for ready-made tools (GitHub, Google Drive, …)
- Add a "confirm before writing files" step for safety
