"""Tools the agent can call.

Each function decorated with @beta_tool becomes a tool: the SDK builds the
JSON schema from the type hints and docstring, and the tool runner calls the
function when Claude asks for it.
"""

import ast
import json
import operator
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from anthropic import beta_tool

from daily import DAILY_TOOLS

# All file tools are confined to this folder so the agent can't touch the rest of the disk.
WORKSPACE = Path(__file__).parent / "workspace"
WORKSPACE.mkdir(exist_ok=True)
MEMORY_FILE = Path(__file__).parent / "memory.json"


def _safe_path(relative: str) -> Path:
    path = (WORKSPACE / relative).resolve()
    if not path.is_relative_to(WORKSPACE.resolve()):
        raise ValueError(f"Path '{relative}' is outside the workspace")
    return path


# --- Calculator -------------------------------------------------------------

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("Only numbers and + - * / // % ** are allowed")


@beta_tool
def calculator(expression: str) -> str:
    """Evaluate an arithmetic expression exactly. Use this instead of doing math in your head.

    Args:
        expression: An arithmetic expression, e.g. "(12.5 * 4) / 3 + 2**10".
    """
    try:
        return str(_eval(ast.parse(expression, mode="eval").body))
    except Exception as e:
        return f"Error: {e}"


# --- Time -------------------------------------------------------------------

@beta_tool
def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time.

    Args:
        timezone: IANA timezone name, e.g. "America/New_York" or "Asia/Kolkata".
    """
    try:
        return datetime.now(ZoneInfo(timezone)).strftime("%A, %Y-%m-%d %H:%M:%S %Z")
    except ZoneInfoNotFoundError:
        return f"Error: unknown timezone '{timezone}'"


# --- Weather and Wikipedia (free public APIs, no key needed) ----------------

def _get_json(url: str, params: dict) -> dict:
    request = urllib.request.Request(
        f"{url}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": "SSCBot/1.0 (github.com/suchitswarna-cyber/Agentic_)"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


@beta_tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert money between currencies using today's exchange rates.

    Args:
        amount: How much money, e.g. 100.
        from_currency: Three-letter code to convert from, e.g. "USD" (use "INR" for rupees).
        to_currency: Three-letter code to convert to, e.g. "INR".
    """
    src, dst = from_currency.strip().upper(), to_currency.strip().upper()
    try:
        data = _get_json(f"https://open.er-api.com/v6/latest/{urllib.parse.quote(src)}", {})
    except Exception:
        return "Couldn't reach the exchange-rate service. Try again in a minute."
    if data.get("result") != "success":
        return f"'{src}' isn't a currency code I know. Use three letters like USD, INR or EUR."
    rate = data.get("rates", {}).get(dst)
    if rate is None:
        return f"'{dst}' isn't a currency code I know. Use three letters like USD, INR or EUR."
    return (f"{amount:,.2f} {src} = {amount * rate:,.2f} {dst} (1 {src} = {rate:,.4f} {dst}). "
            f"Rates by ExchangeRate-API, updated {data.get('time_last_update_utc', 'today')[:16]}.")


# Google News feeds: top stories, or a topic, for each country's edition
_NEWS_EDITIONS = {"india": "hl=en-IN&gl=IN&ceid=IN:en", "usa": "hl=en-US&gl=US&ceid=US:en"}
_NEWS_ALIASES = {"in": "india", "bharat": "india", "us": "usa", "america": "usa", "united states": "usa"}
_NEWS_TOPICS = {
    "top": None, "current affairs": "NATION", "national": "NATION", "nation": "NATION",
    "technology": "TECHNOLOGY", "tech": "TECHNOLOGY", "business": "BUSINESS", "world": "WORLD",
    "science": "SCIENCE", "health": "HEALTH", "sports": "SPORTS", "entertainment": "ENTERTAINMENT",
}


