"""Key combo model: parsing, normalising and formatting things like "Ctrl+Shift+R"."""

from __future__ import annotations

import string
from dataclasses import dataclass

# Canonical modifier order used everywhere for display and comparison.
MODIFIERS = ("Win", "Ctrl", "Alt", "Shift")

_MODIFIER_ALIASES = {
    "ctrl": "Ctrl", "control": "Ctrl", "ctl": "Ctrl", "strg": "Ctrl",
    "alt": "Alt", "option": "Alt", "opt": "Alt", "altgr": None,
    "shift": "Shift",
    "win": "Win", "windows": "Win", "super": "Win", "meta": "Win",
    "cmd": "Win", "command": "Win", "logo": "Win",
}

LETTERS = tuple(string.ascii_uppercase)
DIGITS = tuple("0123456789")
FUNCTION_KEYS = tuple(f"F{i}" for i in range(1, 13))
EXTENDED_FUNCTION_KEYS = tuple(f"F{i}" for i in range(13, 25))
PUNCTUATION = ("`", "-", "=", "[", "]", "\\", ";", "'", ",", ".", "/")
NAVIGATION = ("Insert", "Delete", "Home", "End", "PageUp", "PageDown",
              "Up", "Down", "Left", "Right")
NUMPAD = tuple(f"Num{i}" for i in range(10)) + (
    "NumPlus", "NumMinus", "NumMultiply", "NumDivide", "NumDecimal")
SPECIAL = ("Esc", "Tab", "Space", "Enter", "Backspace", "PrintScreen", "Pause",
           "ScrollLock", "CapsLock", "Menu")

ALL_KEYS = (LETTERS + DIGITS + FUNCTION_KEYS + EXTENDED_FUNCTION_KEYS
            + PUNCTUATION + NAVIGATION + NUMPAD + SPECIAL)

_KEY_ALIASES = {
    "esc": "Esc", "escape": "Esc",
    "tab": "Tab",
    "space": "Space", "spacebar": "Space",
    "enter": "Enter", "return": "Enter",
    "backspace": "Backspace", "bksp": "Backspace",
    "printscreen": "PrintScreen", "prtsc": "PrintScreen", "prtscn": "PrintScreen",
    "print": "PrintScreen", "prntscrn": "PrintScreen", "sysrq": "PrintScreen",
    "pause": "Pause", "break": "Pause",
    "scrolllock": "ScrollLock", "capslock": "CapsLock",
    "menu": "Menu", "apps": "Menu", "contextmenu": "Menu",
    "insert": "Insert", "ins": "Insert",
    "delete": "Delete", "del": "Delete",
    "home": "Home", "end": "End",
    "pageup": "PageUp", "pgup": "PageUp", "prior": "PageUp",
    "pagedown": "PageDown", "pgdn": "PageDown", "next": "PageDown",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "uparrow": "Up", "downarrow": "Down", "leftarrow": "Left", "rightarrow": "Right",
    "grave": "`", "backtick": "`", "backquote": "`", "tilde": "`", "~": "`",
    "minus": "-", "hyphen": "-", "dash": "-", "_": "-", "underscore": "-",
    "equals": "=", "equal": "=", "plus": "=", "+": "=",
    "lbracket": "[", "bracketleft": "[", "{": "[",
    "rbracket": "]", "bracketright": "]", "}": "]",
    "backslash": "\\", "|": "\\", "pipe": "\\",
    "semicolon": ";", ":": ";", "colon": ";",
    "quote": "'", "apostrophe": "'", '"': "'",
    "comma": ",", "<": ",", "period": ".", "dot": ".", ">": ".",
    "slash": "/", "?": "/", "question": "/",
    "numadd": "NumPlus", "numplus": "NumPlus", "numsub": "NumMinus",
    "numminus": "NumMinus", "nummult": "NumMultiply", "nummultiply": "NumMultiply",
    "numdiv": "NumDivide", "numdivide": "NumDivide", "numdot": "NumDecimal",
    "numdecimal": "NumDecimal",
}

