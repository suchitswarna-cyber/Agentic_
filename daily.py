"""Daily helpers: alarms, reminders, timers, a to-do list, quick notes, spending,
habits and important dates (birthdays, anniversaries).

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
    city = state.get("city") if isinstance(state.get("city"), str) else ""
    expenses = [x for x in state.get("expenses") or [] if isinstance(x, dict) and isinstance(x.get("amount"), (int, float))]
    habits = [h for h in state.get("habits") or [] if isinstance(h, dict) and isinstance(h.get("name"), str)]
    dates = [d for d in state.get("dates") or [] if isinstance(d, dict) and isinstance(d.get("month"), int) and isinstance(d.get("day"), int)]
    for h in habits:
        h["log"] = h["log"] if isinstance(h.get("log"), dict) else {}
    try:
        now_ms = float(now_ms)
        tz_offset_min = int(tz_offset_min)
    except (TypeError, ValueError):
        now_ms, tz_offset_min = datetime.now(timezone.utc).timestamp() * 1000, 0
    _ctx.set({"reminders": reminders[:MAX_ITEMS], "todos": todos[:MAX_ITEMS], "notes": notes[:MAX_ITEMS],
              "expenses": expenses[-500:], "habits": habits[:30], "dates": dates[:MAX_ITEMS],
              "city": city[:80], "now": now_ms, "offset": tz_offset_min})


def current_state():
    """The alarms, tasks and notes to send back to the browser (None outside the web page)."""
    c = _ctx.get()
    if c is None:
        return None
    return {key: c[key] for key in ("reminders", "todos", "notes", "expenses", "habits", "dates", "city")}


def home_city() -> str:
    c = _ctx.get()
    return c["city"] if c else ""


def alarms_today() -> list:
    """Alarms and timers due before the end of the user's day, as (time text, label)."""
    c = _get()
    end = _now(c).replace(hour=23, minute=59, second=59)
    return [(_when(r["due"], c).replace(" today", ""), r.get("label", "Alarm"))
            for r in sorted(c["reminders"], key=lambda r: r["due"]) if r["due"] <= _ms(end)]


def open_tasks() -> list:
    return [t["text"] for t in _get()["todos"] if not t.get("done")]


def today_text() -> str:
    return _now(_get()).strftime("%A, %d %B %Y").replace(" 0", " ")


@beta_tool
def set_home_city(city: str) -> str:
    """Save the user's home city, used for the weather in the daily briefing.

    Args:
        city: The city, e.g. "Hyderabad".
    """
    c = _get()
    c["city"] = city.strip()[:80]
    return f"Saved your city as {c['city']}."


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


# --- Spending ---------------------------------------------------------------

def _money(x: float) -> str:
    return f"₹{x:,.2f}".replace(".00", "")


def _since(period: str, c):
    now = _now(c)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period = period.strip().lower()
    if period == "today":
        return start, "today"
    if period == "week":
        return start - timedelta(days=start.weekday()), "this week"
    if period == "all":
        return None, "in total"
    return start.replace(day=1), "this month"


def month_spent() -> float:
    c = _get()
    start, _ = _since("month", c)
    return sum(x["amount"] for x in c["expenses"] if x.get("at", 0) >= _ms(start))


@beta_tool
def add_expense(amount: float, what: str, category: str = "Other") -> str:
    """Log money the user spent, in rupees, e.g. "spent 250 on lunch".

    Convert other currencies to rupees with convert_currency first.

    Args:
        amount: How much, in rupees.
        what: What it was for, e.g. "Lunch".
        category: One of Food, Travel, Shopping, Bills, Health, Fun, Other.
    """
    c = _get()
    if not 0 < amount < 1e9:
        return "The amount must be more than zero."
    category = category.strip().title() or "Other"
    c["expenses"].append({"id": secrets.token_hex(4), "amount": round(float(amount), 2), "what": what.strip()[:100] or category,
                          "category": category[:30], "at": int(c["now"])})
    c["expenses"] = c["expenses"][-500:]
    return f"Logged {_money(amount)} for {what} ({category}). This month so far: {_money(month_spent())}."


