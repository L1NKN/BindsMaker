"""Desktop app (tkinter): suggest, check, record and save keybinds."""

from __future__ import annotations

import sys

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on the Python install
    tk = None

from . import __version__, live, mybinds
from .db import PLATFORMS, ShortcutDB, current_platform
from .detect import running_process_names
from .export import export
from .keys import KEY_GROUPS, Combo, ComboError, normalize_key
from .report import check_report, short_reasons
from .suggest import DEFAULT_FAMILIES, DEFAULT_KEY_GROUPS, alternatives, evaluate, suggest

_MODIFIER_KEYSYMS = {
    "Control_L": "Ctrl", "Control_R": "Ctrl",
    "Alt_L": "Alt", "Alt_R": "Alt", "Meta_L": "Alt", "Meta_R": "Alt", "ISO_Level3_Shift": "Alt",
    "Shift_L": "Shift", "Shift_R": "Shift",
    "Super_L": "Win", "Super_R": "Win", "Win_L": "Win", "Win_R": "Win", "Hyper_L": "Win",
}

# Tk reports the shifted symbol when Shift is held; map back to the physical key.
_KEYSYM_TO_KEY = {
    "exclam": "1", "at": "2", "numbersign": "3", "dollar": "4", "percent": "5",
    "asciicircum": "6", "ampersand": "7", "asterisk": "8", "parenleft": "9", "parenright": "0",
    "underscore": "-", "plus": "=", "braceleft": "[", "braceright": "]", "bar": "\\",
    "colon": ";", "quotedbl": "'", "less": ",", "greater": ".", "question": "/",
    "asciitilde": "`", "minus": "-", "equal": "=", "bracketleft": "[", "bracketright": "]",
    "backslash": "\\", "semicolon": ";", "apostrophe": "'", "comma": ",", "period": ".",
    "slash": "/", "grave": "`", "ISO_Left_Tab": "Tab", "Return": "Enter", "Escape": "Esc",
    "space": "Space", "BackSpace": "Backspace", "Print": "PrintScreen", "Prior": "PageUp",
    "Next": "PageDown", "App": "Menu", "Menu": "Menu", "Scroll_Lock": "ScrollLock",
    "Caps_Lock": "CapsLock", "KP_Add": "NumPlus", "KP_Subtract": "NumMinus",
    "KP_Multiply": "NumMultiply", "KP_Divide": "NumDivide", "KP_Decimal": "NumDecimal",
}


def keysym_to_key(keysym: str) -> str:
    if keysym in _KEYSYM_TO_KEY:
        return _KEYSYM_TO_KEY[keysym]
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return f"Num{keysym[3:]}"
    return normalize_key(keysym)


