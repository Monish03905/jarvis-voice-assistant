"""File and folder management with human-friendly locations."""

from __future__ import annotations

import os
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

HOME = Path.home()
LOCATIONS = {
    "desktop": HOME / "Desktop",
    "downloads": HOME / "Downloads",
    "documents": HOME / "Documents",
    "pictures": HOME / "Pictures",
    "videos": HOME / "Videos",
    "music": HOME / "Music",
    "home": HOME,
    "jarvis": Path(__file__).resolve().parents[2] / "data",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "AppData",
    ".cache", "site-packages", "Windows", "Program Files", "Program Files (x86)",
    "$Recycle.Bin", "System Volume Information",
}

CATEGORY_MAP = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx",
                  ".ppt", ".pptx", ".csv", ".md"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"},
    "Video": {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg"},
}


def resolve_location(location: str | None) -> Path:
    if not location:
        return LOCATIONS["desktop"]
    text = str(location).strip().strip('"')
    key = text.lower()
    if key in LOCATIONS:
        return LOCATIONS[key]
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    if not path.is_absolute():
        path = LOCATIONS["desktop"] / path
    return path


def _fmt(path: Path) -> str:
    return str(path)


def create_folder(name: str, location: str = "Desktop") -> str:
    if not name:
        return "What should I call the folder, Sir?"
    try:
        base = resolve_location(location)
        base.mkdir(parents=True, exist_ok=True)
        target = base / name.strip().strip('"')
        target.mkdir(parents=True, exist_ok=True)
        return f"Folder ready at {_fmt(target)}."
    except Exception as exc:
        return f"I could not create that folder, Sir. {exc}"


def create_file(name: str, location: str = "Desktop", content: str = "") -> str:
    if not name:
        return "What should I call the file, Sir?"
    try:
        base = resolve_location(location)
        base.mkdir(parents=True, exist_ok=True)
        target = base / name.strip().strip('"')
        if not target.suffix:
            target = target.with_suffix(".txt")
        target.write_text(content or "", encoding="utf-8")
        return f"File created at {_fmt(target)}."
    except Exception as exc:
        return f"I could not create that file, Sir. {exc}"


def write_file(path: str, content: str) -> str:
    if not path:
        return "Which file should I write to, Sir?"
    try:
        target = Path(os.path.expandvars(os.path.expanduser(path)))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content or "", encoding="utf-8")
        return f"Written to {_fmt(target)}."
    except Exception as exc:
        return f"I could not write that file, Sir. {exc}"


def read_file(path: str, max_chars: int = 3000) -> str:
    if not path:
        return "Which file should I read, Sir?"
    target = Path(os.path.expandvars(os.path.expanduser(path)))
    if not target.is_file():
        found = _find_exact(target.name)
        if not found:
            return f"I could not find {path}, Sir."
        target = found
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
        snippet = re.sub(r"\s+", " ", text)[:max_chars]
        return f"Here is {target.name}: {snippet}"
    except Exception as exc:
        return f"I could not read that file, Sir. {exc}"


def list_files(directory: str = "Desktop") -> str:
    try:
        base = resolve_location(directory)
        if not base.exists():
            return f"{base} does not exist, Sir."
        items = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        if not items:
            return f"{base.name} is empty, Sir."
        names = [f"{p.name}/" if p.is_dir() else p.name for p in items[:40]]
        extra = "" if len(items) <= 40 else f" and {len(items) - 40} more"
        return f"{base.name} contains: " + ", ".join(names) + extra + "."
    except Exception as exc:
        return f"I could not list that folder, Sir. {exc}"


def _walk(root: Path, limit_seconds: float = 6.0, max_depth: int = 6) -> Iterable[Path]:
    deadline = time.time() + limit_seconds
    root_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        if time.time() > deadline:
            return
        if len(Path(current).parts) - root_depth >= max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in files:
            yield Path(current) / name


def find_files(name: str, location: str | None = None, limit: int = 12) -> list[Path]:
    needle = (name or "").lower().strip()
    if not needle:
        return []
    roots = [resolve_location(location)] if location else [
        LOCATIONS["desktop"], LOCATIONS["documents"], LOCATIONS["downloads"],
        LOCATIONS["pictures"], LOCATIONS["videos"], LOCATIONS["music"],
    ]
    results: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in _walk(root):
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            if needle in path.name.lower():
                results.append(path)
                if len(results) >= limit:
                    return results
    return results


def _find_exact(name: str) -> Optional[Path]:
    for path in find_files(name, limit=50):
        if path.name.lower() == name.lower():
            return path
    found = find_files(name, limit=1)
    return found[0] if found else None


