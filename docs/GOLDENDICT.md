# Ancient Greek for Linux and Windows (GoldenDict-ng)

The macOS build ships as a Dictionary.app bundle. For Linux and Windows the same
data ships as **StarDict**, read by [GoldenDict-ng](https://xiaoyifang.github.io/goldendict-ng/).

You get both dictionaries and, importantly, the same select-a-word-and-look-it-up
workflow macOS gives you natively — GoldenDict calls it **Scan Popup**.

| | |
|---|---|
| Ancient Greek (LSJ) | 122,312 entries, 4,406,456 indexed forms |
| Greek Grammar Reference | 719 topics (Smyth + Goodwin), 12,946 indexed forms |

The 4.4M indexed forms are the Morpheus morphology database. They are what make
this usable for *reading*: select `ἐποίησεν` in a text and you get `ποιέω`,
select `γεγραμμένων` and you get `γράφω`. You do not have to know the lemma.

## 1. Install GoldenDict-ng

Not the original GoldenDict — the maintained `-ng` fork. Both are packaged
widely; on Linux prefer your distro package or the Flatpak, on Windows use the
installer from the project's releases page.

## 2. Add the dictionaries

1. Download `AncientGreek-GoldenDict-<version>.zip` from the
   [releases page](https://github.com/Josolon/ancient-greek-mac/releases) and unzip it
   somewhere permanent — the files are read in place, not copied.
2. In GoldenDict: **Edit → Dictionaries → Sources → Files → Add…**
3. Select the unzipped `goldendict` folder.
4. **Apply**. Indexing takes a minute or two the first time; the LSJ `.dict` is
   ~213 MB and GoldenDict builds its own index cache beside it.

## 3. Apply the stylesheet

StarDict has no stylesheet slot, so the CSS ships separately. Without it the
entries are readable but unstyled — no sense indentation, no Greek serif face,
no morphology table borders.

Find your configuration folder:

| OS | Path |
|---|---|
| Linux | `~/.goldendict` or `~/.config/goldendict` |
| Windows | `%APPDATA%\GoldenDict` |
| macOS | `~/Library/Application Support/GoldenDict` |

**Recommended — as an addon style, which leaves your own styling alone:**

Create `styles/AncientGreek/` in that folder and put `article-style.css` inside it:

```
<config folder>/styles/AncientGreek/article-style.css
```

Then pick **AncientGreek** under **Edit → Preferences → Appearances → Style**.

**Alternative:** append the contents of `article-style.css` to the
`article-style.css` sitting directly in the config folder. Everything is scoped
to `.agk-article`, so it will not disturb your other dictionaries.

Restart GoldenDict either way — it only reads styles at startup.

The stylesheet includes a dark-mode block via `prefers-color-scheme`, and
collapses sense indentation below 520px so deep LSJ entries stay readable at
popup width.

## 4. Turn on Scan Popup — the Look Up equivalent

**Edit → Preferences → Scan Popup.** Two modes worth knowing:

- **Instant popup** on selection.
- **Scan Flag** — a small icon appears next to your selection and only expands
  into the full article if you click it. Much less intrusive when you are
  reading continuous text, which is the usual case here.

On **Linux/X11** this is genuinely better than macOS: X11's PRIMARY selection
means merely highlighting a word fires the lookup, with no keystroke at all.

On **Windows** it works from the clipboard via a configurable global hotkey.
Selection-based lookup is reliable; the hover-without-selecting mode is hit or
miss in Chromium- and Electron-based apps.

### If you are on Wayland

Global hotkeys and Scan Flag do not work under native Wayland — the compositor
deliberately withholds the global input access they need. GoldenDict-ng defaults
to native Wayland from 25.12.0 onward for HiDPI reasons, so you may need to opt
out. Their [own Wayland notes](https://xiaoyifang.github.io/goldendict-ng/topic_wayland/)
recommend forcing X11 mode:

```bash
QT_QPA_PLATFORM=xcb goldendict
```

For the Flatpak, set the same variable with Flatseal or `flatpak override`. The
in-window lookup works fine under native Wayland either way — it is only the
select-anywhere-on-screen behaviour that needs XWayland.

## Cross-dictionary links

Grammar citations in LSJ entries ("S. 789") are clickable and jump to the
Grammar Reference, and the grammar's own internal cross-references work the same
way. On macOS these are `x-dictionary:` links carrying a bundle id; here they are
rewritten to `bword:`, which searches every enabled dictionary. That is slightly
more robust — the link resolves as long as the Grammar Reference is enabled, with
no identifier to get out of sync.

## Notes and limitations

- **Diacritics.** No folded duplicate forms are emitted; GoldenDict normalises
  accents and case at search time, so you can type `anthropos` or unaccented
  Greek and still land on the entry. Selecting accented text from a real edition
  matches the index directly.
- **Disk size.** The LSJ body ships as `.dict.dz` — dictzip, which is ordinary
  gzip plus a chunk table that lets GoldenDict seek to a single article instead
  of inflating the whole file. That trades a marginally larger download for a
  much smaller installed footprint.
- **Fonts.** The stylesheet falls through to DejaVu Serif on Linux and Palatino
  Linotype on Windows, both of which have real polytonic coverage. Installing
  [New Athena Unicode](https://classicalstudies.org/publications-and-research/new-athena-unicode-font)
  or Gentium Plus gives a better result.
- **Some grammar headwords are shouted** (`ACCENT AS AFFECTED BY CONTRACTION…`).
  That casing comes from the upstream Smyth headings and is the same on macOS.

## Attribution

The LSJ text is [LSJLogeion](https://github.com/helmadik/LSJLogeion) — please
credit **Perseus Tufts and Helma Dik/Logeion**. See `LICENSE` for the full terms;
the data is CC BY-SA 4.0 and the build scripts are MIT.

## Rebuilding from source

```bash
python3 scripts/build_unabridged_xml.py
python3 scripts/build_grammar_reference.py
./scripts/package_goldendict.sh v1.5.0
```

`scripts/verify_stardict.py` reads a built set back independently of the writer
and checks sort order, offset integrity and UTF-8 validity:

```bash
python3 scripts/verify_stardict.py dist/goldendict/AncientGreekLSJ --lookup ἐποίησεν
```
