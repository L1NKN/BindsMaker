"""Find out which programs are running, so suggestions can focus on apps you actually use."""

from __future__ import annotations

import csv
import io
import os
import subprocess
import sys


def running_process_names() -> set:
    """Lower-case executable names of running processes (best effort, may be empty)."""
    try:
        if sys.platform.startswith("win"):
            return _windows()
        if os.path.isdir("/proc"):
            return _procfs()
        return _ps()
    except (OSError, subprocess.SubprocessError):
        return set()


def _windows() -> set:
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    return {row[0].lower() for row in csv.reader(io.StringIO(out)) if row}


def _procfs() -> set:
    names = set()
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm", encoding="utf-8", errors="replace") as fh:
                names.add(fh.read().strip().lower())
            # comm is truncated to 15 characters, so also use argv[0].
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                argv0 = fh.read().split(b"\0", 1)[0].decode("utf-8", "replace")
            if argv0:
                names.add(os.path.basename(argv0).lower())
        except OSError:
            continue
    return names


def _ps() -> set:
    out = subprocess.run(["ps", "-axo", "comm="], capture_output=True, text=True, check=True).stdout
    return {os.path.basename(line.strip()).lower() for line in out.splitlines() if line.strip()}
