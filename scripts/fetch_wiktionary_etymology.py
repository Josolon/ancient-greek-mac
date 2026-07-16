"""Filters the shared Wiktionary Ancient Greek extract
(../wiktionary-grc-data/grc_entries.jsonl - see that folder's README for
what it is, where it came from, and why the raw dump rather than kaikki.org's
now-deprecated per-language file) down to just the headwords this
dictionary's own LSJ corpus actually has, keyed the same way
build_unabridged_xml.py already keys its grammar-cross-reference lookup
(strip_all_greek_accents().lower()) so the two lookups compose directly.

Emits data/wiktionary_etymology.json: word -> [etymology_text, ...], a list
rather than a single string because some headwords have more than one
Wiktionary entry with genuinely different etymologies for different senses
(e.g. θύω "to rush/rage" vs θύω "to sacrifice" - unrelated PIE roots). This
project doesn't attempt to match a specific LSJ sense (A)/(B) to a specific
Wiktionary etymology - see render_wiktionary_etymology_html in
build_unabridged_xml.py, which shows every distinct one found rather than
guessing. Genuine work-in-progress limitation, not a bug: LSJ's own (A)/(B)
sense split and Wiktionary's own etymology-1/etymology-2 split aren't
guaranteed to line up 1:1, and nothing here tries to prove they do.
"""
import json
import os

from build_unabridged_xml import strip_all_greek_accents

WIKTIONARY_SOURCE_PATH = '../wiktionary-grc-data/grc_entries.jsonl'
OUTPUT_PATH = 'data/wiktionary_etymology.json'


def fetch_wiktionary_etymology():
    if not os.path.exists(WIKTIONARY_SOURCE_PATH):
        print(f"❌ {WIKTIONARY_SOURCE_PATH} not found - see ../wiktionary-grc-data/README.md "
              f"for how to produce it (a one-time 2.6GB download + filter, not something "
              f"this script does itself).")
        return

    by_word = {}
    total = 0
    with_etym = 0
    with open(WIKTIONARY_SOURCE_PATH, encoding='utf-8') as f:
        for line in f:
            total += 1
            d = json.loads(line)
            etym = (d.get('etymology_text') or '').strip()
            if not etym:
                continue
            with_etym += 1
            key = strip_all_greek_accents(d.get('word', '')).lower()
            if not key:
                continue
            by_word.setdefault(key, [])
            if etym not in by_word[key]:  # same etymology sometimes repeats across pos entries
                by_word[key].append(etym)

    with open(OUTPUT_PATH, 'w', encoding='utf-8') as out:
        json.dump(by_word, out, ensure_ascii=False)

    print(f"📖 Scanned {total} Wiktionary Ancient Greek entries ({with_etym} with an etymology)")
    print(f"💾 Wrote {len(by_word)} distinct headwords to {OUTPUT_PATH}")


if __name__ == '__main__':
    fetch_wiktionary_etymology()
