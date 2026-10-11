#!/bin/sh
# Portable build of zsh 5.9.2 with Terminal.app's Myanmar widths, for the
# MyanTerm release zip: one universal (arm64 + x86_64) binary that runs from
# any directory and needs no Xcode tools on the user's Mac.
#
# Usage:  build-portable.sh [WORKDIR]
#   WORKDIR (default: $TMPDIR/myanterm-zsh-portable) holds the download cache,
#   build tree and logs.  The result is written to <this dir>/dist/zsh.
#   Environment: RUN_CHECK=0 skips zsh's own test suite (make check);
#   REQUIRE_GPG=1 fails instead of warning when gpg is not installed.
#
# How it differs from build.sh (which installs into a PREFIX):
#   * every module (zle, complete, complist, ...) is linked into the binary
#     (--disable-dynamic + config.modules), so there is no module directory;
#     a small fix to zsh's module-list generator (below) registers the
#     dependencies of modules that are only loaded on request;
#   * nothing points into a build or install prefix: --prefix=/usr, and the
#     default fpath uses macOS's own function directories:
#       /usr/local/share/zsh/site-functions   (added by configure, as in Apple's zsh)
#       /usr/share/zsh/site-functions
#       /usr/share/zsh/5.9/functions          Apple's zsh 5.9    (macOS 13.3 and later)
#       /usr/share/zsh/5.8.1/functions        Apple's zsh 5.8.1  (macOS 12.4 - 13.2)
#       /usr/share/zsh/5.8/functions          Apple's zsh 5.8    (macOS 11 - 12.3)
#       /usr/share/zsh/5.9.2/functions        stock layout for this version (in case
#                                             a future macOS ships zsh 5.9.2)
#     Only one of the version directories exists on a given macOS (they are on
#     the sealed system volume), so the first three entries match /bin/zsh.
#   * universal binary from a single configure run (like Apple's own build);
#     MACHTYPE is made per-architecture in config.h, as Apple's zsh does.
#   * minimum macOS 11.0, the first release that runs on Apple silicon, so both
#     slices share one floor.  Only libSystem, libncurses and libiconv from
#     /usr/lib are linked; the build fails if any API newer than 11.0 is used.
#   * Apple's extra flags for /bin/zsh: -DUSE_GETCWD, FUNCNEST limit 700.
#   * pcre (needs a non-system library) and gdbm are left out.
#   * stripped and ad-hoc code signed.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:-${TMPDIR:-/tmp}/myanterm-zsh-portable}
mkdir -p "$WORK"
WORK=$(cd "$WORK" && pwd -P)
OUT=$HERE/dist/zsh
VER=5.9.2
TARBALL=zsh-$VER.tar.xz
SHA256=36fa734374b44783582cec09bcd67822e2f992c779ec1624ab5596df078d2f81
URL=https://www.zsh.org/pub/$TARBALL
# zsh 5.9.2 is signed by dana <dana@dana.is>
SIGNER_FPR=7CA7ECAAF06216B90F894146ACF8146CAE8CBBC4
PATCH=$HERE/myanmar-width.patch
MIN_MACOS=11.0
ARCHS="arm64 x86_64"
NOT_BUILT="zsh/pcre zsh/db/gdbm"
FNDIRS="/usr/share/zsh/5.9/functions,/usr/share/zsh/5.8.1/functions,/usr/share/zsh/5.8/functions"
SRC=$WORK/src
BUILD=$WORK/build
LOGS=$WORK/logs
JOBS=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
RUN_CHECK=${RUN_CHECK:-1}

die() { echo "build-portable: $*" >&2; exit 1; }
[ "$(uname -s)" = Darwin ] || die "macOS only"
[ -f "$PATCH" ] || die "missing $PATCH"
GPG=$(command -v gpg 2>/dev/null || true)

# Keep Homebrew/ccache/swiftly/conda out of the toolchain.
PATH=/usr/bin:/bin:/usr/sbin:/sbin; export PATH
unset CPPFLAGS CFLAGS LDFLAGS LIBS CPP CC TOOLCHAINS SDKROOT 2>/dev/null || true

