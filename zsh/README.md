# zsh with Terminal.app's Burmese widths

Stock zsh (including macOS `/bin/zsh`) treats every Myanmar vowel sign and medial as a zero-width combining mark, but Terminal.app gives the spacing ones (Unicode category Mc: ာ ါ ေ း ျ ြ and others) a full cell. When you edit a command line that contains Burmese, zsh then puts the cursor in the wrong place.

`myanmar-width.patch` changes only that: for U+1000–U+109F, U+A9E0–U+A9FE and U+AA60–U+AA7F, zsh's width function returns 0 for non-spacing marks (Mn) and 1 for everything else. All other characters keep zsh's own widths.

`build.sh PREFIX` downloads the official zsh 5.9.2 source from zsh.org, checks its SHA-256 (and its GPG signature when gpg is installed), applies the patch, builds it with the same options as Apple's `/bin/zsh` (it reads the same `/etc/zshrc` and site functions), runs the zsh test suite (skip with `RUN_CHECK=0`), installs into PREFIX and prints a width self-test (`2 4 1 7 4 2` is correct).

Use it from Terminal > Settings > General > "Shells open with" > Command (complete path): `PREFIX/bin/zsh`. Your login shell, `$SHELL` and dotfiles are unchanged; set the option back to "Default login shell" to undo.