@beta_tool
def spending_summary(period: str = "month") -> str:
    """Show how much the user spent, by category, with the latest items.

    Args:
        period: "today", "week", "month" or "all".
    """
    c = _get()
    start, label = _since(period, c)
    items = [x for x in c["expenses"] if start is None or x.get("at", 0) >= _ms(start)]
    if not items:
        return f"No spending logged {label}."
    by_cat = {}
    for x in items:
        by_cat[x.get("category", "Other")] = by_cat.get(x.get("category", "Other"), 0) + x["amount"]
    lines = [f"Spent {_money(sum(by_cat.values()))} {label}:"]
    lines += [f"- {cat}: {_money(v)}" for cat, v in sorted(by_cat.items(), key=lambda kv: -kv[1])]
    lines.append("Latest:")
    lines += [f"{n}. {_money(x['amount'])} {x['what']} ({_when(x['at'], c)})" for n, x in enumerate(reversed(items[-10:]), 1)]
    return "\n".join(lines)


@beta_tool
def remove_expense(which: str) -> str:
    """Delete logged spending.

    Args:
        which: "last" for the latest entry, words from what it was for, or "all".
    """
    c = _get()
    if which.strip().lower() == "last":
        found = c["expenses"][-1:]
    else:
        found = _pick([dict(x, text=x.get("what", "")) for x in c["expenses"]], which)
        ids = {x["id"] for x in found}
        found = [x for x in c["expenses"] if x["id"] in ids]
    if not found:
        return f"No spending matches '{which}'."
    c["expenses"] = [x for x in c["expenses"] if x not in found]
    return "Removed: " + ", ".join(f"{_money(x['amount'])} {x['what']}" for x in found)


# --- Habits -----------------------------------------------------------------

def _today_key(c) -> str:
    return _now(c).date().isoformat()


def _streak(h, c) -> int:
    day, n = _now(c).date(), 0
    goal = h.get("goal") or 1
    if h["log"].get(day.isoformat(), 0) < goal:  # today isn't done yet; count from yesterday
        day -= timedelta(days=1)
    while h["log"].get(day.isoformat(), 0) >= goal:
        n += 1
        day -= timedelta(days=1)
    return n


def habits_today() -> list:
    c = _get()
    return [(h["name"], h["log"].get(_today_key(c), 0), h.get("goal") or 1, _streak(h, c)) for h in c["habits"]]


@beta_tool
def log_habit(name: str, amount: float = 1, daily_goal: float = 0) -> str:
    """Track a daily habit, e.g. "drank a glass of water", "did my workout", "read 20 pages".

    A new habit is created the first time it's logged.

    Args:
        name: The habit, e.g. "Water" or "Workout".
        amount: How much to add for today (1 if not said). Use 0 to only set the goal.
        daily_goal: Optional daily target, e.g. 8 glasses of water. 0 keeps the current goal.
    """
    c = _get()
    key = name.strip().lower()
    h = next((h for h in c["habits"] if h["name"].lower() == key), None)
    if h is None:
        if len(c["habits"]) >= 30:
            return "You're tracking too many habits. Remove one first."
        h = {"id": secrets.token_hex(4), "name": name.strip().title()[:40], "goal": 1, "log": {}}
        c["habits"].append(h)
    if daily_goal > 0:
        h["goal"] = daily_goal
    today = _today_key(c)
    h["log"][today] = max(0, h["log"].get(today, 0) + amount)
    h["log"] = dict(sorted(h["log"].items())[-60:])  # keep two months
    done, goal = h["log"][today], h.get("goal") or 1
    status = "goal reached 🎉" if done >= goal else f"{goal - done:g} to go"
    return f"{h['name']}: {done:g}/{goal:g} today, {status}. Streak: {_streak(h, c)} day(s)."


@beta_tool
def habit_progress() -> str:
    """Show today's progress and the streak for each habit the user tracks."""
    rows = habits_today()
    if not rows:
        return "No habits tracked yet."
    return "\n".join(f"- {name}: {done:g}/{goal:g} today, streak {streak} day(s)" for name, done, goal, streak in rows)


