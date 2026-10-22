"""Score key combos and suggest ones that nothing else is likely to be using."""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field

from .keys import (
    EXTENDED_FUNCTION_KEYS, FUNCTION_KEYS, KEY_GROUPS, LETTERS, DIGITS, NAVIGATION, NUMPAD,
    PUNCTUATION, Combo, parse_family,
)

# How likely an unknown app is to use a modifier family, as a score penalty.
# Single modifiers and Ctrl+Shift are crowded; three-modifier families are rarely used.
FAMILY_RISK = {parse_family(name): risk for name, risk in {
    "": 35, "Ctrl": 40, "Alt": 35, "Shift": 40, "Win": 35,
    "Ctrl+Shift": 25, "Ctrl+Alt": 18, "Alt+Shift": 15,
    "Win+Shift": 15, "Win+Ctrl": 15, "Win+Alt": 10,
    "Ctrl+Alt+Shift": 4, "Win+Ctrl+Shift": 4, "Win+Alt+Shift": 2, "Win+Ctrl+Alt": 4,
    "Win+Ctrl+Alt+Shift": 6,
}.items()}

# Families tried by default, roughly from "least likely to clash" to "most crowded".
DEFAULT_FAMILIES = (
    "Ctrl+Alt+Shift", "Win+Alt+Shift", "Win+Ctrl+Alt", "Win+Ctrl+Shift",
    "Win+Alt", "Alt+Shift", "Win+Ctrl", "Win+Shift", "Ctrl+Alt", "Ctrl+Shift",
)

DEFAULT_KEY_GROUPS = ("letters", "digits", "function")

# Macro mode (Stream Deck, macro pad, mouse buttons): a device presses the keys, so
# awkward combos are fine and F13-F24 - which no normal keyboard has - are ideal.
MACRO_FAMILIES = (
    "Ctrl+Alt+Shift", "Win+Alt+Shift", "Win+Ctrl+Alt", "Win+Ctrl+Shift", "Win+Ctrl+Alt+Shift",
    "Ctrl+Shift", "Ctrl+Alt", "Alt+Shift", "Win+Alt", "Win+Ctrl", "Win+Shift",
    "Ctrl", "Alt", "Shift", "",
)
MACRO_KEY_GROUPS = ("extended", "function", "letters", "digits")

CONFLICT_PENALTY = {"high": 30, "medium": 20, "low": 10}

# Keys reachable by the left hand while it holds the left-side modifiers (QWERTY).
LEFT_HAND = set("QWERTASDFGZXCVB12345`") | {"F1", "F2", "F3", "F4", "F5", "Esc", "Tab"}
CENTRE = set("YHN67") | {"F6", "F7", "F8"}

# Characters typed with AltGr (= Ctrl+Alt on Windows) on common non-US layouts.
ALTGR_CHARS = {
    "Q": "@ (German)", "E": "€ (most European layouts)", "M": "µ (German)",
    "A": "ą (Polish)", "C": "ć (Polish)", "L": "ł (Polish)", "N": "ń (Polish)",
    "O": "ó (Polish)", "S": "ś (Polish)", "X": "ź (Polish)", "Z": "ż (Polish)",
    "1": "| (Spanish)", "2": "@ / ² (Spanish, German)", "3": "# / ³ (Spanish, French, German)",
    "4": "~ / { (Spanish, French)", "5": "[ (French)", "6": "| (French)",
    "7": "{ (German)", "8": "[ (German)", "9": "] (German)", "0": "} / @ (German, French)",
    "-": "\\ (German)", "=": "~ (German)",
}

STOPWORDS = {"the", "a", "an", "to", "for", "of", "and", "or", "my", "on", "off", "in", "with", "it"}
# Generic verbs: a key matching them is a weaker mnemonic than one matching the noun.
WEAK_WORDS = {"change", "toggle", "switch", "open", "start", "stop", "launch", "run", "show",
              "hide", "set", "turn", "enable", "disable", "go", "next", "previous", "quick"}


@dataclass
class Evaluation:
    combo: Combo
    score: int  # 0-100 for display
    conflicts: list
    reasons: list = field(default_factory=list)  # (delta, text)
    blocked: bool = False
    block_reason: str = ""
    raw: float = 0.0  # unclamped score, used for ranking
    conflict_reasons: int = 0  # the first N reasons are per-app conflicts

    @property
    def global_conflicts(self):
        return [c for c in self.conflicts if c.is_global]

    @property
    def app_conflicts(self):
        return [c for c in self.conflicts if not c.is_global]

    @property
    def is_free(self) -> bool:
        return not self.conflicts and not self.blocked


