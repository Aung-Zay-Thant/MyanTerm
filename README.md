# MyanTerm

A monospace font that renders Burmese (Myanmar script) correctly and naturally in macOS Terminal.app.

macOS Terminal မှာ မြန်မာစာကို မှန်မှန်ကန်ကန်၊ သဘာဝကျကျ ပြသပေးတဲ့ ဖောင့်။

![Terminal.app with SF Mono and with MyanTerm](docs/before-after.png)

## Install

1. Download `MyanTerm-1.0.zip` from [Releases](../../releases) and unzip it.
2. Double-click `Install MyanTerm.command`. The first time, macOS may block it: right-click it, choose Open, then Open again.
   Or, in Terminal: `cd MyanTerm-1.0 && ./install.sh`

The installer:

- copies `MyanTerm-Regular.ttf` and `MyanTerm-Bold.ttf` into `~/Library/Fonts`
- adds a Terminal profile named **MyanTerm** (MyanTerm 13 pt); existing profiles are not changed
- asks whether new Terminal windows should use it (Terminal > Settings > Profiles changes this later)
- checks that your Terminal measures Burmese the way the font expects

Options: `--default` / `--no-default` (skip the question), `--with-zsh` (see below).

To remove everything: `./uninstall.sh`.

## Editing Burmese at the zsh prompt (optional)

The font fixes how Burmese is drawn. Typing and editing Burmese in a command line is a separate problem: zsh counts the spacing vowel signs and medials (ာ ေ ျ ြ း) as zero columns wide while Terminal gives each one a column, so the cursor drifts. `./install.sh --with-zsh` builds zsh 5.9.2 from the official source with a small patch ([zsh/](zsh)) that makes zsh use Terminal's widths, installs it into `~/.local/myanterm-zsh`, and prints how to select it in Terminal > Settings > General > "Shells open with". Your `.zshrc` and other settings are used as before. Building needs the Xcode Command Line Tools (`xcode-select --install`).

## How it works

Terminal.app draws text cell by cell: every Burmese letter and every spacing vowel sign or medial gets one cell, and non-spacing marks get none. It shapes each row with Core Text and then places each glyph at the cell of the character it came from, ignoring the font's own spacing. Normal Burmese fonts rely on the text engine reordering ေ and ြ in front of the consonant and positioning marks freely, which breaks under that grid.

MyanTerm works with the grid instead:

- The font has no Myanmar OpenType script, so Core Text keeps glyphs in typed order and Terminal's placement is predictable.
- Every Burmese syllable (about 7,000, chosen by frequency in large Burmese corpora) is a single ligature glyph drawn from the real Noto Sans Myanmar shaping: reordering, medial widths, kinzi, stacked consonants and mark positions are exactly as in normal Burmese typography.
- Syllables are laid out proportionally, not one per cell. Each common syllable glyph exists in many copies shifted by small steps, and a contextual substitution picks the copy that continues where the previous syllable's natural spacing ended. Text can run a few cells ahead of or behind the grid; the difference is absorbed at the next space. Brackets, quotes and zero-width characters next to Burmese join this flow; English text and code are not affected.
- Uncommon sequences fall back to per-character glyphs that are positioned to stay readable.

## Limits

- Made for macOS Terminal.app. Other terminals (iTerm2, Ghostty, kitty, ...) lay out text differently.
- Built and tested on macOS 27 with Terminal 2.15. The installer checks the cell widths on your system and warns if they differ.
- Spaces between Burmese phrases are sometimes wider than one cell: that is where the extra room goes when a phrase is narrower than the cells Terminal reserves for it.
- Programs that do their own width calculation (for example some full-screen tools) may still disagree with Terminal about where Burmese text ends.

## Building from source

```sh
tools/build_all.sh            # creates fonts/MyanTerm-*.ttf and MyanTerm.terminal
tools/build_all.sh --install  # also copies the fonts into ~/Library/Fonts
```

Needs Python 3; the script installs fontTools and uharfbuzz into a local `.venv`. Sources: `src/` (Noto Sans Mono and Noto Sans Myanmar), `data/corpus_counts.tsv` (syllable frequencies from Burmese Wikipedia, XL-Sum, HPLT, FLORES-200, Tatoeba and other Burmese text), `tools/` (segmenter, syllable list, font builder).

## License

The fonts are licensed under the [SIL Open Font License 1.1](OFL.txt) and are derived from [Noto Sans Mono](https://github.com/notofonts/latin-greek-cyrillic) and [Noto Sans Myanmar](https://github.com/notofonts/myanmar). Installer and tools: MIT. The zsh patch follows the zsh license. See [LICENSE](LICENSE).
