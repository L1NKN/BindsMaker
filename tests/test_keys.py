import pytest

from bindsmaker.keymaps import ahk_hotkey, vk_code, x11_keysym_name, xbindkeys_keys
from bindsmaker.keys import ALL_KEYS, Combo, ComboError, parse_family


@pytest.mark.parametrize("text, expected", [
    ("ctrl+shift+r", "Ctrl+Shift+R"),
    ("Shift + CTRL + r", "Ctrl+Shift+R"),
    ("win+alt+f13", "Win+Alt+F13"),
    ("super+ctrl+alt+shift+x", "Win+Ctrl+Alt+Shift+X"),
    ("Ctrl++", "Ctrl+="),
    ("Ctrl+Plus", "Ctrl+="),
    ("ctrl+shift+!", "Ctrl+Shift+1"),
    ("alt+prtsc", "Alt+PrintScreen"),
    ("ctrl+numpad5", "Ctrl+Num5"),
    ("AltGr+e", "Ctrl+Alt+E"),
    ("ctrl+pgdn", "Ctrl+PageDown"),
    ("F7", "F7"),
])
def test_parse_and_format(text, expected):
    assert str(Combo.parse(text)) == expected


def test_order_independent_equality():
    assert Combo.parse("Shift+Ctrl+R") == Combo.parse("ctrl+shift+r")


@pytest.mark.parametrize("bad", ["", "ctrl+shift", "ctrl+a+b", "ctrl+banana", "ctrl++a"])
def test_parse_errors(bad):
    with pytest.raises(ComboError):
        Combo.parse(bad)


def test_family():
    assert parse_family("Win+Alt") == frozenset({"Win", "Alt"})
    assert Combo.parse("alt+win+r").family == "Win+Alt"


@pytest.mark.parametrize("key", ALL_KEYS)
def test_every_key_maps_everywhere(key):
    combo = Combo(frozenset({"Ctrl", "Alt"}), key)
    assert vk_code(key) > 0
    assert x11_keysym_name(key)
    assert ahk_hotkey(combo).startswith("^!")
    assert xbindkeys_keys(combo).startswith("Control + Mod1 + ")


def test_ahk_names():
    assert ahk_hotkey(Combo.parse("ctrl+alt+shift+r")) == "^!+r"
    assert ahk_hotkey(Combo.parse("win+;")) == "#SC027"
    assert ahk_hotkey(Combo.parse("win+ctrl+f13")) == "#^F13"