def purpose_letters(purpose: str) -> dict:
    """Map candidate keys to a mnemonic bonus for a description like "change resolution"."""
    bonus = {}
    if not purpose:
        return bonus
    for word in re.findall(r"[A-Za-z0-9]+", purpose.lower()):
        if word in STOPWORDS:
            continue
        first = word[0].upper()
        value = 4 if word in WEAK_WORDS else 10
        bonus[first] = max(bonus.get(first, 0), value)
    return bonus


def typing_key(combo: Combo) -> bool:
    """True if pressing the combo would normally type a character (so it can't be a hotkey)."""
    typable = combo.key in LETTERS or combo.key in DIGITS or combo.key in PUNCTUATION or combo.key == "Space"
    return typable and combo.mods <= {"Shift"}


def evaluate(combo: Combo, db, purpose: str = "", mnemonic: dict = None,
             macro: bool = False) -> Evaluation:
    """Score a combo. macro=True skips the "hard to press" penalties (a device presses it)."""
    conflicts = db.conflicts(combo)
    reasons = []
    score = 100.0
    ev = Evaluation(combo, 0, conflicts, reasons)

    if typing_key(combo):
        ev.blocked = True
        ev.block_reason = "types a character - add Ctrl, Alt or Win"
    elif ev.global_conflicts:
        ev.blocked = True
        names = ", ".join(sorted({c.app_name for c in ev.global_conflicts}))
        ev.block_reason = f"already a system-wide shortcut ({names})"

    seen_apps = set()
    for sc in conflicts:
        if sc.app_id in seen_apps:
            continue
        seen_apps.add(sc.app_id)
        penalty = 60 if sc.is_global else CONFLICT_PENALTY[sc.popularity]
        reasons.append((-penalty, f"used by {sc.app_name}: {sc.action}"))
    ev.conflict_reasons = len(reasons)

    fam = combo.family or "bare key"
    risk = FAMILY_RISK.get(combo.mods, 10)
    if combo.key in EXTENDED_FUNCTION_KEYS:
        risk = round(risk * 0.3)
    if risk >= 25:
        reasons.append((-risk, f"{fam} combos are very common in apps"))
    elif risk >= 15:
        reasons.append((-risk, f"{fam} combos are common in apps"))
    elif risk >= 8:
        reasons.append((-risk, f"{fam} combos are sometimes used by apps"))
    elif risk:
        reasons.append((-risk, f"{fam} combos are rarely used by apps"))

    n_mods = len(combo.mods)
    if macro:
        pass
    elif n_mods == 3:
        reasons.append((-3, "three modifiers - slightly harder to press"))
    elif n_mods == 4:
        reasons.append((-10, "four modifiers - awkward to press"))

    key = combo.key
    if key in EXTENDED_FUNCTION_KEYS:
        if macro:
            reasons.append((5, f"{key} has no physical key, so it can't be pressed by accident"))
        else:
            reasons.append((-5, f"{key} needs a macro key, mouse button or remap "
                                "(no physical key on most keyboards)"))
    elif key in PUNCTUATION:
        reasons.append((-6, "punctuation keys move around on non-US layouts"))
    elif key in NAVIGATION:
        reasons.append((-5, "navigation keys are used for text and window movement"))
    elif key in NUMPAD:
        if not macro:
            reasons.append((-8, "many laptops and compact keyboards have no numpad"))
    elif key in DIGITS or key in FUNCTION_KEYS:
        if not macro:
            reasons.append((-2, "digit / function row is a longer reach"))
    elif key not in LETTERS:
        reasons.append((-8, f"{key} is a special key most apps react to"))

    if not macro and (key in LETTERS or key in DIGITS or key in FUNCTION_KEYS or key in PUNCTUATION):
        if key in CENTRE:
            reasons.append((-1, "centre of the keyboard"))
        elif key not in LEFT_HAND:
            reasons.append((-3, "needs two hands"))

    if "Win" in combo.mods and not macro:
        reasons.append((-4, "gaming keyboards often disable the Win key in game mode"))

    if combo.mods == {"Ctrl", "Alt"}:
        reasons.append((-12, "Ctrl+Alt is AltGr on many European layouts"))
        if key in ALTGR_CHARS:
            reasons.append((-10, f"AltGr+{key} types {ALTGR_CHARS[key]}"))
    elif combo.mods == {"Ctrl", "Alt", "Shift"} and key in ALTGR_CHARS and key in LETTERS:
        reasons.append((-2, f"AltGr+Shift+{key} types a capital letter on some layouts"))

    bonus = (mnemonic if mnemonic is not None else purpose_letters(purpose)).get(key, 0)
    if bonus:
        reasons.append((bonus, f"{key} is easy to remember for “{purpose}”" if purpose else f"{key} is mnemonic"))

    score += sum(delta for delta, _ in reasons)
    ev.raw = score
    ev.score = 0 if ev.blocked else int(max(0, min(100, round(score))))
    return ev


