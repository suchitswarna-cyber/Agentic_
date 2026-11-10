"""Daily helpers: alarms, reminders, timers, a to-do list and quick notes.

These are kept in the user's browser, not on the server, so they survive the
server restarting. The web page sends them along with each message (plus its
local time), the tools below change them, and the page saves what comes back
and rings the alarms.
"""

import contextvars
import re
import secrets
from datetime import date, datetime, timedelta, timezone

from anthropic import beta_tool

_ctx = contextvars.ContextVar("daily", default=None)

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
REPEATS = ("once", "daily", "weekdays")
MAX_ITEMS = 100


def begin(state, now_ms, tz_offset_min) -> None:
    """Load the browser's alarms and tasks for this request."""
    state = state if isinstance(state, dict) else {}
    reminders = [r for r in state.get("reminders") or [] if isinstance(r, dict) and isinstance(r.get("due"), (int, float))]
    todos = [t for t in state.get("todos") or [] if isinstance(t, dict) and isinstance(t.get("text"), str)]
    notes = [n for n in state.get("notes") or [] if isinstance(n, dict) and isinstance(n.get("text"), str)]
    try:
        now_ms = float(now_ms)
        tz_offset_min = int(tz_offset_min)
    except (TypeError, ValueError):
        now_ms, tz_offset_min = datetime.now(timezone.utc).timestamp() * 1000, 0
    _ctx.set({"reminders": reminders[:MAX_ITEMS], "todos": todos[:MAX_ITEMS], "notes": notes[:MAX_ITEMS],
              "now": now_ms, "offset": tz_offset_min})


def current_state():
    """The alarms, tasks and notes to send back to the browser (None outside the web page)."""
    c = _ctx.get()
    return None if c is None else {"reminders": c["reminders"], "todos": c["todos"], "notes": c["notes"]}


def _get():
    c = _ctx.get()
    if c is None:
        raise RuntimeError("Alarms and tasks only work in the SSC web page.")
    return c


def _now(c) -> datetime:
    # getTimezoneOffset() is minutes *behind* UTC, e.g. -330 for India.
    return datetime.fromtimestamp(c["now"] / 1000, tz=timezone(timedelta(minutes=-c["offset"])))


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _when(due_ms: int, c) -> str:
    dt = datetime.fromtimestamp(due_ms / 1000, tz=_now(c).tzinfo)
    today = _now(c).date()
    day = "today" if dt.date() == today else "tomorrow" if dt.date() == today + timedelta(days=1) else dt.strftime("%a %d %b")
    return f"{dt.strftime('%I:%M %p').lstrip('0')} {day}"


def _parse_time(text: str):
    m = re.fullmatch(r"\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*", text.lower())
    if not m:
        raise ValueError(f"I couldn't read the time '{text}'. Use something like 07:30 or 7pm.")
    hour, minute, half = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").replace(".", "")
    if half == "pm" and hour < 12:
        hour += 12
    if half == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        raise ValueError(f"'{text}' isn't a valid time.")
    return hour, minute


def _parse_day(text: str, today: date):
    text = text.strip().lower()
    if text in ("", "next"):
        return None
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if text in WEEKDAYS:
        ahead = (WEEKDAYS.index(text) - today.weekday()) % 7
        return today + timedelta(days=ahead)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"I couldn't read the day '{text}'. Use today, tomorrow, a weekday or YYYY-MM-DD.")


def _pick(items: list, which: str):
    """Find items by list number ("2"), by words in their text, or "all"."""
    which = which.strip().lower()
    if which == "all":
        return list(items)
    if which.isdigit() and 1 <= int(which) <= len(items):
        return [items[int(which) - 1]]
    return [i for i in items if which and which in (i.get("label") or i.get("text") or "").lower()]