# Shifted digit symbols on a US layout map back to the physical digit key.
_SHIFTED_DIGITS = dict(zip("!@#$%^&*()", "1234567890"))

KEY_GROUPS = {
    "letters": LETTERS,
    "digits": DIGITS,
    "function": FUNCTION_KEYS,
    "extended": EXTENDED_FUNCTION_KEYS,
    "punctuation": PUNCTUATION,
    "navigation": NAVIGATION,
    "numpad": NUMPAD,
}


class ComboError(ValueError):
    """Raised when a key combo string cannot be understood."""


def normalize_key(name: str) -> str:
    raw = name.strip()
    if not raw:
        raise ComboError("empty key name")
    if len(raw) == 1:
        if raw.isalpha():
            return raw.upper()
        if raw.isdigit() or raw in PUNCTUATION:
            return raw
        if raw in _SHIFTED_DIGITS:
            return _SHIFTED_DIGITS[raw]
    low = raw.lower().replace(" ", "").replace("_", "") if len(raw) > 1 else raw
    if low in _KEY_ALIASES:
        return _KEY_ALIASES[low]
    if low.startswith("f") and low[1:].isdigit() and 1 <= int(low[1:]) <= 24:
        return f"F{int(low[1:])}"
    for prefix in ("numpad", "num", "kp"):
        if low.startswith(prefix) and low[len(prefix):].isdigit() and len(low) == len(prefix) + 1:
            return f"Num{low[-1]}"
    raise ComboError(f"unknown key: {name!r}")


@dataclass(frozen=True, order=False)
class Combo:
    """A modifier set plus one non-modifier key."""

    mods: frozenset
    key: str

    @classmethod
    def parse(cls, text: str) -> "Combo":
        """Parse "ctrl+shift+r", "Win + Alt + F13", "Ctrl++" and similar."""
        if text is None or not text.strip():
            raise ComboError("empty combo")
        cleaned = text.strip()
        parts = [p.strip() for p in cleaned.split("+")]
        # "Ctrl++" / "Ctrl+Shift++" -> trailing empty parts mean the plus key.
        if cleaned.endswith("+"):
            while parts and parts[-1] == "":
                parts.pop()
            parts.append("+")
        if any(p == "" for p in parts):
            raise ComboError(f"malformed combo: {text!r}")
        mods = set()
        key = None
        for part in parts:
            low = part.lower()
            if low in _MODIFIER_ALIASES:
                mod = _MODIFIER_ALIASES[low]
                if mod is None:  # AltGr == Ctrl+Alt on Windows
                    mods.update(("Ctrl", "Alt"))
                else:
                    mods.add(mod)
                continue
            if key is not None:
                raise ComboError(f"more than one non-modifier key in {text!r}")
            key = normalize_key(part)
        if key is None:
            raise ComboError(f"no key in {text!r} (modifier-only combos are not supported)")
        return cls(frozenset(mods), key)

    @property
    def family(self) -> str:
        """The modifier part on its own, e.g. "Ctrl+Alt+Shift" (or "" for a bare key)."""
        return "+".join(m for m in MODIFIERS if m in self.mods)

    def __str__(self) -> str:
        fam = self.family
        return f"{fam}+{self.key}" if fam else self.key

    def sort_key(self):
        return (len(self.mods), self.family, ALL_KEYS.index(self.key) if self.key in ALL_KEYS else 999)


def parse_family(text: str) -> frozenset:
    """Parse a modifier-only string like "Ctrl+Alt+Shift" into a modifier set."""
    if not text.strip():
        return frozenset()
    mods = set()
    for part in text.split("+"):
        low = part.strip().lower()
        if low not in _MODIFIER_ALIASES:
            raise ComboError(f"unknown modifier: {part!r}")
        mod = _MODIFIER_ALIASES[low]
        mods.update(("Ctrl", "Alt") if mod is None else (mod,))
    return frozenset(mods)


def family_name(mods) -> str:
    return "+".join(m for m in MODIFIERS if m in mods)
