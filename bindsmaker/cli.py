"""Command-line interface: `bindsmaker check|suggest|random|resolutions|reserve|release|mine|export|apps|show|gui`."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from . import __version__, live, mybinds
from .db import PLATFORMS, DataError, ShortcutDB, config_dir, current_platform
from .detect import running_process_names
from .export import FORMATS, export
from .keys import KEY_GROUPS, Combo, ComboError, normalize_key
from .report import check_report, suggestions_report
from .resolution import Resolution, ResolutionError
from .suggest import (
    DEFAULT_FAMILIES, DEFAULT_KEY_GROUPS, MACRO_FAMILIES, MACRO_KEY_GROUPS, alternatives, evaluate,
    pick_random, suggest,
)


def _split(values):
    out = []
    for value in values or ():
        out.extend(v.strip() for v in value.split(",") if v.strip())
    return out


def _add_scope_args(p):
    p.add_argument("--platform", choices=PLATFORMS, default=None,
                   help="platform whose shortcuts to consider (default: this computer's)")
    p.add_argument("--apps", action="append", metavar="ID[,ID...]",
                   help="only consider these apps (plus the OS and your own binds); see `bindsmaker apps`")
    p.add_argument("--running", action="store_true",
                   help="only consider apps that are running right now")
    p.add_argument("--no-live", action="store_true",
                   help="skip asking the OS whether a program has grabbed the combo")


def _load_db(args) -> ShortcutDB:
    platform = args.platform or current_platform()
    if platform == "macos":
        print("note: the database does not cover macOS yet; only your own binds are checked.",
              file=sys.stderr)
    running = running_process_names() if getattr(args, "running", False) else None
    return ShortcutDB.load().filtered(platform=platform, app_ids=_split(args.apps) or None,
                                      running=running)


def _live_enabled(args) -> bool:
    return not args.no_live and live.check_available()[0]


def cmd_check(args):
    db = _load_db(args)
    combo = Combo.parse(args.combo)
    purpose = " ".join(args.purpose or [])
    ev = evaluate(combo, db, purpose)
    use_live = _live_enabled(args)
    result = live.check(combo) if use_live else None
    alts = []
    if ev.conflicts or ev.blocked or (result and result.taken):
        alts = alternatives(combo, db, purpose, live_check=live.is_taken if use_live else None)
    print(check_report(ev, result, alts, purpose), end="")
    return 1 if (ev.blocked or (result and result.taken)) else 0


def cmd_suggest(args):
    db = _load_db(args)
    purpose = " ".join(args.purpose or [])
    use_live = _live_enabled(args)
    taken = {Combo.parse(t) for t in _split(args.avoid)}
    evs = suggest(db, purpose, args.count,
                  families=_split(args.families) or None,
                  key_groups=_split(args.keys) or None,
                  keys=[normalize_key(k) for k in _split(args.key)] or None,
                  allow_conflicts=args.allow_conflicts, exclude=taken,
                  live_check=live.is_taken if use_live else None, macro=args.macro)
    context = f"{args.platform or current_platform()}, {len(db.apps)} apps checked"
    if args.macro:
        context += ", macro mode"
    if use_live:
        context += ", live-checked"
    print(suggestions_report(evs, purpose, context), end="")
    if evs:
        print(f"\nSave one with:  bindsmaker reserve \"{evs[0].combo}\" --label \"{purpose or 'my action'}\"")
    return 0


def cmd_reserve(args):
    combo = Combo.parse(args.combo)
    existing = {b["combo"]: b for b in mybinds.load_binds()}
    db = ShortcutDB.load().filtered(platform=args.platform or current_platform())
    others = [c for c in db.conflicts(combo) if c.app_id != "my-binds"]
    if others and not args.force:
        print(f"{combo} is already used by:")
        for c in others:
            print(f"  {c.app_name}: {c.action}")
        print("Use --force to reserve it anyway.")
        return 1
    if str(combo) in existing and not args.force:
        print(f"{combo} is already reserved for “{existing[str(combo)].get('label', '')}”. "
              "Use --force to replace it.")
        return 1
    resolution = str(Resolution.parse(args.resolution)) if args.resolution else ""
    label = args.label or (f"Resolution {resolution}" if resolution else "")
    mybinds.reserve(combo, label, args.command or "", resolution=resolution)
    print(f"Reserved {combo}" + (f" for “{label}”" if label else "")
          + f"  (saved in {mybinds.binds_path()})")
    return 0


def _random_args(args):
    return dict(families=_split(args.families) or None, key_groups=_split(args.keys) or None,
                rng=random.Random(args.seed))


def cmd_random(args):
    db = _load_db(args)
    use_live = _live_enabled(args)
    evs = pick_random(db, args.count, live_check=live.is_taken if use_live else None,
                      macro=not args.by_hand, **_random_args(args))
    evs.sort(key=lambda e: -e.raw)
    context = f"{args.platform or current_platform()}, {len(db.apps)} apps checked"
    if use_live:
        context += ", live-checked"
    print(suggestions_report(evs, "", context).replace("Suggested keybinds", "Random free keybinds", 1), end="")
    if evs:
        print(f"\nSave one with:  bindsmaker reserve \"{evs[0].combo}\" --label \"my action\"")
    return 0


def cmd_resolutions(args):
    """One random, conflict-free bind per resolution, saved and ready for a Stream Deck."""
    wanted = [Resolution.parse(r) for r in _split(args.resolutions)]
    db = _load_db(args)
    use_live = _live_enabled(args)
    by_res = {b["resolution"]: b for b in mybinds.load_binds() if b.get("resolution")}
    rows = []
    for res in wanted:
        existing = by_res.get(str(res))
        if existing and not args.reroll:
            rows.append((str(res), existing["combo"], "kept"))
            continue
        if existing:
            mybinds.release(Combo.parse(existing["combo"]))
            db = _load_db(args)
        picks = pick_random(db, 1, live_check=live.is_taken if use_live else None, **_random_args(args))
        if not picks:
            print("Ran out of free combos - allow more key groups with --keys.", file=sys.stderr)
            return 1
        combo = picks[0].combo
        mybinds.reserve(combo, f"Resolution {res}", resolution=str(res))
        db = _load_db(args)  # so the next resolution can't get the same combo
        rows.append((str(res), str(combo), "new"))

    width = max(len(r[0]) for r in rows)
    cwidth = max(len(r[1]) for r in rows)
    print("Resolution binds (put each combo on a Stream Deck button with the Hotkey action)\n")
    for res, combo, state in rows:
        print(f"  {res.ljust(width)}  ->  {combo.ljust(cwidth)}  ({state})")
    fmt = args.format or ("ahk" if (args.platform or current_platform()) == "windows" else "xbindkeys")
    if args.output:
        binds = mybinds.load_binds()
        Path(args.output).write_text(export(binds, fmt), encoding="utf-8")
        print(f"\nWrote all {len(binds)} of your binds to {args.output}"
              + (" - double-click it (needs AutoHotkey v2) and leave it running." if fmt == "ahk" else "."))
    else:
        print("\nNext: bindsmaker export -o mybinds.ahk   (then double-click mybinds.ahk)")
    return 0


def cmd_release(args):
    combo = Combo.parse(args.combo)
    if mybinds.release(combo):
        print(f"Released {combo}")
        return 0
    print(f"{combo} was not reserved")
    return 1


def cmd_mine(args):
    binds = mybinds.load_binds()
    if not binds:
        print("No binds reserved yet. Try: bindsmaker suggest change resolution")
        return 0
    width = max(len(b["combo"]) for b in binds)
    for b in binds:
        actions = [f"resolution {b['resolution']}"] if b.get("resolution") and \
            b["resolution"] not in b.get("label", "") else []
        actions += [b["command"]] if b.get("command") else []
        extra = f"   -> {'; '.join(actions)}" if actions else ""
        print(f"  {b['combo'].ljust(width)}  {b.get('label', '')}{extra}")
    print(f"\n({mybinds.binds_path()})")
    return 0


def cmd_export(args):
    binds = mybinds.load_binds()
    if not binds:
        print("No binds reserved yet - nothing to export.", file=sys.stderr)
        return 1
    fmt = args.format or ("ahk" if current_platform() == "windows" else "xbindkeys")
    text = export(binds, fmt)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(binds)} bind(s) to {args.output}")
    else:
        print(text)
    return 0


def cmd_apps(args):
    db = ShortcutDB.load()
    platform = args.platform
    rows = []
    for app in sorted(db.apps, key=lambda a: (a.category, a.name)):
        if platform and platform not in app.platforms:
            continue
        rows.append((app.id, app.name, app.category, app.scope, str(len(app.shortcuts)),
                     ",".join(app.platforms)))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    for r in rows:
        print("  " + "  ".join(c.ljust(w) for c, w in zip(r, widths)) + "  " + r[5])
    print(f"\n{len(rows)} apps. Add your own as JSON files in {config_dir() / 'apps'}")
    return 0


def cmd_show(args):
    db = ShortcutDB.load()
    app = db.app(args.app_id)
    if not app:
        print(f"No app with id {args.app_id!r}; see `bindsmaker apps`.")
        return 1
    print(f"{app.name}  [{app.category}, {app.scope}, {', '.join(app.platforms)}]")
    if app.notes:
        print(app.notes)
    print()
    shortcuts = sorted(app.shortcuts, key=lambda s: s.combo.sort_key())
    width = max((len(str(s.combo)) for s in shortcuts), default=0)
    for sc in shortcuts:
        flag = "  (system-wide)" if sc.is_global and app.scope != "global" else ""
        print(f"  {str(sc.combo).ljust(width)}  {sc.action}{flag}")
    return 0


def cmd_gui(_args):
    from .gui import main as gui_main
    gui_main()
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="bindsmaker",
        description="Find keyboard shortcuts that no other app is using.",
        epilog="Examples:\n"
               "  bindsmaker check ctrl+shift+r\n"
               "  bindsmaker suggest change resolution\n"
               "  bindsmaker random -n 5\n"
               "  bindsmaker resolutions 1920x1080 2560x1440@144 -o resolutions.ahk\n"
               "  bindsmaker reserve ctrl+alt+shift+r --label \"Change resolution\"\n"
               "  bindsmaker export -o mybinds.ahk",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"bindsmaker {__version__}")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("check", help="see what a combo clashes with")
    c.add_argument("combo", help='e.g. "Ctrl+Shift+R"')
    c.add_argument("purpose", nargs="*", help="what the bind is for (improves the alternatives)")
    _add_scope_args(c)
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("suggest", help="suggest uncommon, conflict-free combos")
    s.add_argument("purpose", nargs="*", help='what the bind is for, e.g. "change resolution"')
    s.add_argument("-n", "--count", type=int, default=10)
    s.add_argument("--families", action="append", metavar="MODS[,MODS...]",
                   help=f"modifier families to try (default: {', '.join(DEFAULT_FAMILIES)})")
    s.add_argument("--keys", action="append", metavar="GROUP[,GROUP...]",
                   help=f"key groups: {', '.join(KEY_GROUPS)} (default: {', '.join(DEFAULT_KEY_GROUPS)})")
    s.add_argument("--key", action="append", metavar="KEY", help="only these keys, e.g. --key R")
    s.add_argument("--avoid", action="append", metavar="COMBO", help="extra combos to stay away from")
    s.add_argument("--allow-conflicts", action="store_true",
                   help="also show combos used inside other apps (ranked lower)")
    s.add_argument("--macro", action="store_true",
                   help="for a Stream Deck / macro pad: ignore how hard a combo is to press")
    _add_scope_args(s)
    s.set_defaults(func=cmd_suggest)

    def add_random_args(p):
        p.add_argument("--families", action="append", metavar="MODS[,MODS...]",
                       help=f"modifier families to pick from (default: {', '.join(MACRO_FAMILIES[:-1])}, none)")
        p.add_argument("--keys", action="append", metavar="GROUP[,GROUP...]",
                       help=f"key groups: {', '.join(KEY_GROUPS)} (default: {', '.join(MACRO_KEY_GROUPS)})")
        p.add_argument("--seed", type=int, help="repeatable randomness")
        _add_scope_args(p)

    rd = sub.add_parser("random", help="random uncommon combos, made for a Stream Deck / macro pad")
    rd.add_argument("-n", "--count", type=int, default=5)
    rd.add_argument("--by-hand", action="store_true", help="you'll press it yourself: keep it comfortable")
    add_random_args(rd)
    rd.set_defaults(func=cmd_random)

    rs = sub.add_parser("resolutions", help="one random bind per screen resolution, saved to My binds")
    rs.add_argument("resolutions", nargs="+", help="e.g. 1920x1080 2560x1440@144 1280x720")
    rs.add_argument("-o", "--output", help="also write a script with all your binds (e.g. resolutions.ahk)")
    rs.add_argument("--format", choices=FORMATS, help="default: ahk on Windows, xbindkeys elsewhere")
    rs.add_argument("--reroll", action="store_true", help="pick new combos even if a resolution has one")
    add_random_args(rs)
    rs.set_defaults(func=cmd_resolutions)

    r = sub.add_parser("reserve", help="save a combo as one of your binds")
    r.add_argument("combo")
    r.add_argument("-l", "--label", help="what it does")
    r.add_argument("-c", "--command", help="command to run (used by `export`)")
    r.add_argument("-r", "--resolution", help="switch to this resolution, e.g. 1920x1080@144 (used by `export`)")
    r.add_argument("-f", "--force", action="store_true", help="reserve even if it clashes")
    r.add_argument("--platform", choices=PLATFORMS, default=None)
    r.set_defaults(func=cmd_reserve)

    rl = sub.add_parser("release", help="forget one of your binds")
    rl.add_argument("combo")
    rl.set_defaults(func=cmd_release)

    m = sub.add_parser("mine", help="list your reserved binds")
    m.set_defaults(func=cmd_mine)

    e = sub.add_parser("export", help="write your binds as an AutoHotkey or xbindkeys script")
    e.add_argument("--format", choices=FORMATS, help="default: ahk on Windows, xbindkeys elsewhere")
    e.add_argument("-o", "--output", help="file to write (default: print)")
    e.set_defaults(func=cmd_export)

    a = sub.add_parser("apps", help="list the apps in the shortcut database")
    a.add_argument("--platform", choices=PLATFORMS)
    a.set_defaults(func=cmd_apps)

    sh = sub.add_parser("show", help="list one app's shortcuts")
    sh.add_argument("app_id")
    sh.set_defaults(func=cmd_show)

    g = sub.add_parser("gui", help="open the graphical app")
    g.set_defaults(func=cmd_gui)
    return p


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except (ComboError, DataError, ResolutionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
