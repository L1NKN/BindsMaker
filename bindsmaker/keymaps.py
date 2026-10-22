"""Translate key names into Windows virtual-key codes, X11 keysyms and AutoHotkey names."""

from __future__ import annotations

from .keys import Combo

# Punctuation is mapped by physical (US) position, matching how keys.py treats it.
_VK_SPECIAL = {
    "Esc": 0x1B, "Tab": 0x09, "Space": 0x20, "Enter": 0x0D, "Backspace": 0x08,
    "PrintScreen": 0x2C, "Pause": 0x13, "ScrollLock": 0x91, "CapsLock": 0x14, "Menu": 0x5D,
    "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "NumMultiply": 0x6A, "NumPlus": 0x6B, "NumMinus": 0x6D, "NumDecimal": 0x6E, "NumDivide": 0x6F,
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF, "`": 0xC0,
    "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}

_X11_SPECIAL = {
    "Esc": "Escape", "Tab": "Tab", "Space": "space", "Enter": "Return", "Backspace": "BackSpace",
    "PrintScreen": "Print", "Pause": "Pause", "ScrollLock": "Scroll_Lock", "CapsLock": "Caps_Lock",
    "Menu": "Menu", "Insert": "Insert", "Delete": "Delete", "Home": "Home", "End": "End",
    "PageUp": "Prior", "PageDown": "Next", "Left": "Left", "Up": "Up", "Right": "Right", "Down": "Down",
    "NumMultiply": "KP_Multiply", "NumPlus": "KP_Add", "NumMinus": "KP_Subtract",
    "NumDecimal": "KP_Decimal", "NumDivide": "KP_Divide",
    ";": "semicolon", "=": "equal", ",": "comma", "-": "minus", ".": "period", "/": "slash",
    "`": "grave", "[": "bracketleft", "\\": "backslash", "]": "bracketright", "'": "apostrophe",
}

# AutoHotkey: scan codes for punctuation avoid escaping problems (` and ; are special in AHK).
_AHK_SPECIAL = {
    "Esc": "Esc", "Tab": "Tab", "Space": "Space", "Enter": "Enter", "Backspace": "Backspace",
    "PrintScreen": "PrintScreen", "Pause": "Pause", "ScrollLock": "ScrollLock",
    "CapsLock": "CapsLock", "Menu": "AppsKey", "Insert": "Ins", "Delete": "Del", "Home": "Home",
    "End": "End", "PageUp": "PgUp", "PageDown": "PgDn", "Left": "Left", "Up": "Up",
    "Right": "Right", "Down": "Down", "NumMultiply": "NumpadMult", "NumPlus": "NumpadAdd",
    "NumMinus": "NumpadSub", "NumDecimal": "NumpadDot", "NumDivide": "NumpadDiv",
    "`": "SC029", "-": "SC00C", "=": "SC00D", "[": "SC01A", "]": "SC01B", "\\": "SC02B",
    ";": "SC027", "'": "SC028", ",": "SC033", ".": "SC034", "/": "SC035",
}

AHK_MODIFIERS = {"Win": "#", "Ctrl": "^", "Alt": "!", "Shift": "+"}
WIN_MODIFIERS = {"Alt": 0x0001, "Ctrl": 0x0002, "Shift": 0x0004, "Win": 0x0008}
X11_MODIFIERS = {"Shift": 1 << 0, "Ctrl": 1 << 2, "Alt": 1 << 3, "Win": 1 << 6}
XBINDKEYS_MODIFIERS = {"Win": "Mod4", "Ctrl": "Control", "Alt": "Mod1", "Shift": "Shift"}


def _numpad_digit(key: str):
    if key.startswith("Num") and key[3:].isdigit():
        return int(key[3:])
    return None


def vk_code(key: str) -> int:
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        return ord(key.upper())
    if key.startswith("F") and key[1:].isdigit():
        return 0x70 + int(key[1:]) - 1
    digit = _numpad_digit(key)
    if digit is not None:
        return 0x60 + digit
    return _VK_SPECIAL[key]


def x11_keysym_name(key: str) -> str:
    if len(key) == 1 and key.isalpha():
        return key.lower()
    if len(key) == 1 and key.isdigit():
        return key
    if key.startswith("F") and key[1:].isdigit():
        return key
    digit = _numpad_digit(key)
    if digit is not None:
        return f"KP_{digit}"
    return _X11_SPECIAL[key]


def ahk_hotkey(combo: Combo) -> str:
    mods = "".join(AHK_MODIFIERS[m] for m in ("Win", "Ctrl", "Alt", "Shift") if m in combo.mods)
    key = combo.key
    if len(key) == 1 and key.isalnum():
        name = key.lower()
    elif key.startswith("F") and key[1:].isdigit():
        name = key
    elif _numpad_digit(key) is not None:
        name = f"Numpad{_numpad_digit(key)}"
    else:
        name = _AHK_SPECIAL[key]
    return mods + name


def xbindkeys_keys(combo: Combo) -> str:
    parts = [XBINDKEYS_MODIFIERS[m] for m in ("Win", "Ctrl", "Alt", "Shift") if m in combo.mods]
    return " + ".join(parts + [x11_keysym_name(combo.key)])
