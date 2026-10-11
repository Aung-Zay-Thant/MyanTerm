"""MyanTerm builder: natural Burmese in macOS Terminal.app.

How Terminal.app draws text: it shapes each row with Core Text, then draws the
glyphs one after another, advancing by the cell width of the characters each
glyph came from (letters and spacing vowels/medials = 1 cell, non-spacing marks
= 0). Glyph advances and GPOS positions are ignored.

So this font:
  * has no 'mym2' script: Core Text then keeps glyphs in typed order;
  * turns every Burmese syllable into ONE glyph (GSUB ligature) drawn from the
    real Noto Sans Myanmar shaping (HarfBuzz): correct reordering, medial ra
    widths, kinzi, stacks and mark placement;
  * lays syllables out proportionally, like normal typesetting, even though
    Terminal gives each one a fixed number of cells: each syllable glyph exists
    in several copies shifted by small steps, and a contextual GSUB rule picks
    the copy that continues where the previous syllable's natural spacing ended
    (a running "carry", left to right). Text may run about 4 cells ahead of
    the grid (the spare room then shows up at the next space) and spill about
    2 cells past it; wide syllables are squeezed a little (shapes only, never
    their natural side spacing) when they keep running over. The most common
    syllables get a copy for every carry level, the next ones a few coarse
    copies, rare ones a single glyph. Spaces, ASCII brackets,
    quotes and punctuation next to Burmese join the flow; zero-width
    characters (ZWSP, ZWNJ, ZWJ, WJ), which Terminal gives a cell, are
    invisible members of it;
  * keeps per-character "grid" glyphs (shifted by whole cells) as a fallback for
    unusual sequences that aren't in the syllable list.

usage: build.py MONO.ttf MYANMAR.ttf CLUSTERS.txt OUT.ttf FAMILY
CLUSTERS.txt: one syllable per line, most frequent first ("text<TAB>count" ok).
Latin, Greek and Cyrillic runs skip all of this (empty feature list), so English
text and code shape as fast as with a plain monospace font.
"""
import hashlib
import sys
import unicodedata

import uharfbuzz as hb
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.merge import Merger
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from segment import cells  # noqa: E402

mono_path, mm_path, clusters_path, out_path, family = sys.argv[1:6]

CELL = 8000 / 13    # cell width in font units. Terminal.app rounds its cell width to a whole point,
                    # so a 0.6 em font gets 8 pt cells at 13 pt (2.6% wider than the font assumes).
                    # 8/13 em makes the design match Terminal exactly at 13 pt (and 26 pt).
S = 0.86            # Burmese size relative to the em (tuned at 0.84 for 0.6 em cells, scaled to 8/13 em)
# Carry levels (units; 600 = one cell). Text may run up to ~4 cells ahead of the grid
# (narrow syllables; the spare room shows up at the next space) and up to ~2 cells
# behind it (wide syllables). Chosen by simulating 6000 real phrases (FLORES-200):
# only ~0.2% of syllable joins end up more than 90 units off their natural spacing.
LEVELS = list(range(-2340, 1171, 90))
COARSE = [-1800, -900, 0, 540, 1080]   # fewer copies for the less common syllables
NEG_LIMIT, POS_LIMIT = LEVELS[0], LEVELS[-1]
SOFT = 300          # running over by up to half a cell is fine (a space can take it)
STEER = 0.35        # beyond that, this share of the overflow is removed by squeezing
LAG_SOFT = -600     # running more than a cell ahead of the grid (long narrow phrases):
EXPAND = 1.06       #   widen shapes by up to 6% ...
STEER_LAG = 0.3     #   ... to win back this share of the excess,
TRACK = 0           #   and beyond two cells add up to this much extra spacing (off: it showed as gaps)
MIN_SQUEEZE = 0.85  # shapes are never squeezed narrower than this (side spacing never is)
HARD_SQUEEZE = 0.75 # ...unless the spill would pass POS_LIMIT
MAX_CARRY = 1250    # the most frequent syllables get a copy for every carry level
COARSE_CARRY = 2500 # the next ones get copies for the COARSE levels only


QUANT_BIAS = 15     # round carry levels slightly towards tighter spacing: a join may end up
                    # at most ~30 units looser or ~60 units tighter than natural (never touching)


def quant(out):
    """Carry level for an overflow of `out` units."""
    return min(LEVELS, key=lambda lv: abs(lv - (out - QUANT_BIAS)))


