"""Web page for chatting with SSC.

Usage:
    ./run_web.sh           # then open http://localhost:8000

Online (Render), set APP_PASSWORD so only you can use it: the page then shows
a sign-in screen, and a cookie keeps you signed in for 30 days.
"""

import hashlib
import hmac
import json
import os
import threading
import time
from datetime import timedelta

import anthropic
from flask import Flask, Response, jsonify, redirect, request, send_from_directory, session, stream_with_context

import briefing
import daily
import tools
from attachments import parse
from gemini_agent import errors as genai_errors
from providers import make_agent, provider_name

app = Flask(__name__, static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # uploads arrive as base64 JSON

MODE = provider_name()
PASSWORD = os.environ.get("APP_PASSWORD", "")

# Sign-in cookies are signed with a key made from the password, so they survive
# restarts, and changing the password signs everyone out.
app.secret_key = hashlib.sha256(f"ssc-session:{PASSWORD}".encode()).hexdigest()
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),  # Render serves https
)
OPEN_PATHS = {"/login", "/api/login", "/favicon.ico"}


def _signed_in() -> bool:
    return not PASSWORD or session.get("signed_in") is True


@app.before_request
def require_sign_in():
    if not PASSWORD and os.environ.get("RENDER"):  # never run open to the whole internet
        return Response("Set APP_PASSWORD in Render's Environment settings first.", 503)
    if _signed_in() or request.path in OPEN_PATHS or request.path.startswith("/static/doodle-"):
        return None
    if request.path.startswith("/api/"):
        return jsonify(error="Please sign in again.", signed_out=True), 401
    return redirect("/login")


@app.get("/login")
def login_page():
    if PASSWORD and _signed_in():
        return redirect("/")
    return send_from_directory("static", "login.html")


@app.post("/api/login")
def login():
    password = (request.get_json(silent=True) or {}).get("password") or ""
    if PASSWORD and hmac.compare_digest(password.encode(), PASSWORD.encode()):
        session.clear()
        session.permanent = True
        session["signed_in"] = True
        return jsonify(ok=True)
    time.sleep(1)  # slow down password guessing
    return jsonify(error="Wrong password. Try again."), 401


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

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
    return jsonify(mode=MODE, sign_in=bool(PASSWORD))


def _prepare(body):
    """Check a chat request. Returns (error response, None) or (None, (agent, message, attachments, tool_calls))."""
    message = (body.get("message") or "").strip()
    try:
        attachments = [parse(a) for a in body.get("attachments") or []]
    except ValueError as e:
        return (jsonify(error=str(e)), 400), None
    if not message and not attachments:
        return (jsonify(error="Empty message"), 400), None
    if MODE == "Claude" and any(a.kind == "video" for a in attachments):
        return (jsonify(error="Claude can't watch videos. Send a photo instead, or use a Google Gemini key."), 400), None
    agent = _get_agent(body.get("session", "default"))
    tool_calls = []
    agent.on_tool_call = lambda name, args: tool_calls.append({"name": name, "args": args})
    return None, (agent, message, attachments, tool_calls)


def _begin_turn(agent, message, body):
    """Load the browser's alarms and tasks, and put local time and memory in front of the message."""
    daily.begin(body.get("daily"), body.get("now"), body.get("tz_offset"))
    context = []
    if body.get("local_time"):  # so "tomorrow" and "in 2 hours" mean the user's own time
        context.append(str(body["local_time"])[:60])
    if not getattr(agent, "primed", False):  # saves a recall round-trip on every new chat
        known = tools.memory_summary()
        if known:
            context.append(f"What you know about the user: {known}")
        agent.primed = True
    if hasattr(agent, "attempts"):
        agent.attempts = []
    return " ".join(f"[{c}]" for c in context) + f" {message}".rstrip() if context else message


def _friendly_error(e):
    """(message, status) for errors we can explain, or None for real bugs."""
    if isinstance(e, anthropic.AuthenticationError):
        return "Your Claude API key was rejected. Run ./add_key.sh again.", 401
    if isinstance(e, anthropic.RateLimitError):
        return "Rate limited. Wait a moment and try again.", 429
    if isinstance(e, anthropic.APIStatusError):
        return f"API error {e.status_code}: {e.message}", 502
    if isinstance(e, anthropic.APIConnectionError):
        return "Could not reach the Claude API. Check your connection.", 502
    if isinstance(e, TimeoutError):
        return str(e), 504
    if isinstance(e, genai_errors.APIError):
        if e.code in (400, 401, 403) and "key" in str(e).lower():
            return "Your Google API key was rejected. Run ./add_key.sh again.", 401
        if e.code == 429:
            return "Google's free limit is used up for now. Wait a bit and try again.", 429
        if e.code == 503:
            return "Google's Gemini models are overloaded right now. Try again in a minute.", 503
        return f"Google API error {e.code}: {e.message}", 502
    return None


def _meta(agent):
    return {"model": getattr(agent, "model", None), "attempts": getattr(agent, "attempts", [])}


@app.post("/api/chat")
def chat():
    body = request.get_json(force=True)
    error, prepared = _prepare(body)
    if error:
        return error
    agent, message, attachments, tool_calls = prepared
    try:
        answer = agent.chat(_begin_turn(agent, message, body), attachments)
    except Exception as e:
        friendly = _friendly_error(e)
        if not friendly:
            raise
        return jsonify(error=friendly[0]), friendly[1]
    return jsonify(answer=answer, tools=tool_calls, daily=daily.current_state(), meta=_meta(agent))


@app.post("/api/chat/stream")
def chat_stream():
    """Like /api/chat, but sends the reply as it's written: one JSON object per line,
    {"t": "delta", "text": ...} pieces, then {"t": "done", ...} or {"t": "error", ...}."""
    body = request.get_json(force=True)
    error, prepared = _prepare(body)
    if error:
        return error
    agent, message, attachments, tool_calls = prepared

    def line(obj):
        return json.dumps(obj) + "\n"

    def events():
        # Everything happens in here, so the browser's state is loaded on the thread
        # that actually streams the reply.
        try:
            turn = _begin_turn(agent, message, body)
            if hasattr(agent, "chat_stream"):
                pieces = []
                for piece in agent.chat_stream(turn, attachments):
                    pieces.append(piece)
                    yield line({"t": "delta", "text": piece})
                answer = "".join(pieces).strip() or "(no response)"
            else:  # Claude: no streaming here yet, so send the whole answer at once
                answer = agent.chat(turn, attachments)
            yield line({"t": "done", "answer": answer, "tools": tool_calls,
                        "daily": daily.current_state(), "meta": _meta(agent)})
        except Exception as e:
            friendly = _friendly_error(e)
            if not friendly:
                app.logger.exception("chat stream failed")
            yield line({"t": "error", "error": friendly[0] if friendly else "Something went wrong. Try again."})

    return Response(stream_with_context(events()), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/briefing")
def daily_briefing():
    body = request.get_json(silent=True) or {}
    daily.begin(body.get("daily"), body.get("now"), body.get("tz_offset"))
    return jsonify(answer=briefing.build())


@app.post("/api/reset")
def reset():
    body = request.get_json(force=True)
    with _lock:
        _agents.pop(body.get("session", "default"), None)
    return jsonify(ok=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"SSC web ({MODE}) running at http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, threaded=True)
