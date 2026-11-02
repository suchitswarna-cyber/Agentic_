# Atlas — an agentic AI bot

A small, readable agentic AI project built on Claude (`claude-opus-5-5`).
Atlas doesn't just answer — it **plans, calls tools, looks at the results, and keeps going** until the task is done.

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
| `local_agent.py` | Free agent using a local model via Ollama |
| `tools.py` | The tools Claude can use (each is a plain Python function) |
| `main.py`  | Command-line chat interface |

### Built-in tools

| Tool | What it does |
|---|---|
| `calculator` | Exact arithmetic (safe parser, no `eval`) |
| `get_current_time` | Current date/time in any timezone |
| `web_search` | Live web search (Claude mode only) |
| `list_files` / `read_file` / `write_file` | File access, sandboxed to `./workspace` |
| `remember` / `recall` | Long-term memory saved to `memory.json`, kept across runs |

## Two ways to run it

| Mode | Brain | Cost | Web search |
|---|---|---|---|
| **Free (default)** | `qwen2.5:3b` running on your Mac via [Ollama](https://ollama.com) | Free, offline | No |
| **Claude** | `claude-opus-5-5` | Pay-per-use API key | Yes |

The bot uses Claude when an API key is saved, otherwise the free local model.

## Setup

```bash
cd agentic-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

For free mode, install [Ollama](https://ollama.com/download) and download the model once:

```bash
ollama pull qwen2.5:3b
```

Optional: to use Claude instead, run `./add_key.sh` and paste a key from console.anthropic.com.

## Run it

```bash
./run.sh
```

Or give it a single task:

```bash
./run.sh "What's 18% tip on $247.60, split 3 ways?"
```

Add `--local` to force the free model even when a key is saved.

Try prompts that need several steps:

- "My name is Sam and I like Python. Remember that."
- "What's 18% tip on $247.60, split 3 ways?"
- "What time is it in Tokyo and London right now?"
- "Write a study plan for learning agentic AI to plan.md, then read it back to me."

Use `--effort low` for faster, cheaper answers or `--effort xhigh` for harder tasks.
Chat commands: `/reset` clears the conversation, `/quit` exits.

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