def candidates(families=None, key_groups=None, keys=None):
    fams = [parse_family(f) if isinstance(f, str) else frozenset(f)
            for f in (families or DEFAULT_FAMILIES)]
    if keys:
        key_list = list(keys)
    else:
        key_list = []
        for group in key_groups or DEFAULT_KEY_GROUPS:
            key_list.extend(KEY_GROUPS[group])
    seen = set()
    for mods in fams:
        for key in key_list:
            combo = Combo(mods, key)
            if combo not in seen:
                seen.add(combo)
                yield combo


def _pool(db, purpose, families, key_groups, keys, allow_conflicts, exclude, macro):
    if macro:
        families = families or MACRO_FAMILIES
        key_groups = key_groups or MACRO_KEY_GROUPS
    mnemonic = purpose_letters(purpose)
    excluded = set(exclude)
    pool = []
    for combo in candidates(families, key_groups, keys):
        if combo in excluded:
            continue
        ev = evaluate(combo, db, purpose, mnemonic, macro=macro)
        if ev.blocked or (ev.conflicts and not allow_conflicts):
            continue
        pool.append(ev)
    pool.sort(key=lambda e: (-e.raw, e.combo.sort_key()))
    return pool


def suggest(db, purpose: str = "", count: int = 10, families=None, key_groups=None, keys=None,
            allow_conflicts: bool = False, exclude=(), live_check=None, macro: bool = False) -> list:
    """Return the best `count` evaluations.

    live_check -- optional callable(Combo) -> bool returning True if the combo is
                  currently grabbed by another program; those are skipped.
    macro      -- the combo will be sent by a Stream Deck / macro pad, not typed by hand.
    """
    pool = _pool(db, purpose, families, key_groups, keys, allow_conflicts, exclude, macro)

    # Keep the list varied: cap how many suggestions share one modifier family.
    cap = max(2, math.ceil(count / 3))
    chosen, spill, per_family = [], [], {}
    for ev in pool:
        if len(chosen) >= count:
            break
        if live_check is not None and live_check(ev.combo):
            continue
        fam = ev.combo.family
        if per_family.get(fam, 0) >= cap:
            spill.append(ev)
            continue
        per_family[fam] = per_family.get(fam, 0) + 1
        chosen.append(ev)
    for ev in spill:
        if len(chosen) >= count:
            break
        chosen.append(ev)
    chosen.sort(key=lambda e: (-e.raw, e.combo.sort_key()))
    return chosen


def alternatives(combo: Combo, db, purpose: str = "", count: int = 3, live_check=None) -> list:
    """Conflict-free combos that keep the same key but use different modifiers."""
    fams = [f for f in DEFAULT_FAMILIES if parse_family(f) != combo.mods]
    return suggest(db, purpose, count, families=fams, keys=[combo.key], live_check=live_check)


def pick_random(db, count: int = 1, families=None, key_groups=None, keys=None, exclude=(),
                live_check=None, macro: bool = True, rng=None, spread: int = 10) -> list:
    """Pick `count` different random combos from the best conflict-free ones.

    Only combos scoring within `spread` points of the best candidate are eligible,
    so "random" never means "worse".
    """
    rng = rng or random.Random()
    pool = _pool(db, "", families, key_groups, keys, False, exclude, macro)
    if not pool:
        return []
    best = pool[0].raw
    eligible = [ev for ev in pool if ev.raw >= best - spread]
    if len(eligible) < count * 3:  # widen the net rather than run dry
        eligible = pool
    rng.shuffle(eligible)
    chosen = []
    for ev in eligible:
        if len(chosen) >= count:
            break
        if live_check is not None and live_check(ev.combo):
            continue
        chosen.append(ev)
    return chosen
