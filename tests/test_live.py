import sys

import pytest

from bindsmaker import live
from bindsmaker.keys import Combo

available, reason = live.check_available()


@pytest.mark.skipif(not available, reason=f"live check unavailable: {reason}")
def test_live_check_gives_an_answer():
    result = live.check(Combo.parse("Ctrl+Alt+Shift+F12"))
    assert result.status in (live.FREE, live.TAKEN), result.detail


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
def test_windows_detects_a_registered_hotkey():
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # Hold Win+Ctrl+Alt+Shift+F23 ourselves, then ask again: it must read as taken.
    assert user32.RegisterHotKey(None, 1, 0x0001 | 0x0002 | 0x0004 | 0x0008, 0x86)
    try:
        assert live.check(Combo.parse("Win+Ctrl+Alt+Shift+F23")).taken
    finally:
        user32.UnregisterHotKey(None, 1)
    assert not live.check(Combo.parse("Win+Ctrl+Alt+Shift+F23")).taken
