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
profile = {
    "name": "MyanTerm",
    "type": "Window Settings",
    "ProfileCurrentVersion": 2.09,
    "Font": plistlib.dumps(font, fmt=plistlib.FMT_BINARY),
    "FontAntialias": True,
    "FontWidthSpacing": 1.0,
    "FontHeightSpacing": 1.0,
    "columnCount": 100,
    "rowCount": 30,
}
with open(out, "wb") as f:
    plistlib.dump(profile, f, fmt=plistlib.FMT_XML)
print("wrote", out)
