"""Home Assistant integration (lights, climate, scenes, sensors)."""

from __future__ import annotations

import logging
from typing import Optional

import requests

import config as cfg

log = logging.getLogger(__name__)

_DOMAINS = {
    "light", "switch", "fan", "climate", "scene", "cover", "media_player",
    "lock", "vacuum", "script", "input_boolean",
}


def configured() -> bool:
    return bool(cfg.HASS_URL and cfg.HASS_TOKEN and not cfg.HASS_TOKEN.lower().startswith("your"))


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {cfg.HASS_TOKEN}",
        "Content-Type": "application/json",
    }


def _get(path: str) -> object:
    response = requests.get(
        f"{cfg.HASS_URL}/api/{path}", headers=_headers(), timeout=cfg.HASS_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def _post(domain: str, service: str, data: dict) -> None:
    response = requests.post(
        f"{cfg.HASS_URL}/api/services/{domain}/{service}",
        headers=_headers(), json=data, timeout=cfg.HASS_TIMEOUT,
    )
    response.raise_for_status()


def _states() -> list[dict]:
    return [item for item in _get("states") if isinstance(item, dict)]


def _find(name: str, domain: Optional[str] = None) -> Optional[dict]:
    needle = (name or "").strip().lower()
    if not needle:
        return None
    matches = []
    for state in _states():
        entity_id = state.get("entity_id", "")
        entity_domain = entity_id.split(".", 1)[0]
        if domain and entity_domain != domain:
            continue
        if entity_domain not in _DOMAINS:
            continue
        friendly = (state.get("attributes", {}).get("friendly_name") or "").lower()
        if needle == entity_id.lower() or needle == friendly:
            return state
        if needle in friendly or needle in entity_id.lower():
            matches.append(state)
    return matches[0] if matches else None


def status() -> str:
    if not configured():
        return (
            "Home Assistant is not configured, Sir. Set HASS_URL and HASS_TOKEN in the "
            "environment file to link your home."
        )
    try:
        states = _states()
    except Exception as exc:
        return f"I could not reach Home Assistant, Sir. {exc}"
    lights = [s for s in states if s.get("entity_id", "").startswith("light.")]
    on = [s for s in lights if s.get("state") == "on"]
    climate = [s for s in states if s.get("entity_id", "").startswith("climate.")]
    unavailable = [s for s in states if s.get("state") == "unavailable"]
    parts = [
        f"Home Assistant is online with {len(states)} entities.",
        f"{len(on)} of {len(lights)} lights are on.",
    ]
    if climate:
        temps = []
        for entity in climate[:3]:
            target = entity.get("attributes", {}).get("temperature")
            name = entity.get("attributes", {}).get("friendly_name", "thermostat")
            if target is not None:
                temps.append(f"{name} at {target}")
        if temps:
            parts.append("Climate: " + ", ".join(temps) + ".")
    if unavailable:
        parts.append(f"{len(unavailable)} entities are unavailable.")
    return " ".join(parts)


def turn(entity: str, state: str = "on") -> str:
    if not configured():
        return status()
    found = _find(entity)
    if not found:
        return f"I could not find a home device called {entity}, Sir."
    entity_id = found["entity_id"]
    domain = entity_id.split(".", 1)[0]
    service = "turn_on" if (state or "on").lower() not in {"off", "false", "0"} else "turn_off"
    try:
        _post(domain, service, {"entity_id": entity_id})
    except Exception as exc:
        return f"I could not control {entity}, Sir. {exc}"
    name = found.get("attributes", {}).get("friendly_name", entity)
    return f"{name} switched {service.replace('turn_', '')}."


def light(name: str, state: str = "on", brightness: Optional[int] = None) -> str:
    if not configured():
        return status()
    found = _find(name, "light")
    if not found:
        return f"I could not find a light called {name}, Sir."
    entity_id = found["entity_id"]
    friendly = found.get("attributes", {}).get("friendly_name", name)
    try:
        if (state or "on").lower() in {"off", "false", "0"}:
            _post("light", "turn_off", {"entity_id": entity_id})
            return f"{friendly} is off."
        data: dict = {"entity_id": entity_id}
        if brightness is not None:
            data["brightness_pct"] = max(1, min(100, int(brightness)))
        _post("light", "turn_on", data)
    except Exception as exc:
        return f"I could not set {name}, Sir. {exc}"
    suffix = f" at {brightness} percent" if brightness is not None else ""
    return f"{friendly} is on{suffix}."


def climate(name: str, temperature: Optional[float] = None) -> str:
    if not configured():
        return status()
    found = _find(name, "climate")
    if not found:
        return f"I could not find a thermostat called {name}, Sir."
    entity_id = found["entity_id"]
    friendly = found.get("attributes", {}).get("friendly_name", name)
    current = found.get("attributes", {}).get("temperature")
    if temperature is None:
        return (
            f"{friendly} is set to {current}, currently {found.get('state')}, Sir."
            if current is not None else f"{friendly} is {found.get('state')}, Sir."
        )
    try:
        _post("climate", "set_temperature", {
            "entity_id": entity_id, "temperature": float(temperature)
        })
    except Exception as exc:
        return f"I could not set {name}, Sir. {exc}"
    return f"{friendly} set to {temperature} degrees."


def scene(name: str) -> str:
    if not configured():
        return status()
    found = _find(name, "scene")
    if not found:
        return f"I could not find a scene called {name}, Sir."
    try:
        _post("scene", "turn_on", {"entity_id": found["entity_id"]})
    except Exception as exc:
        return f"I could not activate {name}, Sir. {exc}"
    friendly = found.get("attributes", {}).get("friendly_name", name)
    return f"Scene {friendly} activated."


def summary_data() -> dict:
    if not configured():
        return {"configured": False, "entities": []}
    try:
        states = _states()
    except Exception as exc:
        return {"configured": True, "error": str(exc), "entities": []}
    return {
        "configured": True,
        "entities": [
            {
                "entity_id": state.get("entity_id"),
                "name": state.get("attributes", {}).get("friendly_name", state.get("entity_id")),
                "state": state.get("state"),
            }
            for state in states
            if state.get("entity_id", "").split(".", 1)[0] in _DOMAINS
        ][:120],
    }