def search_file(name: str, location: str | None = None) -> str:
    if not name:
        return "What am I looking for, Sir?"
    started = time.time()
    found = find_files(name, location)
    if not found:
        return f"I could not find anything matching {name}, Sir."
    elapsed = time.time() - started
    top = "; ".join(_fmt(p) for p in found[:6])
    more = "" if len(found) <= 6 else f" (and {len(found) - 6} more)"
    return f"Found {len(found)} match{'es' if len(found) != 1 else ''} in {elapsed:.1f} seconds: {top}{more}."


def open_path(path: str | Path) -> str:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
        return f"Opening {Path(path).name}, Sir."
    except Exception as exc:
        return f"I could not open that, Sir. {exc}"


def open_file(name: str) -> str:
    if not name:
        return "Which file should I open, Sir?"
    candidate = Path(os.path.expandvars(os.path.expanduser(name)))
    target = candidate if candidate.exists() else _find_exact(Path(name).name)
    if not target:
        return f"I could not find {name}, Sir."
    return open_path(target)


def move_file(src: str, dest: str) -> str:
    if not src or not dest:
        return "I need both a source and a destination, Sir."
    try:
        source = Path(os.path.expandvars(os.path.expanduser(src)))
        if not source.exists():
            found = _find_exact(source.name)
            if not found:
                return f"I could not find {src}, Sir."
            source = found
        target = resolve_location(dest)
        if target.suffix or (target.exists() and target.is_file()):
            target.parent.mkdir(parents=True, exist_ok=True)
            final = target
        else:
            target.mkdir(parents=True, exist_ok=True)
            final = target / source.name
        if final.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            final = final.with_name(f"{final.stem}_{stamp}{final.suffix}")
        shutil.move(str(source), str(final))
        return f"Moved to {_fmt(final)}."
    except Exception as exc:
        return f"I could not move that, Sir. {exc}"


def rename_file(old: str, new: str) -> str:
    if not old or not new:
        return "I need the current name and the new name, Sir."
    try:
        source = Path(os.path.expandvars(os.path.expanduser(old)))
        if not source.exists():
            found = _find_exact(source.name)
            if not found:
                return f"I could not find {old}, Sir."
            source = found
        target = source.with_name(new)
        source.rename(target)
        return f"Renamed to {target.name}."
    except Exception as exc:
        return f"I could not rename that, Sir. {exc}"


def delete_file(path: str) -> str:
    if not path:
        return "Which file should I remove, Sir?"
    try:
        target = Path(os.path.expandvars(os.path.expanduser(path)))
        if not target.exists():
            found = _find_exact(target.name)
            if not found:
                return f"I could not find {path}, Sir."
            target = found
        from send2trash import send2trash

        send2trash(str(target))
        return f"{target.name} sent to the Recycle Bin, Sir."
    except Exception as exc:
        return f"I could not delete that, Sir. {exc}"


def organize_folder(directory: str = "Downloads", dry_run: bool = False) -> str:
    """Sort a messy folder into Images/Documents/Audio/Video/Archives."""
    try:
        base = resolve_location(directory)
        if not base.exists():
            return f"{base} does not exist, Sir."
        moved = 0
        for item in base.iterdir():
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            category = next((k for k, exts in CATEGORY_MAP.items() if suffix in exts), "Other")
            folder = base / category
            if not dry_run:
                folder.mkdir(exist_ok=True)
                dest = folder / item.name
                if dest.exists():
                    dest = folder / f"{item.stem}_{int(time.time())}{item.suffix}"
                shutil.move(str(item), str(dest))
            moved += 1
        verb = "Would organise" if dry_run else "Organised"
        return f"{verb} {moved} files in {base.name}, Sir."
    except Exception as exc:
        return f"I could not organise that folder, Sir. {exc}"


def disk_usage() -> str:
    try:
        usage = shutil.disk_usage(str(HOME.anchor))
        free = usage.free / 1e9
        total = usage.total / 1e9
        return f"Disk has {free:.0f} gigabytes free of {total:.0f}, Sir."
    except Exception as exc:
        return f"I could not read the disk usage, Sir. {exc}"


def find_by_content(text: str, location: str | None = None, limit: int = 8) -> str:
    """Search inside text-like files for a phrase."""
    needle = (text or "").lower().strip()
    if not needle:
        return "What phrase should I search for, Sir?"
    root = resolve_location(location) if location else LOCATIONS["documents"]
    allowed = {".txt", ".md", ".csv", ".py", ".js", ".json", ".html", ".log", ".ini"}
    hits: list[str] = []
    for path in _walk(root, limit_seconds=8):
        if path.suffix.lower() not in allowed:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if needle in content.lower():
            idx = content.lower().find(needle)
            snippet = re.sub(r"\s+", " ", content[max(0, idx - 60): idx + 90])
            hits.append(f"{path.name}: ...{snippet}...")
            if len(hits) >= limit:
                break
    if not hits:
        return f"No documents contained {text}, Sir."
    return f"Found {len(hits)} matches: " + " | ".join(hits)