@beta_tool
def set_alarm(time: str, label: str = "Alarm", day: str = "", repeat: str = "once") -> str:
    """Set an alarm or reminder that rings in the user's SSC page at a clock time.

    Use for "wake me up at 7", "remind me to call mom at 6pm tomorrow" or
    "alarm every weekday at 6:30".

    Args:
        time: Clock time, e.g. "07:30", "7pm" or "18:45".
        label: What it's for, e.g. "Call mom". Use "Alarm" if nothing was said.
        day: "today", "tomorrow", a weekday like "friday", or a date "2026-11-20". Leave empty for the next time that clock time comes round.
        repeat: "once", "daily" or "weekdays".
    """
    c = _get()
    try:
        hour, minute = _parse_time(time)
        now = _now(c)
        on = _parse_day(day, now.date())
    except ValueError as e:
        return str(e)
    repeat = repeat if repeat in REPEATS else "once"
    due = datetime.combine(on or now.date(), datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
    if due <= now:
        if on is None:  # no day given: the next time this clock time comes round
            due += timedelta(days=1)
        elif day.strip().lower() in WEEKDAYS:  # e.g. "monday" said on a Monday after that time
            due += timedelta(days=7)
        else:
            return "That time has already passed. Pick a later time or another day."
    while repeat == "weekdays" and due.weekday() >= 5:
        due += timedelta(days=1)
    if len(c["reminders"]) >= MAX_ITEMS:
        return "You have too many alarms. Cancel some first."
    item = {"id": secrets.token_hex(4), "kind": "alarm", "label": label.strip() or "Alarm", "due": _ms(due), "repeat": repeat}
    c["reminders"].append(item)
    c["reminders"].sort(key=lambda r: r["due"])
    again = {"daily": ", every day", "weekdays": ", every weekday"}.get(repeat, "")
    return f"Alarm set: '{item['label']}' at {_when(item['due'], c)}{again}. It rings while the SSC page is open."


@beta_tool
def set_timer(minutes: float, label: str = "Timer") -> str:
    """Start a countdown timer that rings in the user's SSC page.

    Args:
        minutes: How long, in minutes. Use decimals for seconds, e.g. 0.5 for 30 seconds.
        label: What it's for, e.g. "Rice". Use "Timer" if nothing was said.
    """
    c = _get()
    if not 0 < minutes <= 24 * 60:
        return "Timers can be from a few seconds up to 24 hours."
    due = _now(c) + timedelta(minutes=minutes)
    item = {"id": secrets.token_hex(4), "kind": "timer", "label": label.strip() or "Timer", "due": _ms(due), "repeat": "once"}
    c["reminders"].append(item)
    c["reminders"].sort(key=lambda r: r["due"])
    return f"Timer set: '{item['label']}' for {minutes:g} minute(s), ringing at {_when(item['due'], c)}."


@beta_tool
def list_alarms() -> str:
    """List the user's alarms, reminders and timers, numbered."""
    c = _get()
    if not c["reminders"]:
        return "No alarms, reminders or timers set."
    lines = []
    for n, r in enumerate(c["reminders"], 1):
        again = {"daily": " (every day)", "weekdays": " (weekdays)"}.get(r.get("repeat"), "")
        lines.append(f"{n}. {r.get('label', 'Alarm')} at {_when(r['due'], c)}{again} [{r.get('kind', 'alarm')}]")
    return "\n".join(lines)


@beta_tool
def cancel_alarm(which: str) -> str:
    """Cancel alarms, reminders or timers.

    Args:
        which: The number from list_alarms, words from its label, or "all".
    """
    c = _get()
    gone = _pick(c["reminders"], which)
    if not gone:
        return f"No alarm matches '{which}'. Call list_alarms to see them."
    c["reminders"] = [r for r in c["reminders"] if r not in gone]
    return "Cancelled: " + ", ".join(r.get("label", "Alarm") for r in gone)


@beta_tool
def add_task(text: str) -> str:
    """Add an item to the user's to-do list.

    Args:
        text: The task, e.g. "Buy milk".
    """
    c = _get()
    text = text.strip()
    if not text:
        return "The task is empty."
    if len(c["todos"]) >= MAX_ITEMS:
        return "Your to-do list is full. Remove some tasks first."
    c["todos"].append({"id": secrets.token_hex(4), "text": text[:200], "done": False})
    return f"Added to your to-do list: {text}"


@beta_tool
def list_tasks() -> str:
    """List the user's to-do list, numbered, with done items ticked."""
    c = _get()
    if not c["todos"]:
        return "The to-do list is empty."
    return "\n".join(f"{n}. [{'x' if t.get('done') else ' '}] {t['text']}" for n, t in enumerate(c["todos"], 1))


@beta_tool
def complete_task(which: str) -> str:
    """Tick off tasks as done.

    Args:
        which: The number from list_tasks, words from the task, or "all".
    """
    c = _get()
    found = _pick(c["todos"], which)
    if not found:
        return f"No task matches '{which}'. Call list_tasks to see them."
    for t in found:
        t["done"] = True
    return "Done: " + ", ".join(t["text"] for t in found)


@beta_tool
def remove_task(which: str) -> str:
    """Delete tasks from the to-do list.

    Args:
        which: The number from list_tasks, words from the task, "done" for every ticked task, or "all".
    """
    c = _get()
    found = [t for t in c["todos"] if t.get("done")] if which.strip().lower() == "done" else _pick(c["todos"], which)
    if not found:
        return f"No task matches '{which}'."
    c["todos"] = [t for t in c["todos"] if t not in found]
    return "Removed: " + ", ".join(t["text"] for t in found)


@beta_tool
def add_note(text: str) -> str:
    """Save a quick note for the user, e.g. a password hint, a parking spot or an idea.

    Args:
        text: The note to save.
    """
    c = _get()
    text = text.strip()
    if not text:
        return "The note is empty."
    if len(c["notes"]) >= MAX_ITEMS:
        return "Your notes are full. Delete some first."
    c["notes"].insert(0, {"id": secrets.token_hex(4), "text": text[:1000], "at": int(c["now"])})
    return f"Saved note: {text}"


@beta_tool
def list_notes() -> str:
    """List the user's saved notes, newest first, numbered."""
    c = _get()
    if not c["notes"]:
        return "No notes saved."
    return "\n".join(f"{n}. {note['text']} (saved {_when(note.get('at', c['now']), c)})" for n, note in enumerate(c["notes"], 1))


@beta_tool
def delete_note(which: str) -> str:
    """Delete saved notes.

    Args:
        which: The number from list_notes, words from the note, or "all".
    """
    c = _get()
    found = _pick(c["notes"], which)
    if not found:
        return f"No note matches '{which}'. Call list_notes to see them."
    c["notes"] = [n for n in c["notes"] if n not in found]
    return "Deleted: " + ", ".join(n["text"][:40] for n in found)


DAILY_TOOLS = [set_alarm, set_timer, list_alarms, cancel_alarm, add_task, list_tasks, complete_task, remove_task,
               add_note, list_notes, delete_note]
