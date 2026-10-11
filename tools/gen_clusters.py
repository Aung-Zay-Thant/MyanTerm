"""Generate the syllable list MyanTerm draws as whole glyphs.

Combines a systematic set (every consonant x medial combination x vowel/tone
combination, plus finals, kinzi and stacked forms) with clusters seen in real
text (corpus TSV files: cluster<TAB>count).

usage: gen_clusters.py OUT.txt [CORPUS.tsv ...]
"""
import itertools
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from segment import CLUSTER  # noqa: E402

CONS = [chr(c) for c in range(0x1000, 0x1021 + 1)] + ["ဿ"]          # က..အ, ဿ
INDEP = ["ဣ", "ဤ", "ဥ", "ဦ", "ဧ", "ဩ", "ဪ", "၎"]
MEDIALS = ["", "ျ", "ြ", "ွ", "ှ", "ျွ", "ြွ",
           "ျှ", "ွှ", "ျွှ", "ြွှ", "ြှ"]
VOWELS = ["", "ာ", "ါ", "ိ", "ီ", "ု", "ူ", "ေ", "ဲ",
          "ော", "ေါ", "ော်", "ေါ်", "ို",
          "ံ", "ုံ", "ိံ", "ာ်"]
TONES = ["", "့", "း"]
FINAL_TAILS = ["်", "်း", "့်", "့်", "့်း"]

out_path = sys.argv[1]
seen, order = set(), []


def put(s):
    if s not in seen and CLUSTER.fullmatch(s):
        seen.add(s)
        order.append(s)


# digits and punctuation (။ ၊ are among the most frequent glyphs; they never form clusters)
for cp in range(0x1040, 0x1050):
    seen.add(chr(cp))
    order.append(chr(cp))

# real text, most frequent first (single letters included), so the most useful syllables
# are always in and get the carry copies
for tsv in sys.argv[2:]:
    for line in open(tsv, encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 2 and int(parts[1]) >= 2:
            put(parts[0])

# every remaining letter on its own (isolated letters are syllables too)
for cp in list(range(0x1000, 0x102B)) + [0x103F]:
    ch = chr(cp)
    if ch not in seen:
        seen.add(ch)
        order.append(ch)

for c, v, t in itertools.product(INDEP, VOWELS[:9], TONES):
    put(c + v + t)
for c, tail in itertools.product(CONS, FINAL_TAILS):
    put(c + tail)
for c, tail in itertools.product(CONS, ["\u103A\u102F", "\u103A\u103B\u102C\u1038", "\u103A\u103B\u102C"]):
    put(c + tail)        # ကျွန်ုပ်, ယောက်ျား
for c, v in itertools.product(CONS, ["", "ာ", "ါ", "ိ", "ီ", "ု", "ူ", "ေ", "ော", "ဲ"]):
    put("င်္" + c + v)                 # kinzi
for a, b in itertools.product(CONS, CONS):           # stacks (same-row stacks are the common ones)
    if (ord(a) - 0x1000) // 5 == (ord(b) - 0x1000) // 5 or a in "မနသပ":
        for v in ["", "ာ", "ိ", "ု", "ေ", "ါ"]:
            put(a + "္" + b + v)

# everything else in the systematic set last (the builder stops when the glyph budget is full)
for c, m, v, t in itertools.product(CONS, MEDIALS, VOWELS, TONES):
    if t and v.endswith("်") and t == "း":
        continue
    put(c + m + v + t)

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(order) + "\n")
print(len(order), "clusters ->", out_path)