def lvl_name(lv):
    return f"m{-lv}" if lv < 0 else f"p{lv}"
GLYPH_LIMIT = 64450 # TrueType hard limit is 65535; ~1000 kept for punctuation/space/zero-width copies
OVERHANG = 0.12     # how far a syllable's ink may reach past its cells, per side, in cells
MARGIN = 25         # minimum side bearing for syllables that fit
ASCENT = 1069       # Noto Sans Mono ascent (unchanged)
DESCENT = 420       # extra room below for Burmese marks

mm = TTFont(mm_path)
gs = mm.getGlyphSet()
hmtx = mm["hmtx"]
cmap = mm.getBestCmap()
by_char = {chr(u): g for u, g in cmap.items()}
hb_font = hb.Font(hb.Face(hb.Blob.from_file_path(mm_path)))


def bounds(g):
    bp = BoundsPen(gs)
    gs[g].draw(bp)
    return bp.bounds


def outline(g):
    rec = DecomposingRecordingPen(gs)
    gs[g].draw(rec)
    return rec.value


def shifted(fx, d):
    return lambda x: fx(x) + d


# ---------------------------------------------------------------- grid fallback
# One glyph per character, positioned in its own cell; contextual variants shift
# outlines by whole cells so the visual order comes out right without reordering.
INK = CELL * (1 + 2 * OVERHANG) - 2 * MARGIN
GAP = 20
new = {}   # name -> (source glyph, x-mapping, advance)


def add(name, src, fx, adv):
    new[name] = (src, fx, adv)


mark_anchor, base_anchor_ref = {}, {}
REF_BASE = "ma"
for lk in mm["GPOS"].table.LookupList.Lookup:
    if lk.LookupType != 4:
        continue
    for st in lk.SubTable:
        sid = id(st)
        for g, r in zip(st.MarkCoverage.glyphs, st.MarkArray.MarkRecord):
            mark_anchor.setdefault(g, (sid, r.Class, r.MarkAnchor.XCoordinate))
        if REF_BASE in st.BaseCoverage.glyphs:
            br = st.BaseArray.BaseRecord[st.BaseCoverage.glyphs.index(REF_BASE)]
            for c, a in enumerate(br.BaseAnchor):
                if a is not None:
                    base_anchor_ref[(sid, c)] = a.XCoordinate


def fit(g, room=INK):
    b = bounds(g) or (0, 0, 0, 0)
    w = b[2] - b[0]
    return S * min(1.0, room / (S * w)) if w else S


def center_map(g):
    b = bounds(g) or (0, 0, 0, 0)
    k = fit(g)
    dx = (CELL - k * (b[0] + b[2])) / 2
    return lambda x: k * x + dx


ref_map = center_map(REF_BASE)


def mark_map(g):
    k = S
    sc = mark_anchor.get(g)
    if sc and (sc[0], sc[1]) in base_anchor_ref:
        ax, target = sc[2], ref_map(base_anchor_ref[(sc[0], sc[1])]) - CELL
    else:
        b = bounds(g) or (0, 0, 0, 0)
        ax, target = (b[0] + b[2]) / 2, -CELL / 2
    return lambda x: k * (x - ax) + target


consonants, mark_fx, cons_fx = [], {}, {}
for ch, g in sorted(by_char.items()):
    cp = ord(ch)
    if not (0x1000 <= cp <= 0x109F or 0xA9E0 <= cp <= 0xA9FF or 0xAA60 <= cp <= 0xAA7F):
        continue
    cat = unicodedata.category(ch)
    if cat == "Mn":
        fx = mark_map(g)
        add(g, g, fx, 0)
        mark_fx[g] = fx
    elif g == "_e":
        b = bounds(g)
        k = fit(g, CELL - 2 * GAP)
        fx = (lambda x, k=k, d=CELL - GAP - k * b[2]: k * x + d - CELL)
        add(g, g, fx, CELL)
        add(g + ".l2", g, shifted(fx, -CELL), CELL)
    elif g == "_tall_aa":
        k = fit(g, CELL - 2 * GAP)
        add(g, g, (lambda x, k=k: k * x + 110), CELL)
    elif g in ("_aa", "visarga"):
        b = bounds(g)
        k = fit(g, CELL - 2 * GAP)
        add(g, g, (lambda x, k=k, d=GAP - k * b[0]: k * x + d), CELL)
    elif g in ("medial_ya", "medial_ra"):
        pass
    else:
        fx = center_map(g)
        add(g, g, fx, CELL)
        if cat == "Lo":
            consonants.append(g)
            cons_fx[g] = fx
            for suf, d in ((".r1", CELL), (".r2", 2 * CELL), (".r05", CELL / 2), (".l05", -CELL / 2)):
                add(g + suf, g, shifted(fx, d), CELL)

