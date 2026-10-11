#!/bin/bash
# Remove MyanTerm: fonts, the "MyanTerm" Terminal profile and the bundled zsh.
set -uo pipefail

ZSH_DIR="$HOME/.local/myanterm-zsh"
PREFS=com.apple.Terminal
if [ -n "${MYANTERM_TEST_PREFS:-}" ]; then   # test mode: don't touch Terminal or its settings
    PREFS=$MYANTERM_TEST_PREFS
    term() { printf 'test: osascript %s\n' "$1" >&2; }
else
    term() { osascript -e "tell application \"Terminal\" to $1" 2>/dev/null; }
fi

# default/startup profile back to Basic if they point at MyanTerm
[ "$(term 'get name of default settings')" = MyanTerm ] && term 'set default settings to settings set "Basic"' >/dev/null
[ "$(term 'get name of startup settings')" = MyanTerm ] && term 'set startup settings to settings set "Basic"' >/dev/null
if term 'get name of settings sets' | tr ',' '\n' | sed 's/^ *//' | grep -qx MyanTerm; then
    term 'delete settings set "MyanTerm"' >/dev/null \
        && echo "Removed the Terminal profile \"MyanTerm\"" \
        || echo "Remove the profile \"MyanTerm\" in Terminal > Settings > Profiles (select it, press -)"
fi

rm -f "$HOME/Library/Fonts/MyanTerm-Regular.ttf" "$HOME/Library/Fonts/MyanTerm-Bold.ttf"
echo "Removed the MyanTerm fonts"

if [ "$(defaults read "$PREFS" Shell 2>/dev/null)" = "$ZSH_DIR/bin/zsh" ]; then
    defaults delete "$PREFS" Shell \
        && echo "Terminal opens windows with your login shell again"
fi
if [ -d "$ZSH_DIR" ]; then
    rm -rf "$ZSH_DIR" && echo "Removed $ZSH_DIR"
fi
echo "Quit Terminal (Command-Q) and open it again to finish."
