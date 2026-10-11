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
# a final may carry a medial/vowel written after the asat: ယောက်ျား, ကျွန်ုပ်
FINAL = f"[{CONS}](?:\u103A\u1037?|\u1037\u103A)[\u103B\u103C]?[{VOW}]*[{TONE}]*"
KINZI = f"င်္{CORE}"
STACK = f"[{CONS}]္{CORE}"
CLUSTER = re.compile(f"{KINZI}|{STACK}|{FINAL}|{CORE}")


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


def cells(s):
    """Terminal.app cell count: non-spacing marks take 0 cells, everything else 1."""
    return sum(0 if unicodedata.category(ch) == "Mn" else 1 for ch in s)


if __name__ == "__main__":
    for line in (sys.argv[1:] or sys.stdin):
        print(" | ".join(c for c, mm in clusters(line.strip()) if mm))