class BindsMakerApp:
    def __init__(self, root):
        self.root = root
        root.title(f"BindsMaker {__version__}")
        root.geometry("940x640")
        root.minsize(760, 520)

        self.platform = tk.StringVar(value=current_platform())
        self.running_only = tk.BooleanVar(value=False)
        live_ok, live_reason = live.check_available()
        self.live_reason = live_reason
        self.use_live = tk.BooleanVar(value=live_ok)
        self._db = None
        self._suggestions = []
        self._recording = False
        self._held = set()

        self._build_settings(live_ok)
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.notebook = nb
        self.tab_suggest = ttk.Frame(nb, padding=8)
        self.tab_check = ttk.Frame(nb, padding=8)
        self.tab_mine = ttk.Frame(nb, padding=8)
        self.tab_db = ttk.Frame(nb, padding=8)
        nb.add(self.tab_suggest, text="Suggest")
        nb.add(self.tab_check, text="Check a combo")
        nb.add(self.tab_mine, text="My binds")
        nb.add(self.tab_db, text="Shortcut database")
        self._build_suggest()
        self._build_check()
        self._build_mine()
        self._build_db()
        self.refresh_mine()

    # -- shared ---------------------------------------------------------------

    def _build_settings(self, live_ok):
        bar = ttk.Frame(self.root, padding=(8, 8, 8, 4))
        bar.pack(fill="x")
        ttk.Label(bar, text="Platform").pack(side="left")
        box = ttk.Combobox(bar, textvariable=self.platform, values=PLATFORMS, width=9, state="readonly")
        box.pack(side="left", padx=(4, 12))
        box.bind("<<ComboboxSelected>>", lambda _e: self.invalidate())
        ttk.Checkbutton(bar, text="Only apps running now", variable=self.running_only,
                        command=self.invalidate).pack(side="left", padx=(0, 12))
        cb = ttk.Checkbutton(bar, text="Live system check", variable=self.use_live)
        cb.pack(side="left")
        if not live_ok:
            cb.state(["disabled"])
            ttk.Label(bar, text=f"({self.live_reason})", foreground="gray").pack(side="left", padx=4)

    def invalidate(self):
        self._db = None
        self.refresh_db_tab()

    def db(self) -> ShortcutDB:
        if self._db is None:
            running = running_process_names() if self.running_only.get() else None
            self._db = ShortcutDB.load().filtered(platform=self.platform.get(), running=running)
        return self._db

    def live_check(self):
        return live.is_taken if self.use_live.get() else None

    # -- suggest tab ----------------------------------------------------------

    def _build_suggest(self):
        t = self.tab_suggest
        row = ttk.Frame(t)
        row.pack(fill="x")
        ttk.Label(row, text="What is the keybind for?").pack(side="left")
        self.purpose = tk.StringVar(value="")
        entry = ttk.Entry(row, textvariable=self.purpose, width=40)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _e: self.run_suggest())
        ttk.Label(row, text="How many").pack(side="left", padx=(12, 4))
        self.count = tk.IntVar(value=15)
        ttk.Spinbox(row, from_=1, to=100, textvariable=self.count, width=5).pack(side="left")
        ttk.Button(row, text="Suggest", command=self.run_suggest).pack(side="left", padx=8)

        fams = ttk.LabelFrame(t, text="Modifier families", padding=6)
        fams.pack(fill="x", pady=(8, 4))
        self.family_vars = {}
        for i, fam in enumerate(DEFAULT_FAMILIES + ("Win+Ctrl+Alt+Shift", "Ctrl", "Alt", "")):
            var = tk.BooleanVar(value=fam in DEFAULT_FAMILIES)
            self.family_vars[fam] = var
            ttk.Checkbutton(fams, text=fam or "No modifier", variable=var).grid(
                row=i // 5, column=i % 5, sticky="w", padx=4)

        keys = ttk.LabelFrame(t, text="Keys", padding=6)
        keys.pack(fill="x", pady=4)
        self.key_vars = {}
        labels = {"extended": "F13-F24 (macro keys)", "function": "F1-F12"}
        for i, group in enumerate(KEY_GROUPS):
            var = tk.BooleanVar(value=group in DEFAULT_KEY_GROUPS)
            self.key_vars[group] = var
            ttk.Checkbutton(keys, text=labels.get(group, group.capitalize()), variable=var).grid(
                row=0, column=i, sticky="w", padx=4)
        self.allow_conflicts = tk.BooleanVar(value=False)
        ttk.Checkbutton(keys, text="Also show combos used inside other apps",
                        variable=self.allow_conflicts).grid(row=1, column=0, columnspan=4, sticky="w", padx=4)

        self.sugg_tree = self._tree(t, (("combo", "Combo", 170), ("score", "Score", 60),
                                        ("why", "Why", 560)))
        self.sugg_tree.bind("<Double-1>", lambda _e: self.check_selected_suggestion())
        btns = ttk.Frame(t)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Check selected", command=self.check_selected_suggestion).pack(side="left")
        ttk.Button(btns, text="Save selected to My binds...",
                   command=self.reserve_selected_suggestion).pack(side="left", padx=6)
        self.sugg_status = ttk.Label(btns, text="", foreground="gray")
        self.sugg_status.pack(side="left", padx=8)

    def _tree(self, parent, columns, height=12):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings",
                            height=height, selectmode="browse")
        for cid, title, width in columns:
            tree.heading(cid, text=title)
            tree.column(cid, width=width, stretch=cid == columns[-1][0])
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def run_suggest(self):
        families = [f for f, v in self.family_vars.items() if v.get()]
        groups = [g for g, v in self.key_vars.items() if v.get()]
        if not families or not groups:
            messagebox.showinfo("BindsMaker", "Pick at least one modifier family and one key group.")
            return
        try:
            count = max(1, int(self.count.get()))
        except (tk.TclError, ValueError):
            count = 15
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            self._suggestions = suggest(self.db(), self.purpose.get().strip(), count,
                                        families=families, key_groups=groups,
                                        allow_conflicts=self.allow_conflicts.get(),
                                        live_check=self.live_check())
        finally:
            self.root.config(cursor="")
        self.sugg_tree.delete(*self.sugg_tree.get_children())
        for i, ev in enumerate(self._suggestions):
            self.sugg_tree.insert("", "end", iid=str(i), values=(str(ev.combo), ev.score, short_reasons(ev)))
        if self._suggestions:
            self.sugg_tree.selection_set("0")
        checked = f"{len(self.db().apps)} apps checked" + (", live-checked" if self.live_check() else "")
        self.sugg_status.config(text=f"{len(self._suggestions)} suggestions ({checked})")

    def _selected_suggestion(self):
        sel = self.sugg_tree.selection()
        if not sel:
            messagebox.showinfo("BindsMaker", "Select a suggestion first.")
            return None
        return self._suggestions[int(sel[0])].combo

    def check_selected_suggestion(self):
        combo = self._selected_suggestion()
        if combo:
            self.combo_text.set(str(combo))
            self.notebook.select(self.tab_check)
            self.run_check()

    def reserve_selected_suggestion(self):
        combo = self._selected_suggestion()
        if combo:
            self.edit_bind_dialog(str(combo), self.purpose.get().strip())

    # -- check tab ------------------------------------------------------------

    def _build_check(self):
        t = self.tab_check
        row = ttk.Frame(t)
        row.pack(fill="x")
        ttk.Label(row, text="Key combo").pack(side="left")
        self.combo_text = tk.StringVar(value="Ctrl+Shift+R")
        entry = ttk.Entry(row, textvariable=self.combo_text, width=28)
        entry.pack(side="left", padx=6)
        entry.bind("<Return>", lambda _e: self.run_check())
        self.record_btn = ttk.Button(row, text="Record...", command=self.start_recording)
        self.record_btn.pack(side="left")
        ttk.Button(row, text="Check", command=self.run_check).pack(side="left", padx=6)
        ttk.Button(row, text="Save to My binds...",
                   command=lambda: self.edit_bind_dialog(self.combo_text.get(), self.purpose.get().strip())
                   ).pack(side="left")
        self.record_hint = ttk.Label(t, text="Type a combo like Ctrl+Alt+Shift+R, or press Record and hold the keys.",
                                     foreground="gray")
        self.record_hint.pack(fill="x", pady=(6, 0))
        frame = ttk.Frame(t)
        frame.pack(fill="both", expand=True, pady=(6, 0))
        self.check_out = tk.Text(frame, wrap="none", font="TkFixedFont", height=20)
        sy = ttk.Scrollbar(frame, orient="vertical", command=self.check_out.yview)
        sx = ttk.Scrollbar(frame, orient="horizontal", command=self.check_out.xview)
        self.check_out.configure(yscrollcommand=sy.set, xscrollcommand=sx.set, state="disabled")
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self.check_out.pack(side="left", fill="both", expand=True)

    def run_check(self):
        try:
            combo = Combo.parse(self.combo_text.get())
        except ComboError as exc:
            self._show_check(f"Can't read that combo: {exc}\n")
            return
        self.combo_text.set(str(combo))
        purpose = self.purpose.get().strip()
        ev = evaluate(combo, self.db(), purpose)
        result = live.check(combo) if self.use_live.get() else None
        alts = []
        if ev.conflicts or ev.blocked or (result and result.taken):
            alts = alternatives(combo, self.db(), purpose, live_check=self.live_check())
        self._show_check(check_report(ev, result, alts, purpose))

    def _show_check(self, text):
        self.check_out.configure(state="normal")
        self.check_out.delete("1.0", "end")
        self.check_out.insert("1.0", text)
        self.check_out.configure(state="disabled")

    def start_recording(self):
        self._recording = True
        self._held = set()
        self.record_btn.config(text="Press keys...")
        self.record_hint.config(text="Hold the modifiers and press the key (Esc cancels). If nothing happens, "
                                     "another program has grabbed that combo - which is itself a conflict!")
        self.root.bind_all("<KeyPress>", self._on_key_press)
        self.root.bind_all("<KeyRelease>", self._on_key_release)
        self.root.focus_force()

    def _stop_recording(self):
        self._recording = False
        self.root.unbind_all("<KeyPress>")
        self.root.unbind_all("<KeyRelease>")
        self.record_btn.config(text="Record...")
        self.record_hint.config(text="Type a combo like Ctrl+Alt+Shift+R, or press Record and hold the keys.")

    def _on_key_press(self, event):
        if not self._recording:
            return None
        mod = _MODIFIER_KEYSYMS.get(event.keysym)
        if mod:
            self._held.add(mod)
            self.combo_text.set("+".join(m for m in ("Win", "Ctrl", "Alt", "Shift") if m in self._held) + "+...")
            return "break"
        if event.keysym == "Escape" and not self._held:
            self._stop_recording()
            return "break"
        try:
            key = keysym_to_key(event.keysym)
        except ComboError:
            self.record_hint.config(text=f"Unsupported key {event.keysym!r} - try another.")
            return "break"
        combo = Combo(frozenset(self._held), key)
        self._stop_recording()
        self.combo_text.set(str(combo))
        self.run_check()
        return "break"

    def _on_key_release(self, event):
        mod = _MODIFIER_KEYSYMS.get(event.keysym)
        if mod:
            self._held.discard(mod)
        return "break" if self._recording else None

    # -- my binds tab ---------------------------------------------------------

    def _build_mine(self):
        t = self.tab_mine
        ttk.Label(t, text="Binds you've claimed. Suggestions and checks always treat these as taken.",
                  foreground="gray").pack(fill="x")
        self.mine_tree = self._tree(t, (("combo", "Combo", 170), ("label", "What it does", 240),
                                        ("command", "Command", 420)))
        self.mine_tree.bind("<Double-1>", lambda _e: self.edit_selected_bind())
        btns = ttk.Frame(t)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Add...", command=lambda: self.edit_bind_dialog("", "")).pack(side="left")
        ttk.Button(btns, text="Edit...", command=self.edit_selected_bind).pack(side="left", padx=6)
        ttk.Button(btns, text="Remove", command=self.remove_selected_bind).pack(side="left")
        ttk.Button(btns, text="Export xbindkeys...",
                   command=lambda: self.export_binds("xbindkeys")).pack(side="right")
        ttk.Button(btns, text="Export AutoHotkey script...",
                   command=lambda: self.export_binds("ahk")).pack(side="right", padx=6)
        self.mine_path = ttk.Label(t, text="", foreground="gray")
        self.mine_path.pack(fill="x", pady=(6, 0))

    def refresh_mine(self):
        self.mine_tree.delete(*self.mine_tree.get_children())
        for b in mybinds.load_binds():
            self.mine_tree.insert("", "end", iid=b["combo"],
                                  values=(b["combo"], b.get("label", ""), b.get("command", "")))
        self.mine_path.config(text=f"Saved in {mybinds.binds_path()}")

    def edit_selected_bind(self):
        sel = self.mine_tree.selection()
        if sel:
            combo, label, command = self.mine_tree.item(sel[0], "values")
            self.edit_bind_dialog(combo, label, command, replacing=combo)

    def remove_selected_bind(self):
        sel = self.mine_tree.selection()
        if sel and messagebox.askyesno("BindsMaker", f"Remove {sel[0]} from your binds?"):
            mybinds.release(Combo.parse(sel[0]))
            self.refresh_mine()
            self.invalidate()

    def edit_bind_dialog(self, combo_text, label="", command="", replacing=None):
        win = tk.Toplevel(self.root)
        win.title("Save keybind")
        win.transient(self.root)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=12)
        frm.pack(fill="both", expand=True)
        vars_ = {}
        for i, (name, title, value) in enumerate((("combo", "Key combo", combo_text),
                                                  ("label", "What it does", label),
                                                  ("command", "Command to run (optional)", command))):
            ttk.Label(frm, text=title).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=value)
            ttk.Entry(frm, textvariable=var, width=48).grid(row=i, column=1, sticky="we", pady=3, padx=(8, 0))
            vars_[name] = var
        ttk.Label(frm, text="The command is used when you export an AutoHotkey / xbindkeys script.",
                  foreground="gray").grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 8))

        def save():
            try:
                combo = Combo.parse(vars_["combo"].get())
            except ComboError as exc:
                messagebox.showerror("BindsMaker", f"Can't read that combo: {exc}", parent=win)
                return
            others = [c for c in self.db().conflicts(combo) if c.app_id != "my-binds"]
            if others:
                names = "\n".join(f"  {c.app_name}: {c.action}" for c in others[:8])
                if not messagebox.askyesno("BindsMaker", f"{combo} is already used by:\n{names}\n\nSave anyway?",
                                           parent=win):
                    return
            if replacing and replacing != str(combo):
                mybinds.release(Combo.parse(replacing))
            mybinds.reserve(combo, vars_["label"].get().strip(), vars_["command"].get().strip())
            win.destroy()
            self.refresh_mine()
            self.invalidate()
            self.notebook.select(self.tab_mine)

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(btns, text="Save", command=save).pack(side="right", padx=6)
        win.bind("<Return>", lambda _e: save())
        win.bind("<Escape>", lambda _e: win.destroy())
        win.grab_set()

    def export_binds(self, fmt):
        binds = mybinds.load_binds()
        if not binds:
            messagebox.showinfo("BindsMaker", "Save some binds first.")
            return
        ext = ".ahk" if fmt == "ahk" else ".xbindkeysrc"
        path = filedialog.asksaveasfilename(defaultextension=ext, initialfile=f"mybinds{ext}",
                                            filetypes=[("Script", f"*{ext}"), ("All files", "*")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(export(binds, fmt))
            messagebox.showinfo("BindsMaker", f"Wrote {len(binds)} bind(s) to\n{path}")

    # -- database tab ---------------------------------------------------------

    def _build_db(self):
        t = self.tab_db
        panes = ttk.PanedWindow(t, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=1)
        panes.add(right, weight=2)
        self.apps_tree = self._tree(left, (("name", "App", 220), ("category", "Category", 90),
                                           ("count", "#", 40)))
        self.apps_tree.bind("<<TreeviewSelect>>", lambda _e: self.show_app())
        self.app_sc_tree = self._tree(right, (("combo", "Combo", 170), ("scope", "Scope", 90),
                                              ("action", "Action", 300)))
        self.app_notes = ttk.Label(right, text="", foreground="gray", wraplength=520)
        self.app_notes.pack(fill="x", pady=(6, 0))
        self.refresh_db_tab()

    def refresh_db_tab(self):
        if not hasattr(self, "apps_tree"):
            return
        self.apps_tree.delete(*self.apps_tree.get_children())
        for app in sorted(self.db().apps, key=lambda a: (a.category, a.name)):
            self.apps_tree.insert("", "end", iid=app.id, values=(app.name, app.category, len(app.shortcuts)))
        self.app_sc_tree.delete(*self.app_sc_tree.get_children())
        self.app_notes.config(text="")

    def show_app(self):
        sel = self.apps_tree.selection()
        if not sel:
            return
        app = self.db().app(sel[0])
        self.app_sc_tree.delete(*self.app_sc_tree.get_children())
        for i, sc in enumerate(sorted(app.shortcuts, key=lambda s: s.combo.sort_key())):
            self.app_sc_tree.insert("", "end", iid=str(i), values=(
                str(sc.combo), "system-wide" if sc.is_global else "in app", sc.action))
        self.app_notes.config(text=app.notes)


def main():
    if tk is None:
        print("The GUI needs tkinter, which this Python install doesn't have.\n"
              "Use the command line instead (bindsmaker --help), or install tkinter "
              "(e.g. `sudo apt install python3-tk`).", file=sys.stderr)
        sys.exit(1)
    root = tk.Tk()
    BindsMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