# ---- 1. source: download, SHA-256, GPG ------------------------------------
mkdir -p "$SRC" "$LOGS"
cd "$SRC"
[ -f "$TARBALL" ] || curl -fsSLO "$URL"
echo "$SHA256  $TARBALL" | shasum -a 256 -c - || die "SHA-256 mismatch for $TARBALL"
if [ -n "$GPG" ]; then
    [ -f "$TARBALL.asc" ] || curl -fsSLO "$URL.asc"
    [ -f zsh-keyring.asc ] || curl -fsSLO https://www.zsh.org/pub/zsh-keyring.asc
    GNUPGHOME=$SRC/gnupg; export GNUPGHOME
    mkdir -p "$GNUPGHOME"; chmod 700 "$GNUPGHOME"
    "$GPG" --batch --quiet --import zsh-keyring.asc 2>/dev/null || true
    status=$("$GPG" --batch --status-fd 1 --verify "$TARBALL.asc" "$TARBALL" 2>/dev/null) \
        || die "GPG signature check failed for $TARBALL"
    echo "$status" | grep -q "^\[GNUPG:\] VALIDSIG .*$SIGNER_FPR" \
        || die "$TARBALL is not signed by $SIGNER_FPR"
    echo "GPG: good signature from $SIGNER_FPR"
    "$(dirname "$GPG")/gpgconf" --kill all >/dev/null 2>&1 || true   # no stray gpg-agent
    unset GNUPGHOME
elif [ "${REQUIRE_GPG:-0}" = 1 ]; then
    die "gpg not found (REQUIRE_GPG=1)"
else
    echo "note: gpg not found; relying on the pinned SHA-256 only"
fi

# ---- 2. fresh tree + patch ----------------------------------------------
rm -rf "$BUILD"
mkdir -p "$BUILD"
tar -C "$BUILD" -xf "$SRC/$TARBALL"
cd "$BUILD/zsh-$VER"
patch -p1 < "$PATCH" > "$LOGS/patch.log"

# Build-system fix for an all-static zsh: Src/mkbltnmlst.sh registers module
# dependencies (add_dep) for load=yes modules and for dynamic load=no ones,
# but not for static load=no ones.  Without this, "zmodload zsh/deltochar"
# boots deltochar before zsh/zle, and zsh/zftp before zsh/net/tcp: both
# segfault.  (Apple's dynamic zsh fails those two with a dlopen error.)
patch -p1 >> "$LOGS/patch.log" <<'EOF'
--- a/Src/mkbltnmlst.sh
+++ b/Src/mkbltnmlst.sh
@@ -100,6 +100,26 @@
     fi
 done

+# Portable (all-static) build: the same for linked-in modules with load=no.
+# Upstream registers their dependencies nowhere, so "zmodload zsh/deltochar"
+# would boot deltochar before zsh/zle (and zsh/zftp before zsh/net/tcp) and
+# crash.
+st_mods="`grep ' link=static .* load=no' $CFMOD | \
+          sed -e '/^#/d' -e 's/ .*/ /' -e 's/^name=/ /'`"
+
+for mod in $st_mods; do
+    modfile="`grep '^name='$mod' ' $CFMOD | \
+              sed -e 's/^.* modfile=//' -e 's/ .*//'`"
+    unset moddeps
+    . $srcdir/../$modfile
+    if test -n "$moddeps"; then
+        echo "/* linked-in module \`$mod' (load=no) */"
+        for dep in $moddeps; do
+          echo "  add_dep(\"$mod\", \"$dep\");"
+        done
+    fi
+done
+
 echo
 done_mods=" "
 for bin_mod in $bin_mods; do
EOF

# ---- 3. configure (one run for both architectures) -----------------------
CC=/usr/bin/clang
SDKROOT=$(xcrun --sdk macosx --show-sdk-path)
MACOSX_DEPLOYMENT_TARGET=$MIN_MACOS
ARCHFLAGS=$(for a in $ARCHS; do printf -- '-arch %s ' "$a"; done)
# -arch goes into CFLAGS/LDFLAGS only: "clang -E" (CPP) rejects several -arch.
CFLAGS="-O2 $ARCHFLAGS-mmacosx-version-min=$MIN_MACOS -Werror=unguarded-availability -Werror=unguarded-availability-new"
LDFLAGS="$ARCHFLAGS-mmacosx-version-min=$MIN_MACOS"
CPPFLAGS="-DUSE_GETCWD"
export CC SDKROOT MACOSX_DEPLOYMENT_TARGET CFLAGS LDFLAGS CPPFLAGS
echo "toolchain: $($CC --version | head -1); SDK $(xcrun --sdk macosx --show-sdk-version); macOS >= $MIN_MACOS; $ARCHS"

