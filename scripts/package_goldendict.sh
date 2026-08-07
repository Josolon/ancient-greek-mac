#!/usr/bin/env bash
# Build the GoldenDict (Linux/Windows/macOS) release bundle from the Apple
# Dictionary source XML.
#
# Prerequisites: src/GreekDictionary.xml and src/GrammarReference.xml already
# built by build_unabridged_xml.py / build_grammar_reference.py.
#
# The .dict is dictzip-compressed by scripts/dictzip.py - no external binary
# needed, so this produces the same artifact on any machine with Python.
set -euo pipefail

cd "$(dirname "$0")/.."

OUT=dist/goldendict
VERSION="${1:-dev}"

rm -rf "$OUT"
mkdir -p "$OUT"

python3 scripts/build_stardict.py src/GreekDictionary.xml \
    --out "$OUT" \
    --name AncientGreekLSJ \
    --bookname "Ancient Greek (LSJ)" \
    --description "Liddell-Scott-Jones Greek-English Lexicon with Morpheus morphology, reconstructed Classical Attic pronunciation, and Wiktionary etymology. LSJ text: Perseus Tufts and Helma Dik/Logeion."

python3 scripts/build_stardict.py src/GrammarReference.xml \
    --out "$OUT" \
    --name GreekGrammarReference \
    --bookname "Greek Grammar Reference (Smyth & Goodwin)" \
    --description "Smyth's Greek Grammar and Goodwin's Greek Moods and Tenses, cross-linked with the LSJ lexicon."

python3 scripts/verify_stardict.py "$OUT/AncientGreekLSJ"
python3 scripts/verify_stardict.py "$OUT/GreekGrammarReference"

cp src/GoldenDictArticle.css "$OUT/article-style.css"
cp docs/GOLDENDICT.md "$OUT/README.md"
cp LICENSE "$OUT/LICENSE"

ZIP="dist/AncientGreek-GoldenDict-${VERSION}.zip"
rm -f "$ZIP"
(cd dist && zip -r -q "$(basename "$ZIP")" goldendict)

echo
echo "Built $ZIP"
ls -lh "$ZIP"
