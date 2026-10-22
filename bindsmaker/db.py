"""Shortcut database: built-in app data, user-supplied app files and the user's own binds."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .keys import Combo, ComboError

PLATFORMS = ("windows", "linux", "macos")
SCOPES = ("global", "app")
POPULARITY = ("high", "medium", "low")
MY_BINDS_ID = "my-binds"


class DataError(ValueError):
    """Raised for malformed shortcut data files."""


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def config_dir() -> Path:
    """Where user data lives. Override with the BINDSMAKER_HOME environment variable."""
    override = os.environ.get("BINDSMAKER_HOME")
    if override:
        return Path(override)
    if current_platform() == "windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "BindsMaker"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "bindsmaker"


@dataclass(frozen=True)
class Shortcut:
    combo: Combo
    action: str
    app_id: str
    app_name: str
    category: str
    popularity: str
    scope: str

    @property
    def is_global(self) -> bool:
        return self.scope == "global"


@dataclass
class App:
    id: str
    name: str
    category: str
    popularity: str
    scope: str
    platforms: tuple
    processes: tuple = ()
    notes: str = ""
    source: str = "builtin"
    shortcuts: list = field(default_factory=list)

    @property
    def always_present(self) -> bool:
        """Apps without process names (the OS, conventions, your own binds) are always considered."""
        return not self.processes


def _reject_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise DataError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _load_json(text: str, source: str):
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates)
    except (json.JSONDecodeError, DataError) as exc:
        raise DataError(f"{source}: {exc}") from exc


def app_from_dict(raw: dict, source: str = "builtin") -> App:
    where = f"{source}:{raw.get('id', '?')}"
    try:
        app_id = raw["id"]
        name = raw["name"]
    except KeyError as exc:
        raise DataError(f"{where}: missing field {exc}") from exc
    category = raw.get("category", "other")
    popularity = raw.get("popularity", "medium")
    scope = raw.get("scope", "app")
    platforms = tuple(raw.get("platforms", PLATFORMS))
    if popularity not in POPULARITY:
        raise DataError(f"{where}: popularity must be one of {POPULARITY}")
    if scope not in SCOPES:
        raise DataError(f"{where}: scope must be one of {SCOPES}")
    for plat in platforms:
        if plat not in PLATFORMS:
            raise DataError(f"{where}: unknown platform {plat!r}")
    app = App(
        id=app_id, name=name, category=category, popularity=popularity, scope=scope,
        platforms=platforms,
        processes=tuple(p.lower() for p in raw.get("processes", ())),
        notes=raw.get("notes", ""), source=source,
    )
    for combo_text, value in raw.get("shortcuts", {}).items():
        if isinstance(value, dict):
            action = value.get("action", "")
            sc_scope = value.get("scope", scope)
        else:
            action, sc_scope = value, scope
        if sc_scope not in SCOPES:
            raise DataError(f"{where}: {combo_text}: scope must be one of {SCOPES}")
        try:
            combo = Combo.parse(combo_text)
        except ComboError as exc:
            raise DataError(f"{where}: {exc}") from exc
        app.shortcuts.append(Shortcut(combo, action, app.id, app.name, category, popularity, sc_scope))
    return app


def _apps_from_json(text: str, source: str) -> list:
    data = _load_json(text, source)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise DataError(f"{source}: expected an app object or a list of apps")
    return [app_from_dict(item, source) for item in data]


def load_builtin_apps() -> list:
    apps = []
    data_dir = resources.files("bindsmaker") / "data"
    for entry in sorted(data_dir.iterdir(), key=lambda p: p.name):
        if entry.name.endswith(".json"):
            apps.extend(_apps_from_json(entry.read_text(encoding="utf-8"), f"data/{entry.name}"))
    return apps


def load_user_apps(base: Path = None) -> list:
    """Extra app files dropped into <config dir>/apps/*.json (same format as the built-in data)."""
    folder = (base or config_dir()) / "apps"
    apps = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            apps.extend(_apps_from_json(path.read_text(encoding="utf-8"), str(path)))
    return apps


def my_binds_app(binds: list) -> App:
    app = App(id=MY_BINDS_ID, name="My binds", category="mine", popularity="high",
              scope="global", platforms=PLATFORMS, source="my_binds.json")
    for bind in binds:
        app.shortcuts.append(Shortcut(Combo.parse(bind["combo"]), bind.get("label", ""),
                                      app.id, app.name, app.category, app.popularity, "global"))
    return app


class ShortcutDB:
    def __init__(self, apps: list):
        ids = [a.id for a in apps]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise DataError(f"duplicate app id(s): {', '.join(sorted(dupes))}")
        self.apps = list(apps)
        self._index = {}
        for app in self.apps:
            for sc in app.shortcuts:
                self._index.setdefault(sc.combo, []).append(sc)

    @classmethod
    def load(cls, include_user: bool = True, base: Path = None) -> "ShortcutDB":
        apps = load_builtin_apps()
        if include_user:
            from .mybinds import load_binds
            apps.extend(load_user_apps(base))
            apps.append(my_binds_app(load_binds(base)))
        return cls(apps)

    def app(self, app_id: str):
        for app in self.apps:
            if app.id == app_id:
                return app
        return None

    def filtered(self, platform: str = None, app_ids=None, running=None) -> "ShortcutDB":
        """Narrow the database.

        platform -- keep apps that exist on this platform.
        app_ids  -- keep only these apps (plus always-present ones like the OS).
        running  -- set of lower-case process names; keep apps that are running
                    (plus always-present ones).
        """
        keep = []
        wanted = {a.lower() for a in app_ids} if app_ids else None
        for app in self.apps:
            if platform and platform not in app.platforms:
                continue
            if wanted is not None and app.id not in wanted and not app.always_present:
                continue
            if running is not None and not app.always_present and not (set(app.processes) & running):
                continue
            keep.append(app)
        return ShortcutDB(keep)

    def conflicts(self, combo: Combo) -> list:
        return list(self._index.get(combo, ()))

    def taken_combos(self):
        return set(self._index)

    def __len__(self):
        return sum(len(a.shortcuts) for a in self.apps)