./configure \
    --prefix=/usr \
    --enable-etcdir=/etc \
    --enable-site-fndir=/usr/share/zsh/site-functions \
    --enable-additional-fpath="$FNDIRS" \
    --enable-multibyte \
    --enable-unicode9 \
    --enable-maildir-support \
    --enable-cap \
    --enable-max-function-depth=700 \
    --disable-dynamic \
    --disable-gdbm \
    --disable-pcre \
    --with-tcsetpgrp \
    > "$LOGS/configure.log" 2>&1 || { tail -40 "$LOGS/configure.log"; die "configure failed"; }

grep -q '^#define ENABLE_UNICODE9 1' config.h || die "unicode9 not enabled"
grep -q '^#define MULTIBYTE_SUPPORT 1' config.h || die "multibyte not enabled"
! grep -q '^#define DYNAMIC ' config.h || die "dynamic loading still enabled"
grep -q '^#define MAX_FUNCTION_DEPTH 700' config.h || die "function depth not set"

# Configure ran its test programs as arm64.  The only architecture-specific
# result is MACHTYPE; make it per slice (Apple's zsh does the same).
grep -q '^#define MACHTYPE ' config.h || die "MACHTYPE not found in config.h"
sed -i '' '/^#define MACHTYPE /c\
#if defined(__x86_64__)\
#define MACHTYPE "x86_64"\
#elif defined(__arm64__) || defined(__aarch64__)\
#define MACHTYPE "arm64"\
#else\
#error "unexpected architecture"\
#endif
' config.h

# The other results that configure got by running test programs are libc/OS
# properties (the same libSystem on Intel), except these size facts, which
# the compiler checks here for every slice.
cat > archcheck.c <<'EOF'
#include "config.h"
#include <sys/types.h>
#include <sys/resource.h>
#ifdef LONG_IS_64_BIT
_Static_assert(sizeof(long) == 8, "LONG_IS_64_BIT");
#else
_Static_assert(sizeof(long) != 8, "LONG_IS_64_BIT");
#endif
#ifdef RLIM_T_IS_UNSIGNED
_Static_assert((rlim_t)-1 > 0, "RLIM_T_IS_UNSIGNED");
#endif
#ifndef RLIM_T_IS_LONG_LONG
_Static_assert(sizeof(rlim_t) <= sizeof(long), "rlim_t longer than long");
#endif
_Static_assert(sizeof(off_t) == 8 && sizeof(ino_t) == 8, "64-bit off_t/ino_t");
EOF
$CC $CFLAGS -I. -fsyntax-only archcheck.c || die "config.h does not fit every architecture"
rm -f archcheck.c

# Link every module into the binary.  With --disable-dynamic, configure marks
# "either" modules static but "dynamic" ones link=no (and forces load=no);
# make those static too and restore each module's load= flag from its .mdd
# (e.g. zsh/watch must autoload: it provides the "log" builtin that Apple's
# /etc/zshrc disables).  auto=no marks the lines as hand-edited.
awk -v skip=" $NOT_BUILT " '
/^name=/ && / link=no / {
    split($1, n, "="); split($2, f, "=")
    if (index(skip, " " n[2] " ") == 0) {
        load = "no"
        while ((getline l < f[2]) > 0) if (l ~ /^load=/) { sub(/^load=/, "", l); load = l }
        close(f[2])
        sub(/ link=no /, " link=static "); sub(/ auto=yes /, " auto=no ")
        sub(/ load=[a-z]+/, " load=" load)
    }
}
{ print }' config.modules > config.modules.new
mv config.modules.new config.modules
grep '^name=' config.modules | sed 's/ functions=.*//' > "$LOGS/config.modules.txt"
STATIC_MODULES=$(grep '^name=' config.modules | grep ' link=static ' | sed 's/^name=\([^ ]*\) .*/\1/' | grep -v '^zsh/main$' | tr '\n' ' ')
grep -q ' link=dynamic ' config.modules && die "config.modules still has dynamic modules"
for m in $NOT_BUILT; do grep -q "^name=$m .* link=no " config.modules || die "$m should not be built"; done
echo "static modules: $STATIC_MODULES"

# ---- 4. build ------------------------------------------------------------
make -j"$JOBS" > "$LOGS/make.log" 2>&1 || { tail -60 "$LOGS/make.log"; die "make failed"; }
if grep -n -E 'only available on macOS|\[-W(error,-W)?unguarded-availability' "$LOGS/make.log"; then
    die "uses an API newer than macOS $MIN_MACOS"
fi

