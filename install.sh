#!/bin/bash
# MyanTerm installer: natural Burmese text in macOS Terminal.app.
#
#   ./install.sh                 install fonts + Terminal profile, ask about making it the default
#   ./install.sh --default       ...and make it the default profile without asking
#   ./install.sh --no-default    ...and leave the default profile alone
#   ./install.sh --with-zsh      also build zsh with Terminal-matching Burmese widths
#                                (needs Xcode Command Line Tools; takes a few minutes)
#
# What it changes: copies MyanTerm-Regular.ttf and MyanTerm-Bold.ttf into ~/Library/Fonts,
# adds a Terminal profile named "MyanTerm" (existing profiles are not modified), and, if you
# agree, makes that profile the default. Undo everything with ./uninstall.sh.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
FONT_DIR="$HOME/Library/Fonts"
ZSH_PREFIX="$HOME/.local/myanterm-zsh"
MAKE_DEFAULT=ask
WITH_ZSH=0
for arg in "$@"; do
    case "$arg" in
        --default) MAKE_DEFAULT=yes ;;
        --no-default) MAKE_DEFAULT=no ;;
        --with-zsh) WITH_ZSH=1 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }

[ "$(uname -s)" = Darwin ] || { say "MyanTerm is for macOS Terminal.app."; exit 1; }

# 1. fonts
mkdir -p "$FONT_DIR"
rm -f "$FONT_DIR"/MyanTerm-Regular.ttf "$FONT_DIR"/MyanTerm-Bold.ttf
cp "$HERE"/fonts/MyanTerm-Regular.ttf "$HERE"/fonts/MyanTerm-Bold.ttf "$FONT_DIR"/
say "Installed fonts into $FONT_DIR"

# 2. Terminal profile
term() { osascript -e "tell application \"Terminal\" to $1" 2>/dev/null; }
if term 'get name of settings sets' | tr ',' '\n' | sed 's/^ *//' | grep -qx MyanTerm; then
    term 'set font name of settings set "MyanTerm" to "MyanTerm-Regular"' >/dev/null
    say "Updated the existing Terminal profile \"MyanTerm\""
else
    open "$HERE/MyanTerm.terminal"      # Terminal imports it and opens one window with it
    for _ in $(seq 1 20); do
        term 'get name of settings sets' | grep -q MyanTerm && break
        sleep 0.5
    done
    say "Added the Terminal profile \"MyanTerm\" (MyanTerm 13pt)"
fi

# 3. default profile
if [ "$MAKE_DEFAULT" = ask ]; then
    if [ -t 0 ]; then
        read -r -p "Use MyanTerm for new Terminal windows? [Y/n] " answer
        case "$answer" in [nN]*) MAKE_DEFAULT=no ;; *) MAKE_DEFAULT=yes ;; esac
    else
        MAKE_DEFAULT=no
    fi
fi
if [ "$MAKE_DEFAULT" = yes ]; then
    term 'set default settings to settings set "MyanTerm"' >/dev/null
    term 'set startup settings to settings set "MyanTerm"' >/dev/null
    say "MyanTerm is now the default profile (Terminal > Settings > Profiles to change it)"
fi

# 4. optional: zsh with Terminal-matching widths for editing Burmese at the prompt
if [ "$WITH_ZSH" = 1 ]; then
    if ! xcode-select -p >/dev/null 2>&1; then
        say "Building zsh needs the Xcode Command Line Tools: run  xcode-select --install  and then"
        say "run this installer again with --with-zsh."
    else
        say "Building zsh (a few minutes)..."
        RUN_CHECK=0 "$HERE"/zsh/build.sh "$ZSH_PREFIX" > "$HERE"/zsh/build.log 2>&1 \
            || { say "zsh build failed; see $HERE/zsh/build.log"; exit 1; }
        say "Built $ZSH_PREFIX/bin/zsh"
        say "To use it: Terminal > Settings > General > \"Shells open with\" > Command (complete path):"
        say "    $ZSH_PREFIX/bin/zsh"
        say "New tabs then edit Burmese at the prompt without the cursor drifting."
    fi
fi

# 5. check that this Terminal measures Burmese the way the font expects
if [ "${TERM_PROGRAM:-}" = Apple_Terminal ] && [ -t 0 ] && [ -t 1 ]; then
    col() { local r; printf '\033[6n' > /dev/tty; IFS='[;' read -r -s -d R _ _ r < /dev/tty; printf '%s' "$r"; }
    saved=$(stty -g < /dev/tty)
    stty -echo -icanon < /dev/tty
    printf '\r'; c0=$(col); printf 'ကျေး'; c1=$(col); printf '\r\033[2K'
    stty "$saved" < /dev/tty
    if [ $((c1 - c0)) -eq 4 ]; then
        say "Check passed: this Terminal gives Burmese the cell widths MyanTerm is built for."
    else
        say "Warning: this Terminal measured ကျေး as $((c1 - c0)) cells (MyanTerm expects 4)."
        say "Burmese may not line up correctly on this macOS version."
    fi
fi

say "Done. Open a new Terminal window to see it."
