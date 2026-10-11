#!/bin/sh
# Reproducible build of zsh 5.9.2 with Terminal.app-compatible Myanmar widths.
#
# Usage:  build.sh [PREFIX]
#   PREFIX defaults to <this dir>/prefix.  zsh compiles PREFIX into the binary
#   (fpath, module_path), so build with the final location you intend to use;
#   do not just copy the installed tree somewhere else.
#
# Steps: download official tarball (zsh.org) -> verify SHA-256 (and GPG if
# gpg is available) -> fresh extract -> apply myanmar-width.patch ->
# configure (flags mirror Apple's /bin/zsh: unicode9 widths, multibyte,
# /etc as etcdir, Apple site-function dirs) -> make -> make check (optional)
# -> make install -> width self-test.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PREFIX=${1:-$HERE/prefix}
VER=5.9.2
TARBALL=zsh-$VER.tar.xz
SHA256=36fa734374b44783582cec09bcd67822e2f992c779ec1624ab5596df078d2f81
URL=https://www.zsh.org/pub/$TARBALL
SRC=$HERE/src
BUILD=$HERE/build
PATCH=$HERE/myanmar-width.patch
JOBS=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
RUN_CHECK=${RUN_CHECK:-1}

mkdir -p "$SRC"
cd "$SRC"
if [ ! -f "$TARBALL" ]; then
    curl -fsSLO "$URL"
    curl -fsSLO "$URL.asc" || true
fi
echo "$SHA256  $TARBALL" | shasum -a 256 -c -

# Optional signature check against the zsh maintainers' keyring.
if command -v gpg >/dev/null 2>&1; then
    [ -f zsh-keyring.asc ] || curl -fsSLO https://www.zsh.org/pub/zsh-keyring.asc
    [ -f "$TARBALL.asc" ] || curl -fsSLO "$URL.asc"
    GNUPGHOME=$SRC/gnupg; export GNUPGHOME
    mkdir -p "$GNUPGHOME"; chmod 700 "$GNUPGHOME"
    gpg --quiet --import zsh-keyring.asc 2>/dev/null || true
    gpg --verify "$TARBALL.asc" "$TARBALL" 2>&1 | grep -E 'Good signature|BAD signature' || {
        echo "GPG verification failed" >&2; exit 1; }
fi

# Fresh tree every time.
rm -rf "$BUILD"
mkdir -p "$BUILD"
tar -C "$BUILD" -xf "$SRC/$TARBALL"
cd "$BUILD/zsh-$VER"
patch -p1 < "$PATCH"

# pcre module only if Homebrew's pcre2 is present (Apple's zsh ships zsh/pcre).
PCRE_FLAG=--disable-pcre
if [ -x /opt/homebrew/opt/pcre2/bin/pcre2-config ]; then
    PCRE_FLAG=--enable-pcre
    PCRE_CONFIG=/opt/homebrew/opt/pcre2/bin/pcre2-config; export PCRE_CONFIG
fi

# Keep Homebrew/conda/etc. out of the toolchain lookups.
PATH=/usr/bin:/bin:/usr/sbin:/sbin; export PATH
unset CPPFLAGS LDFLAGS CFLAGS LIBS 2>/dev/null || true

./configure \
    --prefix="$PREFIX" \
    --enable-etcdir=/etc \
    --enable-additional-fpath=/usr/share/zsh/site-functions \
    --enable-multibyte \
    --enable-unicode9 \
    --enable-maildir-support \
    --enable-cap \
    --disable-gdbm \
    "$PCRE_FLAG" \
    --with-tcsetpgrp \
    > "$HERE/configure.log" 2>&1 || { tail -40 "$HERE/configure.log"; exit 1; }

grep -q '^#define ENABLE_UNICODE9 1' config.h
grep -q '^#define MULTIBYTE_SUPPORT 1' config.h

make -j"$JOBS" > "$HERE/make.log" 2>&1 || { tail -60 "$HERE/make.log"; exit 1; }

if [ "$RUN_CHECK" = 1 ]; then
    # Full upstream test suite; result summary goes to check.log.
    mkdir -p "$HERE/tmp"
    TMPPREFIX="$HERE/tmp/zsh" make check > "$HERE/check.log" 2>&1 || true
    tail -5 "$HERE/check.log"
fi

make install.bin install.modules install.fns install.man > "$HERE/install.log" 2>&1 \
    || { tail -40 "$HERE/install.log"; exit 1; }

ZSH_BIN=$PREFIX/bin/zsh
echo "installed: $ZSH_BIN ($("$ZSH_BIN" --version))"

# Self-test: expected Terminal.app widths 2 4 1 7 4 2, with and without
# COMBINING_CHARS.
LC_ALL=en_US.UTF-8 "$ZSH_BIN" -f -c '
  for s in ကာ ကျေး ကို မင်္ဂလာပါ ကြော် နေ့; do print -n "${(m)#s} "; done; print
  setopt combiningchars
  for s in ကာ ကျေး ကို မင်္ဂလာပါ ကြော် နေ့; do print -n "${(m)#s} "; done; print'