YA = ["medial_ya", "medial_ya_wa", "medial_ya_ha", "medial_ya_wa_ha"]
YA_SHIFT = 260


def ya_map(x, k=S * 0.9):
    if x <= -80:
        return k * x
    if x >= 91:
        return k * x + YA_SHIFT
    return k * x + YA_SHIFT * (x + 80) / 171


for g in YA:
    add(g, g, ya_map, CELL)
    add(g + ".r1", g, shifted(ya_map, CELL), CELL)

RA = ["medial_ra", "medial_ra_wa", "medial_ra_wa_ha"]
RA_L, RA_R = 0.20 * CELL, 1.95 * CELL
K_STROKE = S * 0.9
RA_PTS = [(91, RA_L), (181, RA_L + 90 * K_STROKE), (735, RA_R - 89 * K_STROKE), (824, RA_R)]
RA_MID = (RA_PTS[1][1] + RA_PTS[2][1]) / 2
C_IN_RA = RA_MID - CELL - CELL / 2


def ra_map(x):
    pts = RA_PTS
    if x <= pts[0][0]:
        return pts[0][1] + (x - pts[0][0]) * K_STROKE
    if x >= pts[-1][0]:
        return pts[-1][1] + (x - pts[-1][0]) * K_STROKE
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if xa <= x <= xb:
            return ya + (yb - ya) * (x - xa) / (xb - xa)


for g in RA:
    add(g, g, shifted(ra_map, -CELL), CELL)
    add(g + ".r1", g, ra_map, CELL)

for g, fx in cons_fx.items():
    add(g + ".ra1", g, shifted(fx, C_IN_RA + CELL), CELL)
    add(g + ".ra2", g, shifted(fx, C_IN_RA + 2 * CELL), CELL)

for g in ("medial_wa_ha", "medial_ha_u", "medial_ha_uu"):
    fx = mark_map(g)
    add(g, g, fx, 0)
    mark_fx[g] = fx
for g, fx in mark_fx.items():
    add(g + ".l1", g, shifted(fx, -CELL), 0)
    add(g + ".r1", g, shifted(fx, CELL), 0)
    add(g + ".lra", g, shifted(fx, C_IN_RA), 0)

b = bounds("kinzi")
add("kinzi.sp", "kinzi", (lambda x, k=S, c=(b[0] + b[2]) / 2: k * (x - c) + CELL), CELL)
SUBS = {}
for g in consonants:
    if g + ".sub" in gs:
        b = bounds(g + ".sub")
        k = S * min(1.0, INK / (S * max(1, b[2] - b[0])))
        add(g + ".subsp", g + ".sub", (lambda x, k=k, c=(b[0] + b[2]) / 2: k * (x - c)), CELL)
        SUBS[g] = g + ".subsp"

# ---------------------------------------------------------------- syllable glyphs
P = "mm."
RAW = "raw."   # unscaled Noto outlines, referenced by the syllable composites


def shape(s):
    buf = hb.Buffer()
    buf.add_str(s)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)
    out, x = [], 0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        out.append((hb_font.glyph_to_string(info.codepoint), x + pos.x_offset, pos.y_offset))
        x += pos.x_advance
    return out, x


