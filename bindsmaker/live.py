"""Ask the operating system whether another program has already grabbed a hotkey.

Windows: tries RegisterHotKey and releases it straight away. Failure with
ERROR_HOTKEY_ALREADY_REGISTERED means some running program owns the combo.

Linux (X11): tries XGrabKey on the root window. A BadAccess error means
another client (usually the desktop environment) has grabbed it.

Neither method can see shortcuts that only work inside a focused app, or
programs that read the keyboard through low-level hooks - that is what the
shortcut database is for.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from dataclasses import dataclass

from .keymaps import WIN_MODIFIERS, X11_MODIFIERS, vk_code, x11_keysym_name
from .keys import Combo

FREE, TAKEN, UNKNOWN, UNSUPPORTED = "free", "taken", "unknown", "unsupported"


@dataclass
class LiveResult:
    status: str
    detail: str
    method: str = ""

    @property
    def taken(self) -> bool:
        return self.status == TAKEN


def check(combo: Combo) -> LiveResult:
    if sys.platform.startswith("win"):
        return _check_windows(combo)
    if sys.platform.startswith("linux"):
        return _check_x11(combo)
    return LiveResult(UNSUPPORTED, "live checking is only available on Windows and Linux (X11)")


def check_available():
    """(available, reason) without touching any hotkeys."""
    if sys.platform.startswith("win"):
        return True, "Windows RegisterHotKey"
    if sys.platform.startswith("linux"):
        if os.environ.get("XDG_SESSION_TYPE") == "wayland" or (
                os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DISPLAY")):
            return False, "Wayland does not let apps inspect global shortcuts"
        if not os.environ.get("DISPLAY"):
            return False, "no X11 display"
        if not ctypes.util.find_library("X11"):
            return False, "libX11 not found"
        return True, "X11 XGrabKey"
    return False, "unsupported platform"


def is_taken(combo: Combo) -> bool:
    """Convenience predicate for suggest(live_check=...)."""
    return check(combo).taken


# --- Windows ---------------------------------------------------------------

_ERROR_HOTKEY_ALREADY_REGISTERED = 1409
_MOD_NOREPEAT = 0x4000
_HOTKEY_ID = 0xB1D5  # any id in 0x0000-0xBFFF is fine for an application


def _check_windows(combo: Combo) -> LiveResult:
    method = "Windows RegisterHotKey"
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
    except (AttributeError, OSError) as exc:
        return LiveResult(UNKNOWN, f"could not load user32: {exc}", method)
    try:
        vk = vk_code(combo.key)
    except KeyError:
        return LiveResult(UNKNOWN, f"no virtual-key code for {combo.key}", method)
    mods = _MOD_NOREPEAT
    for mod in combo.mods:
        mods |= WIN_MODIFIERS[mod]
    if user32.RegisterHotKey(None, _HOTKEY_ID, mods, vk):
        user32.UnregisterHotKey(None, _HOTKEY_ID)
        return LiveResult(FREE, "no running program has registered it as a global hotkey", method)
    err = ctypes.get_last_error()
    if err == _ERROR_HOTKEY_ALREADY_REGISTERED:
        return LiveResult(TAKEN, "a running program has already registered it as a global hotkey", method)
    return LiveResult(UNKNOWN, f"RegisterHotKey failed with error {err}", method)


# --- X11 -------------------------------------------------------------------

class _XErrorEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong),
        ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte),
        ("request_code", ctypes.c_ubyte),
        ("minor_code", ctypes.c_ubyte),
    ]


_XErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(_XErrorEvent))
_BAD_ACCESS = 10
_MOD2_NUMLOCK = 1 << 4
_GRAB_MODE_ASYNC = 1


def _check_x11(combo: Combo) -> LiveResult:
    available, reason = check_available()
    method = "X11 XGrabKey"
    if not available:
        return LiveResult(UNSUPPORTED, reason, method)
    xlib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11"))
    xlib.XOpenDisplay.restype = ctypes.c_void_p
    xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
    xlib.XDefaultRootWindow.restype = ctypes.c_ulong
    xlib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    xlib.XStringToKeysym.restype = ctypes.c_ulong
    xlib.XStringToKeysym.argtypes = [ctypes.c_char_p]
    xlib.XKeysymToKeycode.restype = ctypes.c_ubyte
    xlib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    xlib.XGrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int]
    xlib.XUngrabKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_ulong]
    xlib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
    xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]
    xlib.XSetErrorHandler.restype = ctypes.c_void_p

    display = xlib.XOpenDisplay(None)
    if not display:
        return LiveResult(UNSUPPORTED, "could not open the X display", method)
    errors = []

    def on_error(_display, event):
        errors.append(event.contents.error_code)
        return 0

    handler = _XErrorHandler(on_error)
    previous = xlib.XSetErrorHandler(handler)
    try:
        try:
            keysym = xlib.XStringToKeysym(x11_keysym_name(combo.key).encode())
        except KeyError:
            return LiveResult(UNKNOWN, f"no X11 keysym for {combo.key}", method)
        keycode = xlib.XKeysymToKeycode(display, keysym)
        if not keycode:
            return LiveResult(UNKNOWN, f"{combo.key} is not on the current keyboard map", method)
        root = xlib.XDefaultRootWindow(display)
        mask = 0
        for mod in combo.mods:
            mask |= X11_MODIFIERS[mod]
        taken = False
        for extra in (0, _MOD2_NUMLOCK):
            errors.clear()
            xlib.XGrabKey(display, keycode, mask | extra, root, 1, _GRAB_MODE_ASYNC, _GRAB_MODE_ASYNC)
            xlib.XSync(display, 0)
            if _BAD_ACCESS in errors:
                taken = True
                break
            xlib.XUngrabKey(display, keycode, mask | extra, root)
            xlib.XSync(display, 0)
        if taken:
            return LiveResult(TAKEN, "another X11 client (usually the desktop) has grabbed it", method)
        return LiveResult(FREE, "no X11 client has grabbed it", method)
    finally:
        xlib.XSetErrorHandler(ctypes.c_void_p(previous) if previous else None)
        xlib.XCloseDisplay(display)
