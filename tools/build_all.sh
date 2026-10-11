#!/bin/sh
# Rebuild MyanTerm (Regular + Bold) from the Noto sources and the syllable counts.
#   tools/build_all.sh            build into fonts/
#   tools/build_all.sh --install  also copy into ~/Library/Fonts (quit and reopen Terminal afterwards)
set -eu
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || python3 -m venv .venv
$PY -m pip install -q fonttools uharfbuzz
mkdir -p build fonts

$PY tools/gen_clusters.py build/clusters.txt data/corpus_counts.tsv
for w in Regular Bold; do
    $PY tools/build.py src/NotoSansMono-$w.ttf src/NotoSansMyanmar-$w.ttf build/clusters.txt \
        fonts/MyanTerm-$w.ttf "MyanTerm" 2>&1 | grep -v overflowed
done
rm -f fonts/*.mm.ttf fonts/*.mono.ttf
mv fonts/*.fea build/ 2>/dev/null || true
$PY tools/make_profile.py MyanTerm.terminal 13

if [ "${1:-}" = "--install" ]; then
    cp fonts/MyanTerm-Regular.ttf fonts/MyanTerm-Bold.ttf "$HOME/Library/Fonts/"
    echo "installed into ~/Library/Fonts"
fi
