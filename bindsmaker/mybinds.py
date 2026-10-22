"""The user's own reserved binds, stored in <config dir>/my_binds.json."""

from __future__ import annotations

import json
from pathlib import Path

from .keys import Combo

FILENAME = "my_binds.json"


def binds_path(base: Path = None) -> Path:
    from .db import config_dir
    return (base or config_dir()) / FILENAME


def load_binds(base: Path = None) -> list:
    path = binds_path(base)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    binds = data.get("binds", []) if isinstance(data, dict) else data
    return [dict(b, combo=str(Combo.parse(b["combo"]))) for b in binds]


def save_binds(binds: list, base: Path = None) -> Path:
    path = binds_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"binds": binds}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def reserve(combo: Combo, label: str = "", command: str = "", base: Path = None) -> list:
    """Add or update a bind. Returns the new list."""
    binds = [b for b in load_binds(base) if b["combo"] != str(combo)]
    entry = {"combo": str(combo), "label": label}
    if command:
        entry["command"] = command
    binds.append(entry)
    binds.sort(key=lambda b: Combo.parse(b["combo"]).sort_key())
    save_binds(binds, base)
    return binds


def release(combo: Combo, base: Path = None) -> bool:
    """Remove a bind. Returns False if it wasn't reserved."""
    binds = load_binds(base)
    kept = [b for b in binds if b["combo"] != str(combo)]
    if len(kept) == len(binds):
        return False
    save_binds(kept, base)
    return True