def place(placed, adv, n, carry):
    """Draw a syllable whose natural origin sits `carry` units into its n-cell box.
    Squeezing narrows the ink only; the natural side bearings are kept so
    neighbouring syllables never touch. Returns (components, kx, level_out),
    level_out being where the next syllable starts."""
    lo, hi = 1e9, -1e9
    for g, x, y in placed:
        bb = bounds(g)
        if bb:
            lo, hi = min(lo, x + bb[0]), max(hi, x + bb[2])
    if hi < lo:                                     # invisible: nothing to draw
        lo = hi = 0
    inkw, side = hi - lo, S * (lo + (adv - hi))
    box = n * CELL

    def width(k):
        return side + k * inkw

    kx = S
    out = carry + width(kx) - box
    if out > SOFT and inkw:                         # running well over: squeeze the shapes a little
        kx = max(S * MIN_SQUEEZE, (S * inkw - STEER * (out - SOFT)) / inkw)
        out = carry + width(kx) - box
        if out > POS_LIMIT:                         # hard limit on spilling into the next cells
            kx = max(S * HARD_SQUEEZE, (box + POS_LIMIT - carry - side) / inkw)
            out = carry + width(kx) - box
    elif out < LAG_SOFT and inkw:                   # running far ahead of the grid: widen a touch
        kx = min(S * EXPAND, (S * inkw + STEER_LAG * (LAG_SOFT - out)) / inkw)
        out = carry + width(kx) - box
        if out < 2 * LAG_SOFT:
            out = min(2 * LAG_SOFT, out + TRACK)
    x0 = carry
    if out < NEG_LIMIT:                             # far too narrow even so: split the excess
        x0 += (NEG_LIMIT - out) / 2
        out = NEG_LIMIT
    level = quant(out)
    start = x0 + S * lo                             # left ink edge
    comps = [(g, start + kx * (x - lo), y) for g, x, y in placed]
    return comps, kx, level


raw_needed = set()
syl = []          # dicts: text, base, inputs, n, variants{level_in: (name, comps, kx, level_out)}
seen = set()
LETTERS = {}      # single character -> syllable entry (isolated letters/digits/punctuation)
mono_glyphs = 2320   # Latin glyphs left after subsetting (checked by the assert below)
budget = GLYPH_LIMIT - mono_glyphs - len(new) - 1
used = 0
for line in open(clusters_path, encoding="utf-8"):
    s = line.rstrip("\n").split("\t")[0]
    if not s or s in seen or any(ch not in by_char for ch in s):
        continue
    if used + len(raw_needed) + len(LEVELS) > budget:
        print("glyph budget reached; dropped the rest of the list from", repr(s))
        break
    n = cells(s)
    if n == 0:
        continue
    if len(s) == 1 and unicodedata.category(s) not in ("Lo", "Nd", "Po", "So"):
        continue
    placed, adv = shape(s)
    if any(g in (".notdef", "uni25CC") for g, _, _ in placed):
        continue                                  # shaper had to insert a dotted circle: malformed
    seen.add(s)
    base = "syl." + hashlib.md5(s.encode()).hexdigest()[:12]
    levels = LEVELS if len(syl) < MAX_CARRY else COARSE if len(syl) < COARSE_CARRY else [0]
    variants = {}
    for k in levels:
        comps, kx, lo = place(placed, adv, n, k)
        variants[k] = (base if k == 0 else f"{base}.{lvl_name(k)}", comps, kx, lo)
    used += len(variants)
    entry = dict(text=s, base=base, n=n, variants=variants,
                 inputs=tuple(P + by_char[ch] for ch in s))
    syl.append(entry)
    if len(s) == 1:
        LETTERS[s] = entry
    raw_needed.update(g for g, _, _ in placed)

print("syllables:", len(syl), "with carry copies:", sum(len(e["variants"]) > 1 for e in syl),
      "isolated letters:", len(LETTERS))

# ---------------------------------------------------------------- assemble Myanmar font
var_names = [v[0] for e in syl for k, v in sorted(e["variants"].items())]
order = [".notdef"] + [P + n for n in new] + sorted(RAW + g for g in raw_needed) + var_names
assert len(order) + mono_glyphs < 65535, f"too many glyphs: {len(order)}"
glyphs, metrics = {".notdef": mm["glyf"][".notdef"]}, {".notdef": round(CELL)}
for n, (src, fx, adv) in new.items():
    pen = TTGlyphPen(None)
    for op, pts in outline(src):
        getattr(pen, op)(*[(round(fx(x)), round(S * y)) for x, y in pts])
    glyphs[P + n] = pen.glyph()
    metrics[P + n] = adv
for g in raw_needed:
    pen = TTGlyphPen(None)
    for op, pts in outline(g):
        getattr(pen, op)(*[(round(x), round(y)) for x, y in pts])
    glyphs[RAW + g] = pen.glyph()
    metrics[RAW + g] = 0
