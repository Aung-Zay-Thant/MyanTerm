#!/bin/bash
# MyanTerm installer: natural Burmese text in macOS Terminal.app.
#
#   ./install.sh                 install, and ask whether every Terminal window should use MyanTerm
#   ./install.sh --default       ...and do that without asking
#   ./install.sh --no-default    ...and only add the MyanTerm profile
#   ./install.sh --no-zsh        don't set up the zsh that fixes typing Burmese at the prompt
#   ./install.sh --edition=26    install the fonts made for macOS 26 and earlier (or =27); the default
#                                follows this Mac's macOS version
#
# What it changes:
#   ~/Library/Fonts/MyanTerm-Regular.ttf, MyanTerm-Bold.ttf   the fonts (Terminal before macOS 27 draws
#                                                              Burmese narrower, so it gets its own edition)
#   ~/.local/myanterm-zsh/bin/zsh                              zsh 5.9.2 with Terminal's Burmese widths
#   Terminal profile "MyanTerm"                                MyanTerm 13pt, starts that zsh as a login shell
# If you choose to use MyanTerm in every window (the default answer), MyanTerm also becomes the
# default profile and Terminal > Settings > General > "Shells open with" is set to that zsh, so
# typing Burmese works in windows of every profile. Your login shell and dotfiles are not changed.
# Undo everything with ./uninstall.sh.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
FONT_DIR="$HOME/Library/Fonts"
ZSH_DIR="$HOME/.local/myanterm-zsh"
ZSH_BIN="$ZSH_DIR/bin/zsh"
MAKE_DEFAULT=ask
WITH_ZSH=1
EDITION=
for arg in "$@"; do
    case "$arg" in
        --default) MAKE_DEFAULT=yes ;;
        --no-default) MAKE_DEFAULT=no ;;
        --no-zsh) WITH_ZSH=0 ;;
        --with-zsh) WITH_ZSH=1 ;;   # accepted for compatibility with 1.0
        --edition=26|--edition=27) EDITION=${arg#--edition=} ;;
        -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
PREFS=com.apple.Terminal
if [ -n "${MYANTERM_TEST_PROFILE_OUT:-}" ]; then   # test mode: don't touch Terminal or its settings
    PREFS=${MYANTERM_TEST_PREFS:?test mode needs MYANTERM_TEST_PREFS}
    term() { printf 'test: osascript %s\n' "$1" >&2; }
else
    term() { osascript -e "tell application \"Terminal\" to $1" 2>/dev/null; }
fi
has_profile() { term 'get name of settings sets' | tr ',' '\n' | sed 's/^ *//' | grep -qx "$1"; }

[ "$(uname -s)" = Darwin ] || { say "MyanTerm is for macOS Terminal.app."; exit 1; }

# 1. fonts (remove, then copy: a fresh file, not an in-place overwrite of a font Terminal has loaded).
#    Terminal before macOS 27 gives ာ ေ ျ ြ း a cell but draws them with no width, so Burmese
#    gets about 2/3 of the room there: those Macs get the narrower edition in fonts/macos26.
macos=${MYANTERM_TEST_MACOS:-$(sw_vers -productVersion 2>/dev/null || echo 0)}
if [ -z "$EDITION" ]; then
    if [ "${macos%%.*}" -ge 27 ] 2>/dev/null; then EDITION=27; else EDITION=26; fi
fi
SRC_FONTS="$HERE/fonts"
[ "$EDITION" = 26 ] && SRC_FONTS="$HERE/fonts/macos26"
mkdir -p "$FONT_DIR"
upgrade=no
if [ -f "$FONT_DIR/MyanTerm-Regular.ttf" ] && ! cmp -s "$FONT_DIR/MyanTerm-Regular.ttf" "$SRC_FONTS/MyanTerm-Regular.ttf"; then
    upgrade=yes
fi
rm -f "$FONT_DIR"/MyanTerm-Regular.ttf "$FONT_DIR"/MyanTerm-Bold.ttf
cp "$SRC_FONTS"/MyanTerm-Regular.ttf "$SRC_FONTS"/MyanTerm-Bold.ttf "$FONT_DIR"/
if [ "$EDITION" = 26 ]; then
    say "Installed fonts into $FONT_DIR (edition for macOS 26 and earlier; this Mac: macOS $macos)"
    say "  After upgrading this Mac to macOS 27 or later, run this installer again."
else
    say "Installed fonts into $FONT_DIR"
fi

# 2. zsh with Terminal's Burmese widths (only used by the MyanTerm profile)
zsh_ok=0
if [ "$WITH_ZSH" = 1 ]; then
    login_shell=$(dscl . -read "/Users/$(id -un)" UserShell 2>/dev/null | awk '{print $2}')
    if [ ! -f "$HERE/bin/zsh" ]; then
        say "Note: this package has no bin/zsh; skipping the typing fix."
    elif [ "${login_shell##*/}" != zsh ]; then
        say "Note: your login shell is ${login_shell:-unknown}, not zsh; skipping the zsh typing fix."
    elif [[ "$HOME" == *" "* ]]; then
        say "Note: your home folder path contains a space; skipping the zsh typing fix."
    else
        mkdir -p "$ZSH_DIR/bin"
        cp "$HERE/bin/zsh" "$ZSH_BIN.new" && mv -f "$ZSH_BIN.new" "$ZSH_BIN"
        chmod 755 "$ZSH_BIN"
        xattr -d com.apple.quarantine "$ZSH_BIN" 2>/dev/null || true
        widths=$(LC_ALL=en_US.UTF-8 "$ZSH_BIN" -fc 'for s in ကာ ကျေး ကို မင်္ဂလာပါ; do print -n "${(m)#s} "; done' 2>/dev/null || true)
        if [ "$widths" = "2 4 1 7 " ]; then
            zsh_ok=1
            say "Installed $ZSH_BIN (fixes typing Burmese at the prompt)"
        else
            say "Note: the bundled zsh did not pass its self-test on this Mac; skipping the typing fix."
        fi
    fi
fi

# 3. Terminal profile "MyanTerm" (replaces an older one; other profiles untouched)
tmpdir=$(mktemp -d -t myanterm)
profile="$tmpdir/MyanTerm.terminal"
cp "$HERE/MyanTerm.terminal" "$profile"
if [ "$zsh_ok" = 1 ]; then
    plutil -replace CommandString -string "$ZSH_BIN -l" "$profile"
    plutil -replace RunCommandAsShell -bool true "$profile"
fi
was_default=no
if [ -z "${MYANTERM_TEST_PROFILE_OUT:-}" ] && has_profile MyanTerm; then
    [ "$(term 'get name of default settings')" = MyanTerm ] && was_default=yes
    [ "$was_default" = yes ] && term 'set default settings to settings set "Basic"' >/dev/null
    [ "$(term 'get name of startup settings')" = MyanTerm ] && term 'set startup settings to settings set "Basic"' >/dev/null
    term 'delete settings set "MyanTerm"' >/dev/null || true
fi
if [ -n "${MYANTERM_TEST_PROFILE_OUT:-}" ]; then   # test hook: write the profile, don't import it
    cp "$profile" "$MYANTERM_TEST_PROFILE_OUT"
else
    open "$profile"      # Terminal imports the profile and opens one window with it
    for _ in $(seq 1 20); do has_profile MyanTerm && break; sleep 0.5; done
fi
say "Added the Terminal profile \"MyanTerm\" (MyanTerm 13pt$([ "$zsh_ok" = 1 ] && printf ', with the fixed zsh'))"

# 4. every window: MyanTerm as the default profile, and the fixed zsh for all profiles
#    (windows of other profiles would otherwise run /bin/zsh, which garbles Burmese while typing)
if [ "$MAKE_DEFAULT" = ask ]; then
    if [ "$was_default" = yes ]; then
        MAKE_DEFAULT=yes
    elif [ -t 0 ]; then
        read -r -p "Use MyanTerm in every Terminal window? [Y/n] " answer
        case "$answer" in [nN]*) MAKE_DEFAULT=no ;; *) MAKE_DEFAULT=yes ;; esac
    else
        MAKE_DEFAULT=no
    fi