@beta_tool
def remove_habit(name: str) -> str:
    """Stop tracking a habit.

    Args:
        name: The habit's name, or "all".
    """
    c = _get()
    found = _pick([dict(h, text=h["name"]) for h in c["habits"]], name)
    ids = {h["id"] for h in found}
    if not ids:
        return f"No habit matches '{name}'."
    c["habits"] = [h for h in c["habits"] if h["id"] not in ids]
    return "Stopped tracking: " + ", ".join(h["name"] for h in found)


# --- Important dates --------------------------------------------------------

def _next_on(d, today: date) -> date:
    for year in (today.year, today.year + 1):
        try:
            when = date(year, d["month"], d["day"])
        except ValueError:  # 29 Feb in a normal year
            when = date(year, 3, 1)
        if when >= today:
            return when
    return today


def upcoming_dates(days: int = 7) -> list:
    """Dates in the next few days, as (days away, text)."""
    c = _get()
    today = _now(c).date()
    out = []
    for d in c["dates"]:
        when = _next_on(d, today)
        away = (when - today).days
        if away <= days:
            text = f"{d['name']}'s {d.get('kind', 'birthday')}" if d.get("kind") in ("birthday", "anniversary") else d["name"]
            if d.get("year") and d.get("kind") in ("birthday", "anniversary"):
                text += f" ({when.year - d['year']})"
            out.append((away, text, when))
    return sorted(out)


@beta_tool
def add_date(name: str, date_text: str, kind: str = "birthday") -> str:
    """Save a birthday, anniversary or yearly event so SSC reminds the user in the briefing.

    Args:
        name: Whose it is or what it is, e.g. "Mom" or "Diwali party".
        date_text: "MM-DD" or "YYYY-MM-DD" (with the year if known, to show the age), e.g. "1995-03-14".
        kind: "birthday", "anniversary" or "event".
    """
    c = _get()
    m = re.fullmatch(r"\s*(?:(\d{4})-)?(\d{1,2})-(\d{1,2})\s*", date_text)
    if not m:
        return "Give the date as MM-DD or YYYY-MM-DD, e.g. 03-14."
    year, month, day_ = (int(m.group(1)) if m.group(1) else None), int(m.group(2)), int(m.group(3))
    try:
        date(year or 2000, month, day_)
    except ValueError:
        return f"'{date_text}' isn't a real date."
    kind = kind.strip().lower() if kind.strip().lower() in ("birthday", "anniversary", "event") else "event"
    if len(c["dates"]) >= MAX_ITEMS:
        return "You have too many dates saved. Remove some first."
    c["dates"].append({"id": secrets.token_hex(4), "name": name.strip()[:60], "kind": kind,
                       "month": month, "day": day_, "year": year})
    when = _next_on(c["dates"][-1], _now(c).date())
    what = name if kind == "event" else f"{name}'s {kind}"
    return f"Saved {what} on {when.strftime('%d %B').lstrip('0')}. It's {(when - _now(c).date()).days} day(s) away."


@beta_tool
def list_dates() -> str:
    """List saved birthdays, anniversaries and events, soonest first."""
    c = _get()
    if not c["dates"]:
        return "No dates saved."
    rows = upcoming_dates(366)
    return "\n".join(f"{n}. {text}: {when.strftime('%d %b').lstrip('0')} ({'today' if away == 0 else f'in {away} day(s)'})"
                     for n, (away, text, when) in enumerate(rows, 1))


@beta_tool
def remove_date(which: str) -> str:
    """Delete saved dates.

    Args:
        which: Words from the name, or "all".
    """
    c = _get()
    found = _pick([dict(d, text=d["name"]) for d in c["dates"]], which)
    ids = {d["id"] for d in found}
    if not ids:
        return f"No date matches '{which}'."
    c["dates"] = [d for d in c["dates"] if d["id"] not in ids]
    return "Removed: " + ", ".join(d["name"] for d in found)


DAILY_TOOLS = [set_alarm, set_timer, list_alarms, cancel_alarm, add_task, list_tasks, complete_task, remove_task,
               add_note, list_notes, delete_note, set_home_city,
               add_expense, spending_summary, remove_expense, log_habit, habit_progress, remove_habit,
               add_date, list_dates, remove_date]