for e in syl:
    for name, comps, kx, _ in e["variants"].values():
        parts = []
        for g, x, y in comps:
            if not bounds(g):
                continue
            c = GlyphComponent()
            c.glyphName = RAW + g
            c.x, c.y = round(x), round(S * y)
            c.transform = [[kx, 0], [0, S]]
            c.flags = 0x1000   # UNSCALED_COMPONENT_OFFSET
            parts.append(c)
        gl = Glyph()
        gl.numberOfContours = -1
        gl.components = parts
        if not parts:          # e.g. a syllable of only invisible marks
            gl = TTGlyphPen(None).glyph()
        glyphs[name] = gl
        metrics[name] = round(e["n"] * CELL)

out = TTFont(mm_path)
out["cmap"].tables
for t in ("GSUB", "GPOS", "GDEF"):
    del out[t]
out.setGlyphOrder(order)
out["glyf"].glyphs = glyphs
out["glyf"].glyphOrder = order
out["hmtx"].metrics = {}
for n in order:
    glyphs[n].recalcBounds(out["glyf"])
    out["hmtx"].metrics[n] = (round(metrics[n]), getattr(glyphs[n], "xMin", 0))
for sub in out["cmap"].tables:
    sub.cmap = {u: P + g for u, g in cmap.items() if g in new and (sub.format == 12 or u <= 0xFFFF)}
out["post"].formatType = 2.0
out["post"].extraNames, out["post"].mapping = [], {}
out["maxp"].numGlyphs = len(order)
mm_tmp = out_path + ".mm.ttf"
out.save(mm_tmp)

from fontTools import subset  # noqa: E402

KEEP = [(0x0020, 0x036F), (0x0370, 0x03FF), (0x0400, 0x052F), (0x1E00, 0x1EFF), (0x2000, 0x2BFF),
        (0xFB00, 0xFB06), (0xFFFD, 0xFFFD)]
mono = TTFont(mono_path)
opts = subset.Options()
opts.glyph_names = True
opts.notdef_outline = True
opts.hinting = False
opts.drop_tables += ["GSUB", "GPOS", "GDEF"]
sub_ = subset.Subsetter(opts)
sub_.populate(unicodes=[u for a, b in KEEP for u in range(a, b + 1) if u in mono.getBestCmap()])
sub_.subset(mono)
mono_tmp = out_path + ".mono.ttf"
mono.save(mono_tmp)

merged = Merger().merge([mono_tmp, mm_tmp])
for t in ("GSUB", "GPOS", "GDEF"):
    if t in merged:
        del merged[t]

# ASCII/typographic punctuation that often touches Burmese: shifted copies of the Latin glyph,
# drawn proportionally (ink + small bearings) so it hugs the Burmese text it follows.
PUNCT_CHARS = "()[]{}\"',.:;!?-/\u2018\u2019\u201C\u201D\u2013\u2014\u2026"
PB = 50   # side bearing for proportional punctuation
mcmap = merged.getBestCmap()
mglyf, mhmtx = merged["glyf"], merged["hmtx"]
extra = {}                       # name -> (Glyph, advance)
punct = []                       # carry entries for punctuation
for ch in PUNCT_CHARS:
    g = mcmap.get(ord(ch))
    if not g:
        continue
    gl = mglyf[g]
    gl.recalcBounds(mglyf)
    if not hasattr(gl, "xMin"):
        continue
    natural = (gl.xMax - gl.xMin) + 2 * PB
    variants = {0: (g, None, 0)}
    for k in LEVELS:
        if k == 0:
            continue
        name = f"{g}.mm{lvl_name(k)}"
        c = GlyphComponent()
        c.glyphName = g
        c.x, c.y = round(k + PB - gl.xMin), 0
        c.flags = 0x1000
        comp = Glyph()
        comp.numberOfContours = -1
        comp.components = [c]
        extra[name] = (comp, CELL)
        variants[k] = (name, None, quant(k + natural - CELL))
    punct.append(dict(base=g, variants=variants))

# zero-width characters: Terminal gives each a cell; draw nothing and hand the cell to the flow
ZW_CHARS = [0x200B, 0x200C, 0x200D, 0x2060]
zw = dict(base="mm.zw", variants={})
for k in LEVELS:
    name = "mm.zw" if k == 0 else f"mm.zw.{lvl_name(k)}"
    extra[name] = (TTGlyphPen(None).glyph(), 0)
    zw["variants"][k] = (name, None, quant(k - CELL))

