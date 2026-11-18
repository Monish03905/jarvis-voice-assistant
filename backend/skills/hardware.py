"""GPU, thermal and bottleneck diagnostics."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Optional

import psutil

log = logging.getLogger(__name__)

_GPU_CACHE: dict = {"at": 0.0, "data": []}


def _nvidia() -> list[dict]:
    if time.time() - _GPU_CACHE["at"] < 5 and _GPU_CACHE["data"]:
        return _GPU_CACHE["data"]
    query = (
        "name,utilization.gpu,memory.used,memory.total,"
        "temperature.gpu,power.draw,fan.speed"
    )
    try:
        proc = subprocess.run(
            ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6,
        )
        if proc.returncode != 0:
            return []
        cards = []
        for line in proc.stdout.strip().splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 4:
                continue

            def number(index: int) -> Optional[float]:
                try:
                    return float(parts[index])
                except (IndexError, ValueError):
                    return None

            cards.append({
                "name": parts[0],
                "util": number(1),
                "memory_used": number(2),
                "memory_total": number(3),
                "temperature": number(4),
                "power": number(5),
                "fan": number(6),
            })
        _GPU_CACHE.update(at=time.time(), data=cards)
        return cards
    except Exception as exc:
        log.debug("nvidia-smi unavailable: %s", exc)
        return []


def gpu_data() -> list[dict]:
    return _nvidia()


def gpu_stats() -> str:
    cards = _nvidia()
    if not cards:
        return "I cannot see an NVIDIA GPU on this machine, Sir."
    parts = []
    for card in cards:
        bits = [card["name"]]
        if card["util"] is not None:
            bits.append(f"{card['util']:.0f} percent load")
        if card["memory_used"] is not None and card["memory_total"]:
            bits.append(f"{card['memory_used']:.0f} of {card['memory_total']:.0f} megabytes VRAM")
        if card["temperature"] is not None:
            bits.append(f"{card['temperature']:.0f} degrees")
        if card["power"] is not None:
            bits.append(f"{card['power']:.0f} watts")
        parts.append(", ".join(bits))
    return "GPU: " + ". ".join(parts) + "."


def _wmi_temperature() -> Optional[float]:
    try:
        import wmi

        client = wmi.WMI(namespace="root\\wmi")
        zones = client.MSAcpi_ThermalZoneTemperature()
        if not zones:
            return None
        readings = [
            (zone.CurrentTemperature / 10.0) - 273.15 for zone in zones
            if zone.CurrentTemperature
        ]
        readings = [value for value in readings if -20 < value < 120]
        return max(readings) if readings else None
    except Exception as exc:
        log.debug("WMI temperature unavailable: %s", exc)
        return None


def temperature_data() -> dict:
    sensors: list[dict] = []
    try:
        for name, entries in (psutil.sensors_temperatures() or {}).items():
            for entry in entries:
                if entry.current:
                    sensors.append({
                        "name": entry.label or name,
                        "current": round(entry.current, 1),
                        "high": entry.high,
                    })
    except Exception:
        pass
    zone = None if sensors else _wmi_temperature()
    if zone is not None:
        sensors.append({"name": "ACPI thermal zone", "current": round(zone, 1), "high": None})
    gpu_temps = [
        {"name": card["name"], "current": card["temperature"], "high": None}
        for card in _nvidia()
        if card.get("temperature") is not None
    ]
    return {"sensors": sensors + gpu_temps}


def temperatures() -> str:
    data = temperature_data()["sensors"]
    if not data:
        return "This machine does not expose temperature sensors to Windows, Sir."
    parts = [
        f"{item['name']} {item['current']:.0f} degrees" for item in data[:6]
    ]
    return "Temperatures: " + ", ".join(parts) + "."


def diagnose_slowdown() -> str:
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    processes = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            processes.append(proc.info)
        except Exception:
            continue
    by_cpu = sorted(
        (proc for proc in processes if proc.get("cpu_percent") is not None),
        key=lambda proc: proc["cpu_percent"] or 0, reverse=True,
    )[:5]
    by_memory = sorted(
        (proc for proc in processes if proc.get("memory_percent") is not None),
        key=lambda proc: proc["memory_percent"] or 0, reverse=True,
    )[:3]

    findings: list[str] = []
    if cpu >= 85:
        findings.append(f"the processor is saturated at {cpu:.0f} percent")
    if memory.percent >= 88:
        findings.append(f"memory is nearly full at {memory.percent:.0f} percent")
    if disk.percent >= 92:
        findings.append(f"the system drive is {disk.percent:.0f} percent full")
    cards = _nvidia()
    for card in cards:
        if card.get("temperature") and card["temperature"] >= 85:
            findings.append(f"the GPU is running hot at {card['temperature']:.0f} degrees")
        if card.get("util") and card["util"] >= 95:
            findings.append(f"the GPU is pinned at {card['util']:.0f} percent")

    summary = (
        f"CPU {cpu:.0f} percent, memory {memory.percent:.0f} percent, "
        f"disk {disk.percent:.0f} percent used."
    )
    if findings:
        verdict = "I would blame " + "; ".join(findings) + "."
    else:
        verdict = "No single resource is saturated, so the slowdown is likely an app or storage latency."
    top = ", ".join(
        f"{proc['name']} ({proc.get('cpu_percent') or 0:.0f} percent CPU)"
        for proc in by_cpu[:3] if proc.get("name")
    )
    heaviest = ", ".join(
        f"{proc['name']} ({proc.get('memory_percent') or 0:.1f} percent RAM)"
        for proc in by_memory[:2] if proc.get("name")
    )
    extra = []
    if top:
        extra.append("Busiest processes: " + top + ".")
    if heaviest:
        extra.append("Memory hogs: " + heaviest + ".")
    battery = psutil.sensors_battery()
    if battery is not None:
        state = "charging" if battery.power_plugged else "on battery"
        extra.append(f"Battery {battery.percent:.0f} percent, {state}.")
    return " ".join([summary, verdict, *extra])


def vitals() -> dict:
    battery = psutil.sensors_battery()
    data = temperature_data()["sensors"]
    cards = _nvidia()
    return {
        "gpu": cards,
        "temperatures": data,
        "battery": battery.percent if battery else None,
        "charging": battery.power_plugged if battery else None,
    }