if [ "$RUN_CHECK" = 1 ]; then
    mkdir -p "$WORK/tmp"
    TMPPREFIX="$WORK/tmp/zsh" make check > "$LOGS/check.log" 2>&1 || true
    grep -E '^[0-9]+ (successful|failed|skipped)' "$LOGS/check.log" || tail -5 "$LOGS/check.log"
fi

# ---- 5. strip and sign (staged in WORKDIR until the self-test passes) -----
STAGE=$WORK/stage/zsh
rm -rf "$WORK/stage"; mkdir -p "$WORK/stage"
cp Src/zsh "$STAGE"
strip "$STAGE"
# Drop the linker's signature first: it names a random temporary file, and
# re-signing in place would leave pieces of it in the padding, so two builds
# would differ.  The file name "zsh" sets the default signing identifier.
codesign --remove-signature "$STAGE"
codesign --force --sign - "$STAGE" > "$LOGS/codesign.log" 2>&1 || { cat "$LOGS/codesign.log"; die "codesign failed"; }
chmod 755 "$STAGE"

# ---- 6. self-test ----------------------------------------------------------
OUT_FINAL=$OUT; OUT=$STAGE
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1: $2"; else echo "FAIL $1: got '$2', want '$3'"; fail=1; fi; }

check archs "$(lipo -archs "$OUT" | tr ' ' '\n' | sort | tr '\n' ' ')" \
            "$(echo $ARCHS | tr ' ' '\n' | sort | tr '\n' ' ')"
for a in $ARCHS; do
    check "$a minos" "$(otool -arch "$a" -l "$OUT" | awk '$1 == "minos" { print $2 }')" "$MIN_MACOS"
    libs=$(otool -arch "$a" -L "$OUT" | sed 1d | awk '{ print $1 }' | tr '\n' ' ')
    nonsys=$(echo "$libs" | tr ' ' '\n' | grep -v -e '^$' -e '^/usr/lib/' -e '^/System/Library/' || true)
    check "$a non-system libraries" "${nonsys:-none}" none
done
check "build paths in binary" "$(strings -a "$OUT" | grep -c -e "$WORK" -e "$HERE" || true)" 0
codesign --verify --strict "$OUT" 2>/dev/null && check "ad-hoc signature" valid valid \
    || check "ad-hoc signature" invalid valid

T=$(mktemp -d "$WORK/selftest.XXXXXX")
run() { env -i HOME="$T" ZDOTDIR="$T" TMPDIR="$T/" LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8 TERM=xterm-256color \
        PATH=/usr/bin:/bin "$OUT" "$@"; }
check version "$(run -fc 'print -r -- $ZSH_VERSION $MACHTYPE')" "$VER $(uname -m)"
W='for s in ကာ ကျေး ကို မင်္ဂလာပါ ကြော် နေ့; do print -n "${(m)#s} "; done'
check widths "$(run -fc "$W")" "2 4 1 7 4 2 "
check "widths (combiningchars)" "$(run -fc "setopt combiningchars; $W")" "2 4 1 7 4 2 "
# each module on its own in a fresh subshell, so missing dependencies show up
check "modules (no module directory)" "$(run -fc 'module_path=(); bad=(); for m in '"$STATIC_MODULES"'; do ( zmodload $m ) >/dev/null 2>&1 || bad+=$m; done; print -r -- "${bad:-none}"')" none
check "module dependencies" "$(run -fc 'zmodload zsh/deltochar && zmodload zsh/zftp && print -r -- ${modules[zsh/zle]} ${modules[zsh/net/tcp]}')" "loaded loaded"
check fpath "$(run -fc 'print -r -- ${(j<:>)fpath}')" \
    "/usr/local/share/zsh/site-functions:/usr/share/zsh/site-functions:$(echo "$FNDIRS" | tr ',' ':'):/usr/share/zsh/$VER/functions"
check compinit "$(run -fc 'autoload -Uz compinit && compinit -D -u && (( ${#_comps} > 500 )) && print ok')" ok
rm -rf "$T"

[ "$fail" = 0 ] || die "self-test failed; $OUT_FINAL left unchanged"

# ---- 7. install into dist/ -------------------------------------------------
mkdir -p "$HERE/dist"
cp "$STAGE" "$OUT_FINAL.tmp" && mv -f "$OUT_FINAL.tmp" "$OUT_FINAL"
codesign --verify --strict "$OUT_FINAL" || die "signature broken after copy"
echo "built $OUT_FINAL ($(stat -f %z "$OUT_FINAL") bytes, sha256 $(shasum -a 256 "$OUT_FINAL" | cut -d' ' -f1))"
