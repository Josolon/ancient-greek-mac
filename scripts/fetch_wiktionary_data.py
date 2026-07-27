"""Filters the shared Wiktionary Ancient Greek extract
(../wiktionary-grc-data/grc_entries.jsonl - see that folder's README for
what it is, where it came from, and why the raw dump rather than kaikki.org's
now-deprecated per-language file) down to two lookups this dictionary's own
build reads, both keyed the same way build_unabridged_xml.py already keys its
grammar-cross-reference lookup (strip_all_greek_accents().lower()) so all
three lookups compose directly.

1. data/wiktionary_etymology.json: word -> [etymology_text, ...], a list
   rather than a single string because some headwords have more than one
   Wiktionary entry with genuinely different etymologies for different senses
   (e.g. θύω "to rush/rage" vs θύω "to sacrifice" - unrelated PIE roots). This
   project doesn't attempt to match a specific LSJ sense (A)/(B) to a specific
   Wiktionary etymology - see render_wiktionary_etymology_html in
   build_unabridged_xml.py, which shows every distinct one found rather than
   guessing. Genuine work-in-progress limitation, not a bug: LSJ's own (A)/(B)
   sense split and Wiktionary's own etymology-1/etymology-2 split aren't
   guaranteed to line up 1:1, and nothing here tries to prove they do.

2. data/wiktionary_vowel_length.json: word -> canonical_form_with_marks. A
   third, independent source of dichrona (α/ι/υ) length for headwords LSJ's
   own orth_orig/pron data doesn't mark - both λύω and θύω's "to sacrifice"
   sense are long-υ verbs that LSJ simply doesn't bother re-marking (see
   ../phonology-recap.md for the general pattern: a source not marking
   something isn't the same as that thing being unmarked/short, it's often
   just the source treating it as the unremarkable default). Wiktionary's own
   'canonical' form tag carries the length marks directly (e.g. 'θῡ́ω').
   merge_wiktionary_vowel_length in build_unabridged_xml.py grafts these onto
   the LSJ headword the same letter-aligned way orth_orig/pron already are,
   as a third-priority fallback - LSJ's own marks always win where present.
   A vowel where Wiktionary's own canonical form carries BOTH a macron AND a
   breve (rare - about 0.4% of canonical forms) is left unmarked rather than
   guessed at: that combination is Wiktionary's own way of flagging a vowel
   whose length is itself disputed/variable, not a typo to resolve either way.
"""
import json
import os
import unicodedata

from build_unabridged_xml import strip_all_greek_accents

WIKTIONARY_SOURCE_PATH = '../wiktionary-grc-data/grc_entries.jsonl'
ETYMOLOGY_OUTPUT_PATH = 'data/wiktionary_etymology.json'
VOWEL_LENGTH_OUTPUT_PATH = 'data/wiktionary_vowel_length.json'

_LENGTH_MARKS = {0x0304, 0x0306}


_PRESENT_1SG_TAGS = {'active', 'indicative', 'singular', 'first-person'}


def _present_1sg_active_indicative(forms):
    """Falls back to a verb's own conjugation-table entry for present active
    indicative 1st singular - i.e. the exact same word as the headword -
    when the 'canonical' tag's form is missing or marks a vowel ambiguous
    (see _has_ambiguous_vowel). Rare (rescues only ~2 words in the whole
    corpus out of 169 ambiguous canonicals - λύω is one of them, its
    'canonical' tag hedges 'λῡ̆́ω' even though its own present-tense table
    row gives the unambiguous 'λῡ́ω'), but worth the extra pass for exactly
    that kind of case. Tag rows here don't carry an explicit tense - it's
    implied by the nearest preceding 'table-tags' marker, so this tracks
    that marker while walking the list rather than filtering on tags alone."""
    tense = 'present'  # present is the first table and often has no explicit marker before it
    for form_entry in forms:
        tags = form_entry.get('tags', [])
        if 'table-tags' in tags:
            tense = form_entry.get('form', tense)
            continue
        if tense == 'present' and set(tags) >= _PRESENT_1SG_TAGS:
            return form_entry.get('form', '')
    return None


def _has_ambiguous_vowel(form):
    """True if any single vowel in `form` carries both a macron AND a breve -
    Wiktionary's own notation for a length that's itself disputed/variable,
    not a markup slip. See module docstring."""
    marks = set()
    for ch in unicodedata.normalize('NFD', form):
        if unicodedata.combining(ch):
            marks.add(ord(ch))
        else:
            if _LENGTH_MARKS <= marks:
                return True
            marks = set()
    return _LENGTH_MARKS <= marks


def fetch_wiktionary_data():
    if not os.path.exists(WIKTIONARY_SOURCE_PATH):
        print(f"❌ {WIKTIONARY_SOURCE_PATH} not found - see ../wiktionary-grc-data/README.md "
              f"for how to produce it (a one-time 2.6GB download + filter, not something "
              f"this script does itself).")
        return

    etym_by_word = {}
    length_by_word = {}
    total = 0
    with_etym = 0
    with_length = 0
    skipped_ambiguous = 0
    with open(WIKTIONARY_SOURCE_PATH, encoding='utf-8') as f:
        for line in f:
            total += 1
            d = json.loads(line)
            key = strip_all_greek_accents(d.get('word', '')).lower()
            if not key:
                continue

            etym = (d.get('etymology_text') or '').strip()
            if etym:
                with_etym += 1
                etym_by_word.setdefault(key, [])
                if etym not in etym_by_word[key]:  # same etymology sometimes repeats across pos entries
                    etym_by_word[key].append(etym)

            if key not in length_by_word:
                forms = d.get('forms') or []
                canonical = next((f.get('form', '') for f in forms if 'canonical' in f.get('tags', [])), None)
                candidate = canonical
                if canonical and _has_ambiguous_vowel(canonical):
                    candidate = _present_1sg_active_indicative(forms)  # may still be ambiguous or None
                if candidate and not _has_ambiguous_vowel(candidate):
                    length_by_word[key] = candidate
                    with_length += 1
                elif canonical:
                    skipped_ambiguous += 1

    with open(ETYMOLOGY_OUTPUT_PATH, 'w', encoding='utf-8') as out:
        json.dump(etym_by_word, out, ensure_ascii=False)
    with open(VOWEL_LENGTH_OUTPUT_PATH, 'w', encoding='utf-8') as out:
        json.dump(length_by_word, out, ensure_ascii=False)

    print(f"📖 Scanned {total} Wiktionary Ancient Greek entries")
    print(f"💾 Wrote {len(etym_by_word)} distinct headwords ({with_etym} entries) to {ETYMOLOGY_OUTPUT_PATH}")
    print(f"💾 Wrote {with_length} distinct headwords to {VOWEL_LENGTH_OUTPUT_PATH} "
          f"({skipped_ambiguous} skipped for an ambiguous macron+breve vowel)")


if __name__ == '__main__':
    fetch_wiktionary_data()
