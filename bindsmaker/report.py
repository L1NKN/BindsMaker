"""Plain-text reports shared by the CLI and the GUI."""

from __future__ import annotations

_POPULARITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _table(rows, indent="  "):
    if not rows:
        return []
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]) - 1)]
    out = []
    for row in rows:
        cells = [str(c).ljust(w) for c, w in zip(row, widths)] + [str(row[-1])]
        out.append(indent + "  ".join(cells).rstrip())
    return out


def status_line(ev, live=None) -> str:
    if ev.blocked:
        return f"BLOCKED - {ev.block_reason}"
    if live is not None and live.taken:
        return "TAKEN - a running program has already grabbed it"
    if ev.conflicts:
        apps = {c.app_id for c in ev.conflicts}
        return f"clashes with {len(apps)} app{'s' if len(apps) != 1 else ''}"
    return "no known conflicts"


def short_reasons(ev, limit: int = 2) -> str:
    ranked = sorted(ev.reasons, key=lambda r: (r[0] < 0, -abs(r[0])))
    return "; ".join(text for _, text in ranked[:limit])


def check_report(ev, live=None, alternatives=(), purpose: str = "") -> str:
    lines = [f"{ev.combo}   score {ev.score}/100   {status_line(ev, live)}", ""]
    if ev.conflicts:
        lines.append("Already used by")
        ordered = sorted(ev.conflicts,
                         key=lambda c: (not c.is_global, _POPULARITY_RANK[c.popularity], c.app_name))
        rows = [(c.app_name, c.category, "system-wide" if c.is_global else "in app", c.action)
                for c in ordered]
        lines += _table(rows)
        lines.append("")
    if live is not None:
        lines.append(f"Live system check ({live.method or 'n/a'}): {live.status.upper()} - {live.detail}")
        lines.append("")
    if ev.reasons:
        rows = []
        if ev.conflict_reasons:
            total = sum(d for d, _ in ev.reasons[:ev.conflict_reasons])
            rows.append((f"{total:+d}", f"clashes with {ev.conflict_reasons} app(s) listed above"))
        rows += [(f"{d:+d}", t) for d, t in ev.reasons[ev.conflict_reasons:]]
        lines.append("Score breakdown")
        lines += _table(rows)
        lines.append("")
    if alternatives:
        lines.append(f"Try instead (same key, no known conflicts{', for “' + purpose + '”' if purpose else ''})")
        lines += _table([(str(a.combo), f"{a.score}/100", short_reasons(a, 1)) for a in alternatives])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def suggestions_report(evs, purpose: str = "", context: str = "") -> str:
    head = "Suggested keybinds"
    if purpose:
        head += f" for “{purpose}”"
    lines = [head + (f"  ({context})" if context else ""), ""]
    if not evs:
        lines.append("  Nothing left - try more modifier families or key groups.")
        return "\n".join(lines) + "\n"
    rows = [("#", "Combo", "Score", "Why")]
    rows += [(str(i), str(ev.combo), str(ev.score), short_reasons(ev)) for i, ev in enumerate(evs, 1)]
    lines += _table(rows)
    return "\n".join(lines) + "\n"
