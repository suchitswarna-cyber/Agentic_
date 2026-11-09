# SSC — an agentic AI bot

A small, readable agentic AI project that runs on **Google Gemini** (free tier, `gemini-flash-latest`) or **Claude** (`claude-opus-5-5`).
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
| `agent.py` | Claude version: model, system prompt, conversation history, the loop |
| `gemini_agent.py` | Google Gemini version of the same agent |
| `providers.py` | Picks Gemini or Claude depending on which key you saved |
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
| `web_search` | Live web search (Claude only) |
| `list_files` / `read_file` / `write_file` | File access, sandboxed to `./workspace` |
| `remember` / `recall` | Long-term memory saved to `memory.json`, kept across runs |

## Setup

You need an API key from one of these:

| AI | Where to get a key | Cost |
|---|---|---|
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com) → Get API key | Free, with daily limits |
| **Claude** | [console.anthropic.com](https://console.anthropic.com) → API Keys | Paid per request |

If both keys are saved, SSC uses Gemini.

```bash
git clone https://github.com/suchitswarna-cyber/Agentic_.git
cd Agentic_
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./add_key.sh        # paste your Google or Claude key; it's saved to .env (never committed)
```

## Run it online (always on, no computer needed)

SSC can run on [Render](https://render.com)'s free plan straight from this GitHub repo. It updates by itself whenever you push to `main`.

1. Sign up at **render.com** using **Sign in with GitHub**, and allow Render to see this repo.
2. Click **New → Blueprint**, pick the `Agentic_` repo, and click **Apply**. Render reads `render.yaml`.
3. When asked, fill in:
   - `GEMINI_API_KEY`: your Google key (or delete it and add `ANTHROPIC_API_KEY` for Claude)
   - `APP_PASSWORD`: a password you make up. SSC shows a sign-in page that asks for it.
4. Wait for the build to finish, then open the `https://ssc-….onrender.com` address Render shows.

Good to know about the free plan:
- It pauses after about 15 minutes with no visitors, so the first message after a pause takes about a minute.
- Saved memory and files are wiped whenever it restarts or you push an update.

## Run it on your computer

### In your browser

```bash
./run_web.sh
```

Then open **http://localhost:8000**.

Click 📎 and choose **Photos & videos**, **Files** or **Other** (or drag a file onto the page, or paste a screenshot) to ask about it:

- **Text files** (TXT, MD, CSV, JSON, code): the AI reads the whole file.
- **PDFs**: read directly, including tables and charts.
- **Pictures** (PNG, JPG, GIF, WebP): the AI looks at them directly.
- **Videos** (MP4, MOV, WebM): Gemini watches them. Claude can't read videos.
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

With Claude, use `--effort low` for faster, cheaper answers or `--effort xhigh` for harder tasks.
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
