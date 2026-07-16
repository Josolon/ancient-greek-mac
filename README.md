# 🏛️ macOS Ancient Greek Dictionary

![Ancient Greek Dictionary working preview](assets/preview.png)
![Ancient Greek Dictionary working preview](assets/preview1.png)

A custom `.dictionary` plugin for the native macOS Dictionary app and system-wide "Look Up" feature. This dictionary combines the **complete Liddell–Scott–Jones (LSJ) lexicon** (117,129 unabridged entries) with beautifully styled noun declensions and verb principal parts.

**v1.3.0** — Reconstructed Classical Attic pronunciation (IPA, per W. Sidney Allen's *Vox Graeca*) on every LSJ entry, with a cross-language Pronunciation Guide reference entry (English/German/French/Italian/Spanish/Modern Greek/Icelandic/Latin); vowel length (macron/breve) now shown directly on headwords wherever LSJ's own source records it; clickable cross-references between the two dictionaries; and an experimental Wiktionary etymology integration (**work in progress, ~12% coverage** - see Data Sources). Builds on v1.2.0's companion Grammar Reference dictionary.

## ✨ Features

* **117k Unabridged LSJ Entries:** Full Chicago TEI-XML LSJ data compiled into the macOS `.dictionary` format.
* **System Integration:** Works natively with macOS "Look Up" (Force Click or Three-Finger Tap on any word).
* **Morphology Tables:** Declensions and principal parts always visible (no folds). Declension tables show all cases and numbers; principal parts organized in classical order (Present → Future → Aorist → Perfect).
* **Hierarchical Sense Indentation:** Major senses (I, II, III…) styled as visual subheadings; sub-senses indented with subtle left borders for visual hierarchy.
* **Grammar & Etymology:** Part of speech, gender, declension class, and dialect/voice/comparative/diminutive labels are pulled out of LSJ's own TEI tags into a labeled badge row, both at the entry level and on individual senses (e.g. a sense marked "as Subst." shows a `substantive` badge right there). A bare "Related to: X" etymology line surfaces LSJ's own cross-reference where the source has one, and (where available - see Data Sources) a fuller Wiktionary etymology paragraph is shown alongside it.
* **Reconstructed pronunciation (Vox Graeca):** Every entry shows a reconstructed Classical Attic IPA transcription per W. Sidney Allen's *Vox Graeca* - phonemic vowel length, the "spurious diphthongs" ει/ου, aspirated stops, pitch (not stress) accent modeled per-mora, hiatus-conditioned glide lengthening, and more. A companion "Pronunciation Guide" reference entry (searchable under "pronunciation") maps every vowel/diphthong/consonant/geminate onto real example words in eight other languages. Vowel length for the "dichrona" α/ι/υ (not shown by ordinary spelling) is displayed directly on the headword with a macron/breve wherever LSJ's own source data records it.
* **Grammar & Syntax cross-references:** Particles, conjunctions, and verbs with special constructions (ἄν, γάρ, ὅτι, βούλομαι, τυγχάνω, …) are cross-referenced to the specific paragraphs of Smyth's and Goodwin's reference grammars that discuss them - and clickable, jumping straight into the companion Grammar Reference dictionary (and back again, for its own internal "see 348"-style cross-references).
* **Companion "Greek Grammar Reference" dictionary:** A second `.dictionary` bundle covering ~700 topics from Smyth's *A Greek Grammar for Colleges* and Goodwin's *Syntax of the Moods and Tenses of the Greek Verb*, searchable both by topic ("Genitive Absolute", "Conditional Sentences", …) and by canonical citation (`S. 2070`, `Smyth 2070`, `G. 473`, `Goodwin 473`).
* **Polytonic Support:** Handles Greek diacritics and polytonic accents smoothly within Apple's search engine.

## 📦 Installation (For End Users)

1. Download the latest release from the [Releases](https://github.com/Josolon/ancient-greek-mac/releases) page.
2. Unzip the `.zip` file to get `AncientGreek.dictionary` and `GreekGrammarReference.dictionary`.
3. Open Finder, press `Cmd + Shift + G`, and navigate to `~/Library/Dictionaries/`.
4. Drag and drop both `.dictionary` folders into this location.
5. Open the macOS **Dictionary app**, go to **Settings**, and enable "Ancient Greek (LSJ)" and/or "Ancient Greek Grammar (Smyth & Goodwin)".

## 🛠️ Building from Source

### Prerequisites
* Python 3.x
* [Dictionary Development Kit](https://developer.apple.com/download/all/) (Found in Apple's "Additional Tools for Xcode").
* macOS 10.6+ and Xcode command-line tools.

### Build Scripts

This project includes two build pipelines:

#### **`scripts/build_xml.py`** — Quick abridged version (from SQLite databases)
For rapid iteration during development. Generates a smaller dictionary from pre-built morphology SQLite databases.

```bash
python3 scripts/build_xml.py
cd src && make install
```

#### **`scripts/build_unabridged_xml.py`** — Full LSJ (117k entries from TEI-XML)
Compiles the complete unabridged Chicago TEI-XML LSJ corpus. This is the official v1.0.0+ build.

```bash
python3 scripts/build_unabridged_xml.py
cd src && make install
```

#### **`scripts/build_grammar_reference.py`** — Companion Grammar Reference dictionary
Compiles Smyth's and Goodwin's reference grammars into the second `.dictionary` bundle, and emits `data/grammar_word_index.json` (a Greek word → paragraph-reference index) that `build_unabridged_xml.py` reads to add "Grammar & Syntax" cross-references to LSJ's particle/conjunction entries. Run this *before* `build_unabridged_xml.py` if you want those cross-references included - it's optional; the main dictionary still builds fine without it.

```bash
python3 scripts/fetch_grammar_sources.py   # one-time: vendors Smyth + Goodwin into data/
python3 scripts/build_grammar_reference.py
python3 scripts/build_unabridged_xml.py
cd src && make install
```

#### **`scripts/fetch_wiktionary_etymology.py`** — Wiktionary etymology lookup (optional, work in progress)
Filters a shared, un-versioned Wiktionary Ancient Greek extract (see Data Sources) down to `data/wiktionary_etymology.json`, which `build_unabridged_xml.py` reads to show a fuller etymology paragraph alongside LSJ's own bare cross-reference, where Wiktionary has one. Entirely optional - the main dictionary builds fine without it, just without that extra line. Run before `build_unabridged_xml.py` if you want it included.

```bash
python3 scripts/fetch_wiktionary_etymology.py
python3 scripts/build_unabridged_xml.py
cd src && make install
```

### Full Build Instructions

1. Clone this repository:
   ```bash
   git clone https://github.com/Josolon/ancient-greek-mac.git
   cd ancient-greek-mac
   ```

2. (Optional, for grammar cross-references) Fetch and build the grammar reference sources:
   ```bash
   python3 scripts/fetch_grammar_sources.py
   python3 scripts/build_grammar_reference.py
   ```

3. Run the XML generation script (choose one):
   - **For development:** `python3 scripts/build_xml.py`
   - **For official build:** `python3 scripts/build_unabridged_xml.py`

4. Compile and install both dictionaries:
   ```bash
   cd src
   make install
   ```

5. Open the **Dictionary** app, go to **Settings**, toggle "Ancient Greek" and "Ancient Greek Grammar" off and back on to reload.

### CSS Styling

All visual presentation is controlled by `src/GreekDictionary.css`. The stylesheet defines:
- Entry heading styling with polytonic support
- Sense hierarchy with depth-based indentation and colored left borders
- Major sense (Roman numeral) subheadings with separator lines
- Morphology table styling (declensions, principal parts)
- Greek text (`gk-word`) and citation (`citation`) highlighting
## 📁 Project Structure

```
ancient-greek-mac/
├── data/
│   ├── lsj_unicode/           # Chicago TEI-XML LSJ source (86 files)
│   ├── lsj.db                 # SQLite LSJ entries [gitignored]
│   ├── morph.db                # SQLite morphology data [gitignored]
│   ├── smyth_html/             # Smyth grammar HTML chapters [gitignored, fetched]
│   ├── goodwin.xml             # Goodwin grammar TEI-XML [gitignored, fetched]
│   ├── grammar_word_index.json # Word → Smyth/Goodwin paragraph index [gitignored, generated]
│   └── wiktionary_etymology.json # Word → Wiktionary etymology text [gitignored, generated]
├── scripts/
│   ├── build_xml.py           # Abridged builder (SQLite → XML)
│   ├── build_unabridged_xml.py # Full LSJ builder (TEI-XML → XML)
│   ├── fetch_grammar_sources.py # Vendors Smyth + Goodwin from Perseus
│   ├── build_grammar_reference.py # Grammar Reference dictionary + word index builder
│   ├── fetch_wiktionary_etymology.py # Filters the shared Wiktionary extract to data/wiktionary_etymology.json
│   └── phonology.py           # Reconstructed-Attic IPA transcription engine
├── src/
│   ├── GreekDictionary.xml    # Generated LSJ dictionary source [gitignored]
│   ├── GreekDictionary.css    # LSJ dictionary styling
│   ├── GreekDictionary.plist  # LSJ Apple Dictionary metadata
│   ├── GrammarReference.xml   # Generated Grammar Reference source [gitignored]
│   ├── GrammarReference.css   # Grammar Reference styling
│   ├── GrammarReference.plist # Grammar Reference Apple Dictionary metadata
│   ├── Makefile               # Build rules for both bundles
│   └── objects/               # Build artifacts [gitignored]
└── README.md
```

## 📚 Data Sources

* **LSJ Lexicon:** Complete Liddell–Scott–Jones ancient Greek dictionary, provided by the [Chicago Digital Classics](https://github.com/perseids-project/morphology) project in TEI-XML format.
* **Morphology:** Ancient Greek inflectional morphology from [Morpheus](https://github.com/perseids-project/morphology), integrated for noun declension and verb principal parts tables.
* **Grammar Reference:** Herbert Weir Smyth, *A Greek Grammar for Colleges* (1920), via [PerseusDL/sg_reader](https://github.com/PerseusDL/sg_reader); William Watson Goodwin, *Syntax of the Moods and Tenses of the Greek Verb* (1889), via the [Perseus Digital Library](https://www.perseus.tufts.edu/). Both public domain, freely redistributable with attribution per Perseus's standard text-reuse policy.
* **Pronunciation:** Reconstructed Classical Attic phonology per W. Sidney Allen, *Vox Graeca* (3rd ed., 1987).
* **Wiktionary Etymology (⚠️ work in progress):** Etymology text from the Ancient Greek (`grc`) entries of [Wiktionary](https://en.wiktionary.org/), via [kaikki.org](https://kaikki.org/)'s raw [Wiktextract](https://github.com/tatuylonen/wiktextract) data dump (CC BY-SA 4.0 / GFDL, per Wiktionary's own licensing). This only covers about **12% of the LSJ dictionary** - most LSJ headwords (rare forms, proper nouns, inflected citation forms) simply have no matching Wiktionary entry yet - and where a headword has more than one Wiktionary sense with a genuinely different etymology, all of them are shown rather than guessed at. Shown alongside, not in place of, LSJ's own etymology cross-reference.

## 🤝 Contributing

Contributions are welcome! Areas for improvement include:

* **Weird/broken entries:** By far the most valuable contribution. With 117,129 entries auto-generated from TEI-XML, edge cases in the source encoding inevitably slip through (missing headings, mangled overview boxes, garbled citations, etc.). If you spot an entry that looks wrong in the Dictionary app, [open an issue](https://github.com/Josolon/ancient-greek-mac/issues) with the headword and a screenshot/description - or better yet, trace it to the parsing logic in `scripts/build_unabridged_xml.py` and send a PR.
* **Styling:** Enhance CSS for better typography, colors, or responsive layout.
* **Python scripts:** Optimize parsing, add error handling, or improve how the TEI-XML hierarchy (senses, headings, preambles) is reconstructed.
* **Documentation:** Expand README, add usage guides, or create troubleshooting FAQs.

**Not in scope here:** morphological data (declensions, principal parts, inflectional forms) comes from the upstream [Morpheus](https://github.com/perseids-project/morphology) database and is maintained by classicists there, not in this repo. If you find an incorrect or missing inflected form, please report it upstream rather than opening a PR against `data/morph.db` here.

To contribute:
1. Fork this repository.
2. Create a feature branch (`git checkout -b feature/my-improvement`).
3. Commit your changes (`git commit -m "Add feature X"`).
4. Push and open a Pull Request.

## 📄 License

This project uses a **dual-license model**:

- **Code** (Python scripts, CSS, Makefile): [MIT License](LICENSE)
- **Data** (LSJ lexicon, morphology): [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/) (per Chicago Digital Classics)
- **Grammar Reference data** (Smyth, Goodwin): public domain texts, redistributed per the Perseus Digital Library's standard policy - freely distributable with attribution to Perseus, National Endowment for the Humanities funding, and the original authors.
- **Wiktionary etymology data:** CC BY-SA 4.0 / GFDL, per [Wiktionary](https://en.wiktionary.org/)'s own dual licensing.

See [LICENSE](LICENSE) for full details. When distributing this dictionary, all applicable licenses apply.

## 🙏 Acknowledgments

* **Liddell, Scott, Jones (LSJ):** The foundational ancient Greek lexicon.
* **Herbert Weir Smyth** and **William Watson Goodwin:** Authors of the reference grammars behind the Grammar Reference dictionary and the Grammar & Syntax cross-references.
* **Perseus Digital Library / Perseids:** For TEI-XML source data, morphology tooling, and the Smyth/Goodwin digitizations (funded in part by the National Endowment for the Humanities).
* **W. Sidney Allen:** *Vox Graeca*, the reconstructed-pronunciation reference this dictionary's IPA transcriptions follow.
* **Wiktionary contributors / kaikki.org / Wiktextract:** For the etymology data (work in progress, see Data Sources).
* **Apple Dictionary Development Kit:** For the macOS `.dictionary` format specification.