def news_text(country: str = "india", topic: str = "top", count: int = 5) -> str:
    """Latest headlines for India or the USA, by topic, from Google News.

    Args:
        country: "india" or "usa".
        topic: "top" (main headlines), "current affairs" (national news), "technology",
            "business", "world", "science", "health", "sports" or "entertainment".
        count: How many headlines, 1 to 10.
    """
    key = country.strip().lower()
    key = _NEWS_ALIASES.get(key, key)
    if key not in _NEWS_EDITIONS:
        return "I can get news for India or the USA."
    subject = topic.strip().lower()
    if subject not in _NEWS_TOPICS:
        return "Topics I know: top, current affairs, technology, business, world, science, health, sports, entertainment."
    section = _NEWS_TOPICS[subject]
    url = (f"https://news.google.com/rss/headlines/section/topic/{section}?" if section
           else "https://news.google.com/rss?") + _NEWS_EDITIONS[key]
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (SSCBot)"})
        with urllib.request.urlopen(request, timeout=10) as response:
            root = ET.fromstring(response.read())
    except Exception:
        return "Couldn't reach the news service. Try again in a minute."
    now = datetime.now().astimezone()
    lines = []
    for item in root.findall("./channel/item")[: max(1, min(count, 10))]:
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            hours = int((now - parsedate_to_datetime(item.findtext("pubDate"))).total_seconds() // 3600)
            age = "just now" if hours < 1 else f"{hours}h ago" if hours < 48 else f"{hours // 24}d ago"
        except Exception:
            age = ""
        lines.append(f"- {title} ({', '.join(x for x in (source, age) if x)})")
    if not lines:
        return "No headlines found right now."
    place = "USA" if key == "usa" else "India"
    label = "top" if subject == "top" else subject
    return f"{place} {label} headlines (via Google News):\n" + "\n".join(lines)


@beta_tool
def get_news(country: str = "india", topic: str = "top", count: int = 5) -> str:
    """Get the latest news headlines for India or the USA.

    Args:
        country: "india" or "usa".
        topic: "top" (main headlines), "current affairs" (national news), "technology",
            "business", "world", "science", "health", "sports" or "entertainment".
        count: How many headlines, 1 to 10.
    """
    return news_text(country, topic, count)


# Open-Meteo weather codes -> plain words
_WEATHER = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "fog", 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
    75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "heavy showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def weather_text(city: str) -> str:
    """Current weather in plain words, from Open-Meteo or (if that fails) wttr.in."""
    try:
        places = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                           {"name": city, "count": 1}).get("results")
        if not places:
            return f"Error: couldn't find a city called '{city}'"
        place = places[0]
        now = _get_json("https://api.open-meteo.com/v1/forecast", {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "wind_speed_10m,weather_code",
        })["current"]
        return (
            f"{place['name']}, {place.get('country', '')}: "
            f"{_WEATHER.get(now['weather_code'], 'unknown conditions')}, "
            f"{now['temperature_2m']}°C (feels like {now['apparent_temperature']}°C), "
            f"humidity {now['relative_humidity_2m']}%, wind {now['wind_speed_10m']} km/h"
        )
    except Exception:
        pass
    # Open-Meteo often rate-limits shared hosting like Render, so fall back to wttr.in.
    try:
        data = _get_json(f"https://wttr.in/{urllib.parse.quote(city)}", {"format": "j1"})
        now, area = data["current_condition"][0], data["nearest_area"][0]
        return (
            f"{area['areaName'][0]['value']}, {area['country'][0]['value']}: "
            f"{now['weatherDesc'][0]['value'].strip().lower()}, {now['temp_C']}°C "
            f"(feels like {now['FeelsLikeC']}°C), humidity {now['humidity']}%, wind {now['windspeedKmph']} km/h"
        )
    except Exception:
        return "Error: the weather services are busy right now. Try again in a minute."


@beta_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city.

    Args:
        city: City name, e.g. "London" or "Hyderabad".
    """
    return weather_text(city)


@beta_tool
def search_wikipedia(query: str) -> str:
    """Look up a topic on Wikipedia and return a short summary. Use for facts about people, places, events, and concepts.

    Args:
        query: What to look up, e.g. "Alan Turing" or "photosynthesis".
    """
    try:
        hits = _get_json("https://en.wikipedia.org/w/api.php", {
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "srlimit": 1,
        })["query"]["search"]
        if not hits:
            return f"No Wikipedia article found for '{query}'"
        title = hits[0]["title"]
        summary = _get_json(
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + urllib.parse.quote(title.replace(" ", "_")), {})
        return f"{title}: {summary.get('extract', '(no summary)')}"
    except Exception as e:
        return f"Error: {e}"


# --- Files (sandboxed to ./workspace) ---------------------------------------

@beta_tool
def list_files() -> str:
    """List all files in the agent's workspace folder."""
    files = [str(p.relative_to(WORKSPACE)) for p in WORKSPACE.rglob("*") if p.is_file()]
    return "\n".join(sorted(files)) or "(workspace is empty)"


@beta_tool
def read_file(path: str) -> str:
    """Read a text file from the workspace.

    Args:
        path: File path relative to the workspace, e.g. "notes/todo.md".
    """
    try:
        return _safe_path(path).read_text()
    except Exception as e:
        return f"Error: {e}"


@beta_tool
def write_file(path: str, content: str) -> str:
    """Create or overwrite a text file in the workspace.

    Args:
        path: File path relative to the workspace, e.g. "report.md".
        content: The full text to write.
    """
    try:
        target = _safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} characters to {path}"
    except Exception as e:
        return f"Error: {e}"


# --- Long-term memory (persists across runs) --------------------------------

def _load_memory() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {}


@beta_tool
def remember(key: str, value: str) -> str:
    """Save a fact to long-term memory so it is available in future conversations.

    Args:
        key: Short label, e.g. "user_name" or "favorite_language".
        value: The fact to store.
    """
    memory = _load_memory()
    memory[key] = value
    MEMORY_FILE.write_text(json.dumps(memory, indent=2))
    return f"Remembered {key}"


def memory_summary() -> str:
    """Saved facts as one line, to hand the AI up front instead of a recall round-trip."""
    try:
        memory = _load_memory()
    except Exception:
        return ""
    return "; ".join(f"{k}: {v}" for k, v in memory.items())[:1000]


@beta_tool
def recall() -> str:
    """Return everything saved in long-term memory."""
    memory = _load_memory()
    return json.dumps(memory, indent=2) if memory else "(memory is empty)"


# Server-side tool: runs on Anthropic's infrastructure, no local code needed.
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}

# Tools that run on this computer (used by both the Claude and the local agent).
LOCAL_TOOLS = [
    calculator,
    get_current_time,
    get_weather,
    search_wikipedia,
    list_files,
    read_file,
    write_file,
    remember,
    recall,
    convert_currency,
    get_news,
    *DAILY_TOOLS,
]

ALL_TOOLS = LOCAL_TOOLS + [WEB_SEARCH]
