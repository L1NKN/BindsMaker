import pytest

from bindsmaker import mybinds
from bindsmaker.db import ShortcutDB
from bindsmaker.keys import Combo
from bindsmaker.suggest import alternatives, evaluate, purpose_letters, suggest


@pytest.fixture
def db(tmp_path):
    return ShortcutDB.load(base=tmp_path).filtered(platform="windows")


def test_crowded_combo_scores_low(db):
    bad = evaluate(Combo.parse("Ctrl+Shift+R"), db)
    good = evaluate(Combo.parse("Ctrl+Alt+Shift+R"), db)
    assert bad.conflicts and not good.conflicts
    assert bad.score < 20 < 80 < good.score


def test_global_conflicts_block(db):
    ev = evaluate(Combo.parse("Win+Alt+R"), db)  # Xbox Game Bar recording
    assert ev.blocked and ev.score == 0
    assert "Xbox Game Bar" in ev.block_reason


def test_typing_keys_block(db):
    assert evaluate(Combo.parse("Shift+R"), db).blocked
    assert not evaluate(Combo.parse("F13"), db).blocked


def test_altgr_penalty(db):
    plain = evaluate(Combo.parse("Ctrl+Alt+J"), db)
    altgr = evaluate(Combo.parse("Ctrl+Alt+Q"), db)
    assert any("AltGr+Q" in text for _, text in altgr.reasons)
    assert altgr.score < plain.score


def test_purpose_letters():
    bonus = purpose_letters("change the resolution")
    assert bonus["R"] > bonus["C"] > 0
    assert "T" not in bonus


def test_suggestions_are_conflict_free_and_mnemonic(db):
    evs = suggest(db, "change resolution", 10)
    assert len(evs) == 10
    assert all(ev.is_free for ev in evs)
    assert evs[0].combo.key == "R"
    assert evs == sorted(evs, key=lambda e: -e.raw)
    assert len({ev.combo.family for ev in evs}) >= 3  # variety


def test_suggest_respects_live_check_and_exclude(db):
    first = suggest(db, "change resolution", 1)[0].combo
    second = suggest(db, "change resolution", 1, live_check=lambda c: c == first)[0].combo
    third = suggest(db, "change resolution", 1, exclude={first})[0].combo
    assert second != first and third != first


def test_reserved_binds_are_avoided(tmp_path):
    mybinds.reserve(Combo.parse("Ctrl+Alt+Shift+R"), "Resolution", base=tmp_path)
    db = ShortcutDB.load(base=tmp_path).filtered(platform="windows")
    assert evaluate(Combo.parse("Ctrl+Alt+Shift+R"), db).blocked
    assert all(str(ev.combo) != "Ctrl+Alt+Shift+R" for ev in suggest(db, "resolution", 20))


def test_alternatives_keep_the_key(db):
    alts = alternatives(Combo.parse("Ctrl+Shift+R"), db)
    assert alts and all(a.combo.key == "R" and a.is_free for a in alts)


def test_allow_conflicts_includes_in_app_clashes(db):
    evs = suggest(db, count=500, families=["Ctrl+Shift"], keys=list("RTN"), allow_conflicts=True)
    assert {str(e.combo) for e in evs} == {"Ctrl+Shift+R", "Ctrl+Shift+T", "Ctrl+Shift+N"}
