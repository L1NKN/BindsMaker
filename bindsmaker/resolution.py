"""Screen resolutions like "1920x1080" or "2560x1440@144" for resolution-switching binds."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^\s*(\d{3,5})\s*[x×*]\s*(\d{3,5})\s*(?:@\s*(\d{2,3})\s*(?:hz)?)?\s*$", re.I)


class ResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class Resolution:
    width: int
    height: int
    hz: int = 0  # 0 = keep the current refresh rate

    @classmethod
    def parse(cls, text: str) -> "Resolution":
        match = _PATTERN.match(text or "")
        if not match:
            raise ResolutionError(f"can't read resolution {text!r} - use e.g. 1920x1080 or 2560x1440@144")
        w, h, hz = match.groups()
        return cls(int(w), int(h), int(hz or 0))

    def __str__(self) -> str:
        return f"{self.width}x{self.height}" + (f"@{self.hz}" if self.hz else "")


# AutoHotkey v2 function using the Win32 ChangeDisplaySettingsW API on the primary display.
# DEVMODEW offsets: dmSize 68, dmFields 72, dmPelsWidth 172, dmPelsHeight 176,
# dmDisplayFrequency 184; the struct is 220 bytes.
AHK_FUNCTION = """\
ChangeResolution(width, height, hz := 0) {
    dm := Buffer(220, 0)
    NumPut("UShort", 220, dm, 68)                        ; dmSize
    DllCall("EnumDisplaySettingsW", "Ptr", 0, "Int", -1, "Ptr", dm)  ; current settings
    NumPut("UInt", width, dm, 172)                       ; dmPelsWidth
    NumPut("UInt", height, dm, 176)                      ; dmPelsHeight
    fields := 0x80000 | 0x100000                         ; DM_PELSWIDTH | DM_PELSHEIGHT
    if hz {
        NumPut("UInt", hz, dm, 184)                      ; dmDisplayFrequency
        fields |= 0x400000                               ; DM_DISPLAYFREQUENCY
    }
    NumPut("UInt", fields, dm, 72)                       ; dmFields
    result := DllCall("ChangeDisplaySettingsW", "Ptr", dm, "UInt", 0)
    if result != 0 {
        mode := width "x" height
        if hz
            mode .= "@" hz
        MsgBox("Couldn't switch to " mode " - your display may not support it (error " result ").", "BindsMaker")
    }
}
"""


def ahk_call(res: Resolution) -> str:
    return f"ChangeResolution({res.width}, {res.height}" + (f", {res.hz})" if res.hz else ")")


def xrandr_command(res: Resolution) -> str:
    return f"xrandr -s {res.width}x{res.height}" + (f" -r {res.hz}" if res.hz else "")
