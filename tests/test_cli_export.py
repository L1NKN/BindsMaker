import pytest

from bindsmaker import mybinds
from bindsmaker.cli import main
from bindsmaker.resolution import Resolution, ResolutionError
from bindsmaker.export import to_ahk, to_xbindkeys


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BINDSMAKER_HOME", str(tmp_path))
    return tmp_path


def test_check_reports_conflicts(capsys):
    assert main(["check", "ctrl+shift+r", "--platform", "windows", "--no-live"]) == 0
    out = capsys.readouterr().out
    assert "Google Chrome" in out and "Hard reload" in out
    assert "Try instead" in out and "Ctrl+Alt+Shift+R" in out


def test_check_blocked_exit_code(capsys):
    assert main(["check", "win+l", "--platform", "windows", "--no-live"]) == 1
    assert "BLOCKED" in capsys.readouterr().out


def test_bad_combo_exit_code(capsys):
    assert main(["check", "ctrl+banana", "--no-live"]) == 2
    assert "unknown key" in capsys.readouterr().err


def test_suggest(capsys):
    assert main(["suggest", "change", "resolution", "-n", "5", "--platform", "windows", "--no-live"]) == 0
    out = capsys.readouterr().out
    assert "Ctrl+Alt+Shift+R" in out
    assert "bindsmaker reserve" in out


def test_reserve_flow(capsys, tmp_path):
    assert main(["reserve", "ctrl+shift+r", "--platform", "windows"]) == 1  # clashes
    assert main(["reserve", "ctrl+alt+shift+r", "-l", "Change resolution", "--platform", "windows"]) == 0
    assert main(["reserve", "ctrl+alt+shift+r", "-l", "Other", "--platform", "windows"]) == 1  # already mine
    assert main(["mine"]) == 0
    assert "Change resolution" in capsys.readouterr().out
    out_file = tmp_path / "binds.ahk"
    assert main(["export", "--format", "ahk", "-o", str(out_file)]) == 0
    assert "^!+r::" in out_file.read_text()
    assert main(["release", "ctrl+alt+shift+r"]) == 0
    assert main(["export"]) == 1


def test_apps_and_show(capsys):
    assert main(["apps", "--platform", "windows"]) == 0
    assert "chrome" in capsys.readouterr().out
    assert main(["show", "chrome"]) == 0
    assert "Hard reload" in capsys.readouterr().out
    assert main(["show", "nope"]) == 1


def test_ahk_export_escapes_quotes():
    text = to_ahk([{"combo": "Ctrl+Alt+Shift+R", "label": "Res",
                    "command": 'C:\\Tools\\QRes.exe /x:1920 /y:"1080"'}])
    assert '#Requires AutoHotkey v2.0' in text
    assert '^!+r::' in text
    assert 'Run("C:\\Tools\\QRes.exe /x:1920 /y:`"1080`"")' in text


def test_xbindkeys_export():
    text = to_xbindkeys([{"combo": "Win+Alt+Shift+R", "label": "Res", "command": "xrandr -s 1920x1080"}])
    assert '"xrandr -s 1920x1080"' in text
    assert "Mod4 + Mod1 + Shift + r" in text


def test_two_normal_keys_explains_itself(capsys):
    assert main(["check", "b+shift+f3", "--no-live"]) == 2
    assert "F13-F24" in capsys.readouterr().err


def test_random(capsys):
    assert main(["random", "-n", "4", "--seed", "3", "--platform", "windows", "--no-live"]) == 0
    out = capsys.readouterr().out
    assert "Random free keybinds" in out and out.count("\n  ") >= 5


def test_resolutions_flow(capsys, tmp_path):
    out_file = tmp_path / "res.ahk"
    args = ["resolutions", "1920x1080", "2560x1440@144", "--platform", "windows", "--no-live", "--seed", "7"]
    assert main(args + ["-o", str(out_file)]) == 0
    first = capsys.readouterr().out
    script = out_file.read_text()
    assert "ChangeResolution(1920, 1080)" in script
    assert "ChangeResolution(2560, 1440, 144)" in script
    assert script.count("ChangeResolution(width, height, hz := 0)") == 1
    binds = {b["resolution"]: b["combo"] for b in mybinds.load_binds()}
    assert set(binds) == {"1920x1080", "2560x1440@144"}
    assert len(set(binds.values())) == 2
    # Running again keeps the existing binds; --reroll replaces them.
    assert main(args) == 0
    assert "(kept)" in capsys.readouterr().out
    assert main(args + ["--reroll", "--seed", "8"]) == 0
    assert len(mybinds.load_binds()) == 2
    assert "(new)" in capsys.readouterr().out and first


def test_reserve_with_resolution(capsys):
    assert main(["reserve", "ctrl+alt+shift+f17", "--resolution", "1280x720", "--platform", "windows"]) == 0
    (bind,) = mybinds.load_binds()
    assert bind == {"combo": "Ctrl+Alt+Shift+F17", "label": "Resolution 1280x720", "resolution": "1280x720"}
    assert main(["reserve", "ctrl+alt+shift+f18", "--resolution", "huge", "--platform", "windows"]) == 2


def test_resolution_parsing():
    assert str(Resolution.parse("1920 x 1080")) == "1920x1080"
    assert str(Resolution.parse("2560x1440@144Hz")) == "2560x1440@144"
    with pytest.raises(ResolutionError):
        Resolution.parse("1080p")
