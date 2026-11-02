"""Web page for chatting with SSC.

Usage:
    ./run_web.sh           # then open http://localhost:8000
"""

import os
import sys
import threading

import anthropic
from flask import Flask, jsonify, request, send_from_directory

from agent import Agent
from local_agent import LocalAgent

app = Flask(__name__, static_folder="static")

USE_CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY")) and "--local" not in sys.argv
MODE = "Claude" if USE_CLAUDE else "Free local model"

# One agent (and conversation) per browser tab, keyed by an id the page sends.
_agents: dict = {}
_lock = threading.Lock()


def _get_agent(session_id: str):
    with _lock:
        if session_id not in _agents:
            _agents[session_id] = Agent() if USE_CLAUDE else LocalAgent()
        return _agents[session_id]


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/info")
def info():
    return jsonify(mode=MODE)


@app.post("/api/chat")
def chat():
    body = request.get_json(force=True)
    message = (body.get("message") or "").strip()
    if not message:
        return jsonify(error="Empty message"), 400

    agent = _get_agent(body.get("session", "default"))
    tool_calls = []
    agent.on_tool_call = lambda name, args: tool_calls.append({"name": name, "args": args})

    try:
        answer = agent.chat(message)
    except ConnectionError:
        return jsonify(error="Can't reach Ollama. Open the Ollama app and try again."), 503
    except anthropic.AuthenticationError:
        return jsonify(error="Your Claude API key was rejected. Run ./add_key.sh again."), 401
    except anthropic.RateLimitError:
        return jsonify(error="Rate limited. Wait a moment and try again."), 429
    except anthropic.APIStatusError as e:
        return jsonify(error=f"API error {e.status_code}: {e.message}"), 502
    except anthropic.APIConnectionError:
        return jsonify(error="Could not reach the Claude API. Check your connection."), 502

    return jsonify(answer=answer, tools=tool_calls)


@app.post("/api/reset")
def reset():
    body = request.get_json(force=True)
    with _lock:
        _agents.pop(body.get("session", "default"), None)
    return jsonify(ok=True)


if __name__ == "__main__":
    print(f"SSC web ({MODE}) running at http://localhost:8000")
    app.run(host="127.0.0.1", port=8000, threaded=True)
