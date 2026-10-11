"""Write a Terminal.app profile (.terminal) that uses MyanTerm.

usage: make_profile.py OUT.terminal [SIZE]
The font is stored the way Terminal stores it (an NSKeyedArchiver'd NSFont).
"""
import plistlib
import sys
from plistlib import UID

out, size = sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 13.0
font = {
    "$version": 100000,
    "$archiver": "NSKeyedArchiver",
    "$top": {"root": UID(1)},
    "$objects": ["$null",
                 {"NSSize": size, "NSfFlags": 16, "NSName": UID(2), "$class": UID(3)},
                 "MyanTerm-Regular",
                 {"$classname": "NSFont", "$classes": ["NSFont", "NSObject"]}],
}
# Everything that affects how Burmese is measured and drawn is pinned here, so the profile
# behaves the same on every Mac regardless of the user's other Terminal settings.
profile = {
    "name": "MyanTerm",
    "type": "Window Settings",
    "ProfileCurrentVersion": 2.09,
    "Font": plistlib.dumps(font, fmt=plistlib.FMT_BINARY),
    "FontAntialias": True,
    "FontWidthSpacing": 1.0,          # cell = round(font advance) = 8 pt at 13 pt, as the font is built for
    "FontHeightSpacing": 1.0,
    "CharacterEncoding": 4,           # UTF-8
    "SetLanguageEnvironmentVariables": True,   # LANG=..UTF-8, so zsh decodes Burmese as characters
    "EastAsianAmbiguousWide": False,  # keep Terminal's standard widths
    "TerminalType": "xterm-256color",
    "columnCount": 100,
    "rowCount": 30,
}
with open(out, "wb") as f:
    plistlib.dump(profile, f, fmt=plistlib.FMT_XML)
print("wrote", out)
