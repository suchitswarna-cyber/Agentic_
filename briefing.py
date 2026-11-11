"""The daily briefing, built without the AI so it's quick.

Everything it needs is fetched at the same time: the weather for the user's
saved city and four news sections. Alarms and to-dos come from the browser.
"""

import random
import re
from concurrent.futures import ThreadPoolExecutor

import daily
import tools

NEWS = [("India", "india", "top"), ("USA", "usa", "top"),
        ("Current affairs", "india", "current affairs"), ("Technology", "usa", "technology")]

LINES = [
    "Arise, awake, and stop not till the goal is reached. — Swami Vivekananda",
    "If you want to shine like a sun, first burn like a sun. — A. P. J. Abdul Kalam",
    "The secret of getting ahead is getting started. — Mark Twain",
    "Believe you can and you're halfway there. — Theodore Roosevelt",
    "It does not matter how slowly you go as long as you do not stop. — Confucius",
    "Nothing will work unless you do. — Maya Angelou",
]


def _headlines(text: str) -> list:
    return [line[2:] for line in text.splitlines() if line.startswith("- ")]


def build() -> str:
    """The briefing as markdown. Call daily.begin() first."""
    city = daily.home_city()
    with ThreadPoolExecutor(max_workers=5) as pool:
        weather = pool.submit(tools.weather_text, city) if city else None
        news = [pool.submit(tools.news_text, country, topic, 10) for _, country, topic in NEWS]
        weather = weather.result() if weather else None
        news = [n.result() for n in news]

    parts = [f"**{daily.today_text()}**", "", "Weather:"]
    if weather is None:
        parts.append("Tell me your city, e.g. \"my city is Hyderabad\", and the weather will show here.")
    else:
        parts.append(weather.replace("Error: ", ""))

    parts += ["", "Today's alarms:"]
    alarms = daily.alarms_today()
    parts += [f"- {when} — {label}" for when, label in alarms] or ["No alarms today."]

    dates = daily.upcoming_dates(7)
    if dates:
        parts += ["", "Coming up:"]
        parts += [f"- {text}: {'today 🎉' if away == 0 else 'tomorrow' if away == 1 else f'in {away} days'}"
                  for away, text, _ in dates]

    habits = daily.habits_today()
    if habits:
        parts += ["", "Habits:"]
        parts += [f"- {name}: {done:g}/{goal:g} today · {streak}-day streak" for name, done, goal, streak in habits]

    spent = daily.month_spent()
    if spent:
        parts += ["", f"Spent this month: {daily._money(spent)}"]

    parts += ["", "To-do:"]
    tasks = daily.open_tasks()
    parts += [f"- {t}" for t in tasks[:8]] or ["Nothing on your list."]

    seen = set()
    for (title, _, _), text in zip(NEWS, news):
        picked = []
        for line in _headlines(text):
            key = re.sub(r"\W+", " ", line.split(" (")[0].lower())[:60]
            if key not in seen:
                seen.add(key)
                picked.append(f"- {line}")
            if len(picked) == 3:
                break
        parts += ["", f"{title}:"] + (picked or ["Couldn't load these headlines right now."])

    parts += ["", "---", f"*{random.choice(LINES)}*"]
    return "\n".join(parts)
