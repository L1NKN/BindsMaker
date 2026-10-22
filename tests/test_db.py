import json

import pytest

from bindsmaker import mybinds
from bindsmaker.db import DataError, ShortcutDB, app_from_dict, load_builtin_apps
from bindsmaker.keys import Combo


def test_builtin_data_loads_and_is_well_formed():
    apps = load_builtin_apps()  # raises on duplicate keys, bad combos, bad fields
    assert len(apps) > 20
    db = ShortcutDB(apps)
    assert len(db) > 500
    for app in apps:
        assert app.platforms, app.id


def test_duplicate_keys_are_rejected(tmp_path):
    folder = tmp_path / "apps"
    folder.mkdir()
    (folder / "x.json").write_text('{"id": "x", "name": "X", "shortcuts": {"Ctrl+Q": "a", "Ctrl+Q": "b"}}')
    with pytest.raises(DataError, match="duplicate"):
        ShortcutDB.load(base=tmp_path)


def test_original_problem_is_detected(tmp_path):
    db = ShortcutDB.load(base=tmp_path).filtered(platform="windows")
    users = {c.app_id for c in db.conflicts(Combo.parse("Ctrl+Shift+R"))}
    assert {"chrome", "firefox", "edge", "vscode"} <= users


def test_platform_filter(tmp_path):
    db = ShortcutDB.load(base=tmp_path)
    combo = Combo.parse("Ctrl+Alt+Shift+R")  # GNOME screen recording
    assert any(c.app_id == "gnome" for c in db.filtered(platform="linux").conflicts(combo))
    assert not db.filtered(platform="windows").conflicts(combo)


def test_running_filter_keeps_always_present_apps(tmp_path):
    db = ShortcutDB.load(base=tmp_path).filtered(platform="windows", running={"discord.exe"})
    ids = {a.id for a in db.apps}
    assert {"windows", "conventions", "discord", "my-binds"} <= ids
    assert "chrome" not in ids


def test_per_shortcut_scope_override():
    app = app_from_dict({"id": "t", "name": "T", "scope": "app",
                         "shortcuts": {"Ctrl+Q": "x", "Win+`": {"action": "y", "scope": "global"}}})
    scopes = {str(s.combo): s.scope for s in app.shortcuts}
    assert scopes == {"Ctrl+Q": "app", "Win+`": "global"}


def test_user_app_files_are_merged(tmp_path):
    folder = tmp_path / "apps"
    folder.mkdir()
    (folder / "mine.json").write_text(json.dumps(
        {"id": "my-game", "name": "My Game", "shortcuts": {"Ctrl+Alt+Shift+K": "Kill feed"}}))
    db = ShortcutDB.load(base=tmp_path)
    assert db.conflicts(Combo.parse("ctrl+alt+shift+k"))[-1].app_id == "my-game"


def test_reserve_and_release(tmp_path):
    combo = Combo.parse("ctrl+alt+shift+r")
    mybinds.reserve(combo, "Change resolution", "qres.exe /x 1920", base=tmp_path)
    mybinds.reserve(Combo.parse("win+alt+shift+b"), "Brightness", base=tmp_path)
    binds = mybinds.load_binds(tmp_path)
    assert [b["combo"] for b in binds] == ["Ctrl+Alt+Shift+R", "Win+Alt+Shift+B"]

    db = ShortcutDB.load(base=tmp_path).filtered(platform="windows")
    (sc,) = db.conflicts(combo)
    assert sc.app_id == "my-binds" and sc.is_global and sc.action == "Change resolution"

    assert mybinds.release(combo, base=tmp_path)
    assert not mybinds.release(combo, base=tmp_path)
    assert [b["combo"] for b in mybinds.load_binds(tmp_path)] == ["Win+Alt+Shift+B"]
