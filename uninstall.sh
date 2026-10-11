#!/bin/bash
# Remove MyanTerm: fonts, the "MyanTerm" Terminal profile, and the optional zsh build.
set -uo pipefail

ZSH_PREFIX="$HOME/.local/myanterm-zsh"
term() { osascript -e "tell application \"Terminal\" to $1" 2>/dev/null; }

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

if [ -d "$ZSH_PREFIX" ]; then
    if [ "$(defaults read com.apple.Terminal Shell 2>/dev/null)" = "$ZSH_PREFIX/bin/zsh" ]; then
        echo "First set Terminal > Settings > General > \"Shells open with\" back to \"Default login shell\","
        echo "then run:  rm -rf \"$ZSH_PREFIX\""
    else
        rm -rf "$ZSH_PREFIX" && echo "Removed $ZSH_PREFIX"
    fi
fi
