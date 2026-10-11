#!/bin/sh
# Make the release zip: dist/MyanTerm-VERSION.zip (fonts, installer, profile, zsh patch, docs).
#   tools/package.sh 1.0
set -eu
cd "$(dirname "$0")/.."
VERSION=${1:?usage: tools/package.sh VERSION}
NAME=MyanTerm-$VERSION
OUT=dist/$NAME
rm -rf "$OUT" "dist/$NAME.zip"
mkdir -p "$OUT/fonts" "$OUT/zsh" "$OUT/docs"
cp fonts/MyanTerm-Regular.ttf fonts/MyanTerm-Bold.ttf "$OUT/fonts/"
cp install.sh uninstall.sh "Install MyanTerm.command" MyanTerm.terminal README.md OFL.txt LICENSE "$OUT/"
cp zsh/build.sh zsh/myanmar-width.patch zsh/README.md "$OUT/zsh/"
cp docs/before-after.png "$OUT/docs/"
chmod +x "$OUT/install.sh" "$OUT/uninstall.sh" "$OUT/Install MyanTerm.command" "$OUT/zsh/build.sh"
(cd dist && ditto -c -k --norsrc --noextattr --noqtn --keepParent "$NAME" "$NAME.zip")
shasum -a 256 "dist/$NAME.zip"