# the space joins the flow: after a phrase that ran over it shrinks (to half a cell at least)
# so phrases never touch; after a phrase that ran short it takes up half of the spare room
space_g = mcmap.get(0x20)
space = dict(base=space_g, variants={0: (space_g, None, 0)})
for k in LEVELS:
    if k == 0:
        continue
    name = f"{space_g}.mm{lvl_name(k)}"
    extra[name] = (TTGlyphPen(None).glyph(), CELL)
    space["variants"][k] = (name, None, quant(max(0, k - CELL / 2) if k > 0 else k / 2))

order_m = merged.getGlyphOrder() + list(extra)
assert len(order_m) < 65535, f"too many glyphs: {len(order_m)}"
merged.setGlyphOrder(order_m)
for name, (gl, adv) in extra.items():
    mglyf[name] = gl
    gl.recalcBounds(mglyf)
    mhmtx[name] = (round(adv), getattr(gl, "xMin", 0))
for sub in merged["cmap"].tables:
    for u in ZW_CHARS:
        if sub.format == 12 or u <= 0xFFFF:
            sub.cmap[u] = "mm.zw"
merged["maxp"].numGlyphs = len(order_m)


def cls(names):
    return "[" + " ".join(P + n for n in names) + "]"


def gcls(names):
    return "[" + " ".join(names) + "]"


C = consonants
MARKS = [n for n, v in new.items() if v[2] == 0 and not n.endswith((".l1", ".r1", ".lra"))]
CONT = sorted({P + by_char[ch] for ch in by_char
               if unicodedata.category(ch) in ("Mn", "Mc") and by_char[ch] in new})
multi = sorted((e for e in syl if len(e["text"]) > 1), key=lambda e: -len(e["inputs"]))
syl_rules = "\n".join(f"  sub {' '.join(e['inputs'])} by {e['base']};" for e in multi)
letters = sorted(LETTERS.values(), key=lambda e: e["inputs"][0])
carry_bases = [e for e in syl if len(e["variants"]) > 1] + punct + [zw, space]
LEVEL_RANGE = LEVELS
out_class = {k: [] for k in LEVEL_RANGE}
for e in syl + [zw]:
    for v in e["variants"].values():
        out_class[v[-1]].append(v[0])
for e in punct + [space]:        # an unshifted punctuation mark or space resets the flow
    for k, v in e["variants"].items():
        if k != 0:
            out_class[v[-1]].append(v[0])
