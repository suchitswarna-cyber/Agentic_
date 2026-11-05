"""Web page for chatting with SSC.

Usage:
    ./run_web.sh           # then open http://localhost:8000
"""

import threading

import anthropic
from flask import Flask, jsonify, request, send_from_directory

from attachments import parse
from gemini_agent import errors as genai_errors
from providers import make_agent, provider_name

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # uploads arrive as base64 JSON

MODE = provider_name()

# One agent (and conversation) per browser tab, keyed by an id the page sends.
_agents: dict = {}
_lock = threading.Lock()


def _get_agent(session_id: str):
    with _lock:
        if session_id not in _agents:
            _agents[session_id], _ = make_agent()
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
    try:
        attachments = [parse(a) for a in body.get("attachments") or []]
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not message and not attachments:
        return jsonify(error="Empty message"), 400

    agent = _get_agent(body.get("session", "default"))
    tool_calls = []
    agent.on_tool_call = lambda name, args: tool_calls.append({"name": name, "args": args})

    try:
        answer = agent.chat(message, attachments)
    except anthropic.AuthenticationError:
        return jsonify(error="Your Claude API key was rejected. Run ./add_key.sh again."), 401
    except anthropic.RateLimitError:
        return jsonify(error="Rate limited. Wait a moment and try again."), 429
    except anthropic.APIStatusError as e:
        return jsonify(error=f"API error {e.status_code}: {e.message}"), 502
    except anthropic.APIConnectionError:
        return jsonify(error="Could not reach the Claude API. Check your connection."), 502
    except TimeoutError as e:
        return jsonify(error=str(e)), 504
    except genai_errors.APIError as e:
        if e.code in (400, 401, 403) and "key" in str(e).lower():
            return jsonify(error="Your Google API key was rejected. Run ./add_key.sh again."), 401
        if e.code == 429:
            return jsonify(error="Google's free limit is used up for now. Wait a bit and try again."), 429
        if e.code == 503:
            return jsonify(error="Google's Gemini models are overloaded right now. Try again in a minute."), 503
        return jsonify(error=f"Google API error {e.code}: {e.message}"), 502

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
