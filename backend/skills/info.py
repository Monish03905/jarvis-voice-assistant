"""Time, weather, web search, Wikipedia and a safe calculator."""

from __future__ import annotations

import ast
import datetime as dt
import html
import math
import operator
import re
from typing import Any
from urllib.parse import quote, unquote, urlparse, parse_qs

import requests

import config as cfg

_WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 56: "freezing drizzle", 57: "heavy freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain",
    67: "heavy freezing rain", 71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains", 80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers", 95: "a thunderstorm",
    96: "a thunderstorm with hail", 99: "a severe thunderstorm with hail",
}


# ---------------------------------------------------------------------------
# time & weather
# ---------------------------------------------------------------------------
def get_time() -> str:
    now = dt.datetime.now()
    return f"It is {now.strftime('%I:%M %p').lstrip('0')}, Sir."


def get_date() -> str:
    today = dt.date.today()
    return f"Today is {today.strftime('%A, %d %B %Y')}, Sir."


def _geocode(city: str) -> tuple[float, float, str] | None:
    try:
        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
        if not results:
            return None
        row = results[0]
        label = ", ".join(filter(None, [row.get("name"), row.get("admin1"), row.get("country")]))
        return float(row["latitude"]), float(row["longitude"]), label
    except Exception:
        return None


def get_weather(city: str = "") -> str:
    city = (city or cfg.DEFAULT_CITY).strip()
    place = _geocode(city)
    if place is None:
        return f"I could not find {city}, Sir."
    lat, lon, label = place
    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto", "forecast_days": 1,
            },
            timeout=12,
        )
        response.raise_for_status()
        data = response.json()
        current = data["current"]
        daily = data["daily"]
        code = int(current.get("weather_code", 0))
        condition = _WEATHER_CODES.get(code, "unsettled weather")
        return (
            f"In {label} it is {round(current['temperature_2m'])} degrees with {condition}. "
            f"Feels like {round(current['apparent_temperature'])}. "
            f"Today ranges from {round(daily['temperature_2m_min'][0])} to "
            f"{round(daily['temperature_2m_max'][0])}, with a "
            f"{daily['precipitation_probability_max'][0]} percent chance of rain. "
            f"Humidity {round(current['relative_humidity_2m'])} percent, "
            f"wind {round(current['wind_speed_10m'])} kilometres per hour, Sir."
        )
    except Exception as exc:
        # optional fallback to OpenWeatherMap when a key is present
        if cfg.WEATHER_API_KEY and not cfg.WEATHER_API_KEY.lower().startswith("your"):
            try:
                response = requests.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={"q": city, "appid": cfg.WEATHER_API_KEY, "units": "metric"},
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                return (
                    f"In {city} it is {round(data['main']['temp'])} degrees with "
                    f"{data['weather'][0]['description']}, Sir."
                )
            except Exception:
                pass
        return f"I could not fetch the weather, Sir. {exc}"


# ---------------------------------------------------------------------------
# web
# ---------------------------------------------------------------------------
def wikipedia_search(topic: str) -> str:
    topic = (topic or "").strip()
    if not topic:
        return "What topic should I look up, Sir?"
    try:
        response = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(topic.replace(' ', '_'))}",
            headers={"User-Agent": "JARVIS/3.0 (personal assistant)"},
            timeout=12,
        )
        if response.status_code != 200:
            return f"I could not find {topic} on Wikipedia, Sir."
        data = response.json()
        extract = data.get("extract") or ""
        if not extract:
            return f"I could not find a summary for {topic}, Sir."
        return extract
    except Exception as exc:
        return f"I could not reach Wikipedia, Sir. {exc}"


def web_search(query: str, limit: int = 3) -> str:
    query = (query or "").strip()
    if not query:
        return "What should I search for, Sir?"
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=12,
        )
        response.raise_for_status()
        blocks = re.findall(
            r'result__a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', response.text, re.DOTALL
        )
        results: list[str] = []
        for href, title in blocks:
            title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
            if not title:
                continue
            target = href
            if "uddg=" in target:
                target = unquote(parse_qs(urlparse(target).query).get("uddg", [target])[0])
            results.append(f"{title}: {target}")
            if len(results) >= limit:
                break
        if not results:
            return f"I did not find useful results for {query}, Sir."
        return "Here is what I found. " + " | ".join(results)
    except Exception as exc:
        return f"The web search failed, Sir. {exc}"


# ---------------------------------------------------------------------------
# calculator (AST whitelist - no eval)
# ---------------------------------------------------------------------------
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "exp": math.exp, "abs": abs,
    "round": round, "floor": math.floor, "ceil": math.ceil, "pi": math.pi,
    "e": math.e,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _FUNCS and not callable(_FUNCS[node.id]):
        return float(_FUNCS[node.id])
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
        func = _FUNCS[node.func.id]
        if callable(func):
            return float(func(*[_eval(arg) for arg in node.args]))
    raise ValueError("unsupported expression")


def calculate(expression: str) -> str:
    expression = (expression or "").strip()
    if not expression:
        return "What should I calculate, Sir?"
    cleaned = (
        expression.lower()
        .replace("×", "*").replace("÷", "/").replace("^", "**")
        .replace("plus", "+").replace("minus", "-").replace("times", "*")
        .replace("divided by", "/").replace("percent of", "/100*")
        .replace("what is", "").replace("calculate", "").replace("=", "")
        .strip()
    )
    cleaned = re.sub(r"[^0-9a-zA-Z_+\-*/().,%\s]", "", cleaned)
    cleaned = cleaned.replace(",", "")
    try:
        tree = ast.parse(cleaned, mode="eval")
        value = _eval(tree)
        if value.is_integer():
            value = int(value)
        else:
            value = round(value, 6)
        return f"That is {value}, Sir."
    except Exception:
        return "I could not evaluate that expression, Sir."