ALNUM = sorted({mcmap[ord(c)] for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789" if ord(c) in mcmap})
PUNCT_BASES = [e["base"] for e in punct]


def copy_for(e, k):
    """The copy of e to use after a syllable that left the carry at level k."""
    v = e["variants"]
    return v[k][0] if k in v else v[min(v, key=lambda lv: abs(lv - k))][0]


carry_lookups = "\n".join(
    f"lookup TO_{lvl_name(k)} {{\n" + "\n".join(f"  sub {e['base']} by {copy_for(e, k)};"
                                               for e in carry_bases if copy_for(e, k) != e["base"])
    + f"\n}} TO_{lvl_name(k)};" for k in LEVEL_RANGE if k != 0)
carry_classes = "\n".join(f"@OUT_{lvl_name(k)} = {gcls(out_class[k])};" for k in out_class if k != 0 and out_class[k])
carry_rules = "\n".join(f"  sub @OUT_{lvl_name(k)} @CARRY' lookup TO_{lvl_name(k)};"
                        for k in LEVEL_RANGE if k != 0 and out_class[k])
all_out = " ".join(f"@OUT_{lvl_name(k)}" for k in LEVEL_RANGE if k != 0 and out_class[k])

fea = f"""
languagesystem DFLT dflt;
languagesystem latn dflt;

@C = {cls(C)};
@C_r1 = {cls(g + '.r1' for g in C)};
@C_r2 = {cls(g + '.r2' for g in C)};
@C_r05 = {cls(g + '.r05' for g in C)};
@C_l05 = {cls(g + '.l05' for g in C)};
@C_ra1 = {cls(g + '.ra1' for g in C)};
@C_ra2 = {cls(g + '.ra2' for g in C)};
@Cany = [@C @C_r1 @C_r2 @C_r05 @C_l05 @C_ra1 @C_ra2];
@YA = {cls(YA)};
@YA_r1 = {cls(g + '.r1' for g in YA)};
@YAany = [@YA @YA_r1];
@RA = {cls(RA)};
@RA_r1 = {cls(g + '.r1' for g in RA)};
@RAany = [@RA @RA_r1];
@E = [{P}_e];
@Eany = [{P}_e {P}_e.l2];
@MK = {cls(MARKS)};
@MK_l1 = {cls(g + '.l1' for g in MARKS)};
@MK_r1 = {cls(g + '.r1' for g in MARKS)};
@MK_lra = {cls(g + '.lra' for g in MARKS)};
@MKany = [@MK @MK_l1 @MK_r1 @MK_lra];
@SUBSP = {cls(SUBS.values())};
@CONT = {gcls(CONT)};
@LET_IN = {gcls(e['inputs'][0] for e in letters)};
@LET_OUT = {gcls(e['base'] for e in letters)};
@CARRY = {gcls(e['base'] for e in carry_bases)};
@PUNCT = {gcls(PUNCT_BASES)};
@ALNUM = {gcls(ALNUM)};
{carry_classes}

# 1. whole syllables -> one glyph each
lookup SYLLABLES {{
{syl_rules}
}} SYLLABLES;

# 2. a letter that is a whole syllable by itself (not followed by a vowel sign, medial, mark...)
lookup LETTERS {{
  ignore sub @LET_IN' @CONT;
  sub @LET_IN' by @LET_OUT;
}} LETTERS;

# 3. proportional layout: pick the copy that continues the previous syllable's spacing
{carry_lookups}

lookup CARRY_FLOW {{
  lookupflag IgnoreMarks;   # stray fallback marks don't break the flow
  # punctuation right before Latin letters/digits stays on the grid (code, English)
  ignore sub [{all_out}] @PUNCT' @ALNUM;
{carry_rules}
}} CARRY_FLOW;

# 4. per-character fallback for sequences not in the syllable list
lookup LIGS {{
  sub {P}nga {P}asat {P}virama by {P}kinzi.sp;
{chr(10).join(f'  sub {P}virama {P}{c} by {P}{s};' for c, s in SUBS.items())}
  sub {P}medial_ya {P}medial_wa {P}medial_ha by {P}medial_ya_wa_ha;
  sub {P}medial_ya {P}medial_wa by {P}medial_ya_wa;
  sub {P}medial_ya {P}medial_ha by {P}medial_ya_ha;
  sub {P}medial_ra {P}medial_wa {P}medial_ha by {P}medial_ra_wa_ha;
  sub {P}medial_ra {P}medial_wa by {P}medial_ra_wa;
  sub {P}medial_wa {P}medial_ha by {P}medial_wa_ha;
  sub {P}medial_ha {P}_u by {P}medial_ha_u;
  sub {P}medial_ha {P}_uu by {P}medial_ha_uu;
}} LIGS;

lookup STACK {{
  sub @C' @SUBSP by @C_r05;
  sub {P}kinzi.sp @C' by @C_l05;
}} STACK;

lookup SHIFT_C {{
  lookupflag IgnoreMarks;
  sub @C' @RA @E by @C_ra2;
  sub @C' @YA @E by @C_r1;
  sub @C' @RA by @C_ra1;
  sub @C' @E by @C_r1;
}} SHIFT_C;

lookup SHIFT_M {{
  lookupflag IgnoreMarks;
  sub @YA' @E by @YA_r1;
  sub @RA' @E by @RA_r1;
  sub [@YAany @RAany] @E' by {P}_e.l2;
}} SHIFT_M;

lookup SHIFT_MK {{
  sub @Cany @MK' @Eany by @MK_r1;
  sub @Cany @MK' @MKany @Eany by @MK_r1;
  sub @Cany @MKany @MK' @Eany by @MK_r1;
  sub @RAany @MK' by @MK_lra;
  sub @RAany @MKany @MK' by @MK_lra;
  sub @RAany @Eany @MK' by @MK_lra;
  sub @RAany @Eany @MKany @MK' by @MK_lra;
  sub @YAany @MK' by @MK_l1;
  sub @YAany @MKany @MK' by @MK_l1;
  sub @YAany @MKany @MKany @MK' by @MK_l1;
  sub @YAany @Eany @MK' by @MK_l1;
  sub @YAany @Eany @MKany @MK' by @MK_l1;
}} SHIFT_MK;

feature ccmp {{
  lookup SYLLABLES;
  lookup LETTERS;
  lookup CARRY_FLOW;
  lookup LIGS;
  lookup STACK;
  lookup SHIFT_C;
  lookup SHIFT_M;
  lookup SHIFT_MK;
}} ccmp;

table GDEF {{
  GlyphClassDef [@Cany @YAany @RAany @Eany @SUBSP {P}kinzi.sp], , [@MKany {P}medial_wa_ha.l1 {P}medial_wa_ha.r1 {P}medial_wa_ha.lra {P}medial_ha_u.l1 {P}medial_ha_u.r1 {P}medial_ha_u.lra {P}medial_ha_uu.l1 {P}medial_ha_uu.r1 {P}medial_ha_uu.lra], ;
}} GDEF;
"""
open(out_path + ".fea", "w").write(fea)
addOpenTypeFeaturesFromString(merged, fea)

# Speed: Latin, Greek and Cyrillic runs get an empty feature list, so none of the Burmese
# lookups run on them (Core Text shapes English/code as fast as with a plain monospace font).
# Spaces and punctuation next to Burmese belong to the Myanmar run and still join the flow.
from fontTools.ttLib.tables import otTables  # noqa: E402

script_list = merged["GSUB"].table.ScriptList
for tag in ("latn", "grek", "cyrl"):
    rec = next((r for r in script_list.ScriptRecord if r.ScriptTag == tag), None)
    if rec is None:
        rec = otTables.ScriptRecord()
        rec.ScriptTag = tag
        rec.Script = otTables.Script()
        rec.Script.LangSysRecord, rec.Script.LangSysCount = [], 0
        rec.Script.DefaultLangSys = otTables.LangSys()
        rec.Script.DefaultLangSys.ReqFeatureIndex, rec.Script.DefaultLangSys.LookupOrder = 0xFFFF, None
        script_list.ScriptRecord.append(rec)
    rec.Script.DefaultLangSys.FeatureIndex, rec.Script.DefaultLangSys.FeatureCount = [], 0
script_list.ScriptRecord.sort(key=lambda r: r.ScriptTag)
script_list.ScriptCount = len(script_list.ScriptRecord)

merged["hhea"].ascent = ASCENT
merged["hhea"].descent = -DESCENT
merged["hhea"].lineGap = 0
merged["OS/2"].sTypoAscender, merged["OS/2"].sTypoDescender, merged["OS/2"].sTypoLineGap = ASCENT, -DESCENT, 0
merged["OS/2"].usWinAscent = max(merged["OS/2"].usWinAscent, ASCENT)
merged["OS/2"].usWinDescent = max(merged["OS/2"].usWinDescent, DESCENT)
merged["post"].isFixedPitch = 1
for g, (a, lsb) in list(merged["hmtx"].metrics.items()):   # widen the Latin cell to match
    if a in (600, 1200, 1800):
        merged["hmtx"].metrics[g] = (round(a / 600 * CELL), lsb)
merged["OS/2"].xAvgCharWidth = round(CELL)
merged["hhea"].advanceWidthMax = max(a for a, _ in merged["hmtx"].metrics.values())

style = "Bold" if "Bold" in mono_path else "Regular"
ps = family.replace(" ", "") + "-" + style
name = merged["name"]
name.names = [n for n in name.names if n.nameID in (7, 8, 9, 11, 12)]
VERSION = "1.100"
COPYRIGHT = ("Copyright 2022 The Noto Project Authors (https://github.com/notofonts/latin-greek-cyrillic, "
             "https://github.com/notofonts/myanmar). MyanTerm modifications copyright 2026 the MyanTerm authors.")
DESCRIPTION = ("Monospace font that renders Burmese (Myanmar script) naturally in macOS Terminal.app. "
               "Based on Noto Sans Mono and Noto Sans Myanmar.")
LICENSE = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
           "This license is available with a FAQ at: https://openfontlicense.org")
for nid, val in {0: COPYRIGHT, 1: family, 2: style, 3: f"{VERSION};{ps}", 4: f"{family} {style}",
                 5: f"Version {VERSION}", 6: ps, 10: DESCRIPTION, 13: LICENSE,
                 14: "https://openfontlicense.org"}.items():
    name.setName(val, nid, 3, 1, 0x409)
    name.setName(val, nid, 1, 0, 0)
merged["OS/2"].usWeightClass = 700 if style == "Bold" else 400
merged["OS/2"].fsSelection = (merged["OS/2"].fsSelection & ~0b1100001) | (0b100000 if style == "Bold" else 0b1000000)
merged["head"].macStyle = 1 if style == "Bold" else 0
merged.save(out_path)
print("glyphs:", len(merged.getGlyphOrder()), "saved", out_path)
