"""Split Burmese text into the clusters MyanTerm draws as single glyphs.

A cluster is one of
  kinzi  : င ် ္ + core          e.g. င်္ဂ
  stack  : C ္ + core            e.g. တ္တ, ဒ္ဓ
  final  : C ် [့] [း]  /  C ့ ်   e.g. င်, န့်, င်း  (also က်ျား, န်ု)
  core   : C [medials] [vowels] [tones]   e.g. ကြော်, ကျေး, ပို့
Anything else (spaces, Latin, digits, punctuation) is returned as-is.
"""
import re
import sys
import unicodedata

CONS = "က-ဪဿ၎ၐ-ၕၚ-ၝၡၥၦၮ-ၰၵ-ႁႎꧠ-ꧤꧧ-ꧯꧺ-ꧾꩠ-ꩯꩱ-ꩶꩺ"
MED = "ျြွှၞ-ၠႂ"
VOW = "ေါာိီုူဲဳ-ဵံၖ-ၙၢ-ၤၧ-ၭၱ-ၴႃ-ႍႏႚ-ႝ"
TONE = "့်း"
CORE = f"[{CONS}](?![်္])[{MED}]*[{VOW}]*[{TONE}]*"
# a final may carry ျ or a vowel written after the asat (ယောက်ျား, ကျွန်ုပ်), but never ေ or ြ:
# those always start the next syllable (also when it is typed in visual order)
FINAL = f"[{CONS}](?:\u103A\u1037?|\u1037\u103A)\u103B?[\u102B-\u1030\u1032-\u1036]*[{TONE}]*"
KINZI = f"င်္{CORE}"
STACK = f"[{CONS}]္{CORE}"
CLUSTER = re.compile(f"{KINZI}|{STACK}|{FINAL}|{CORE}")

# Standard Unicode storage order inside a syllable (UTN #11): consonant, medials ျ ြ ွ ှ,
# ေ, ါ/ာ, ိ/ီ/ဲ, ု/ူ, then ံ ့ ် (any order) and း last. Text typed in visual order or with
# swapped marks also matches CLUSTER, so the syllable list keeps only this order and the
# font maps the common other orders onto the same glyphs.
EXT_VOW = "\u1033-\u1035\u1056-\u1059\u1062-\u1064\u1067-\u106D\u1071-\u1074\u1083-\u108D\u108F\u109A-\u109D"
CANON_CORE = (f"[{CONS}]\u103B?\u103C?\u103D?\u103E?[\u105E-\u1060\u1082]*"
              f"\u1031?[\u102B\u102C]?[\u102D\u102E\u1032]?[\u102F\u1030]?[{EXT_VOW}]*[\u1036\u1037\u103A]{{0,3}}\u1038?")
CANONICAL = re.compile(f"\u1004\u103A\u1039{CANON_CORE}|[{CONS}]\u1039{CANON_CORE}|{FINAL}|{CANON_CORE}")


def canonical(cluster):
    """True if the cluster is in standard Unicode order."""
    return CANONICAL.fullmatch(cluster) is not None


def clusters(text):
    """Yield (cluster, is_myanmar) pieces covering text."""
    pos = 0
    for m in CLUSTER.finditer(text):
        if m.start() > pos:
            yield text[pos:m.start()], False
        yield m.group(), True
        pos = m.end()
    if pos < len(text):
        yield text[pos:], False


def cells(s, spacing_marks=True):
    """Cells Terminal.app draws s in: non-spacing marks take 0 cells, everything else 1.
    Terminal before macOS 27 draws the spacing vowel signs and medials (Mc: ာ ေ ျ ြ း ...)
    with no width either (it still gives them a cell for the cursor): spacing_marks=False."""
    zero = ("Mn",) if spacing_marks else ("Mn", "Mc")
    return sum(0 if unicodedata.category(ch) in zero else 1 for ch in s)


if __name__ == "__main__":
    for line in (sys.argv[1:] or sys.stdin):
        print(" | ".join(c for c, mm in clusters(line.strip()) if mm))