fi
shell_changed=no
every_window=no
if [ "$MAKE_DEFAULT" = yes ]; then
    term 'set default settings to settings set "MyanTerm"' >/dev/null
    term 'set startup settings to settings set "MyanTerm"' >/dev/null
    say "MyanTerm is now the default profile (Terminal > Settings > Profiles to change it)"
    if [ "$zsh_ok" = 1 ]; then
        current=$(defaults read "$PREFS" Shell 2>/dev/null || true)
        case "$current" in
            "$ZSH_BIN") every_window=yes ;;
            ""|/bin/zsh)
                defaults write "$PREFS" Shell -string "$ZSH_BIN"
                shell_changed=yes; every_window=yes
                say "Terminal now opens every window with $ZSH_BIN"
                say "  (Terminal > Settings > General > \"Shells open with\" changes this back)"
                ;;
            *)
                say "Note: Terminal is set to open windows with $current, so typing Burmese"
                say "works only in MyanTerm windows (Shell > New Window > MyanTerm)."
                ;;
        esac
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

if [ "$upgrade" = yes ] || [ "$shell_changed" = yes ]; then
    say ""
    say "IMPORTANT: quit Terminal now (Terminal > Quit Terminal, or Command-Q) and open it again."
    [ "$upgrade" = yes ] && say "Terminal keeps the old MyanTerm font in memory until it restarts."
    [ "$shell_changed" = yes ] && say "Windows that are already open keep running /bin/zsh until then."
    say ""
fi
if [ "$every_window" = yes ]; then
    say "Done. Burmese works in every Terminal window."
elif [ "$MAKE_DEFAULT" = yes ]; then
    say "Done. New Terminal windows use MyanTerm."
else
    say "Done. Burmese works in windows that use the MyanTerm profile (Shell > New Window > MyanTerm)."
fi
