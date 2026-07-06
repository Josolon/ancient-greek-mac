"""Builds a third .dictionary bundle - "Greek Grammar Reference" - from Smyth's
A Greek Grammar for Colleges (1920) and Goodwin's Syntax of the Moods and
Tenses of the Greek Verb (1889), both Perseus Digital Library texts, freely
redistributable with attribution (see README's Data Sources section).

Unlike LSJ, a grammar reference is organized by topic/section-number, not by
headword, so entries here are keyed by the book's own English section
headings (e.g. "GENITIVE ABSOLUTE") rather than a Greek word. Each entry is
also indexed by its canonical citation form (e.g. "S. 2070", "G. 473") so a
citation typed into Look Up jumps straight to the right entry.

This script also emits data/grammar_word_index.json: a Greek-word -> list of
(source, paragraph number) index, mined from the Greek word tokens embedded
in both texts. build_unabridged_xml.py loads this to cross-reference LSJ's
particle/conjunction/preposition entries with the relevant Smyth/Goodwin
paragraphs discussing that specific word.
"""
import glob
import html as html_lib
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from html.parser import HTMLParser

SMYTH_HTML_DIR = 'data/smyth_html/'
GOODWIN_XML_PATH = 'data/goodwin.xml'
OUTPUT_XML_PATH = 'src/GrammarReference.xml'
WORD_INDEX_PATH = 'data/grammar_word_index.json'

HEADING_TAGS = {'h2', 'h3', 'h4', 'h5', 'h6'}

# --- Beta Code -> Unicode (Goodwin's TEI source is Beta Code; Smyth's HTML
# derivative already ships proper Unicode, so this is only needed for Goodwin) ---
_BETA_LETTERS = {
    'a': 'α', 'b': 'β', 'g': 'γ', 'd': 'δ', 'e': 'ε', 'z': 'ζ', 'h': 'η', 'q': 'θ',
    'i': 'ι', 'k': 'κ', 'l': 'λ', 'm': 'μ', 'n': 'ν', 'c': 'ξ', 'o': 'ο', 'p': 'π',
    'r': 'ρ', 's': 'σ', 't': 'τ', 'u': 'υ', 'f': 'φ', 'x': 'χ', 'y': 'ψ', 'w': 'ω',
    'v': 'ϝ',
}
_BETA_UPPER = {k: v.upper() for k, v in _BETA_LETTERS.items()}
_BETA_MARKS = {')': '̓', '(': '̔', '/': '́', '\\': '̀', '=': '̂', '|': 'ͅ', '+': '̈'}

def beta_to_unicode(text):
    """Converts TLG/Perseus Beta Code to Unicode Greek."""
    out = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '*':
            i += 1
            if i < n and text[i].lower() in _BETA_LETTERS:
                out.append(_BETA_UPPER[text[i].lower()])
                i += 1
            continue
        low = ch.lower()
        if low in _BETA_LETTERS:
            base = _BETA_LETTERS[low]
            i += 1
            marks = ''
            while i < n and text[i] in _BETA_MARKS:
                marks += _BETA_MARKS[text[i]]
                i += 1
            out.append(unicodedata.normalize('NFC', base + marks))
            continue
        out.append(ch)
        i += 1
    result = "".join(out)
    result = re.sub(r'σ(?=[\s.,;:!?’\'"()\[\]]|$)', 'ς', result)
    return result

def clean_ws(text):
    return re.sub(r'\s+', ' ', text).strip()

def strip_accents(text):
    STRIP = {0x0300, 0x0301, 0x0302, 0x0304, 0x0306, 0x0308, 0x0313, 0x0314, 0x0345}
    decomposed = unicodedata.normalize('NFD', text)
    filtered = "".join(ch for ch in decomposed if ord(ch) not in STRIP)
    return unicodedata.normalize('NFC', filtered)

def natural_smyth_key(path):
    name = os.path.basename(path)
    m = re.match(r'body\.1_div1\.(\d+)(?:_div2\.(\d+))?\.html', name)
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else -1)


# --- Smyth: HTML parsing ---

class SmythParser(HTMLParser):
    """Walks a chapter file's HTML in document order, emitting a flat event
    list of ('heading', level, text) and ('para', num, text). Paragraph text
    is flattened to plain text (dropping inline styling) - a deliberate v1
    simplification; the citation/index metadata is the valuable part here,
    not rich inline typography like LSJ's own entries have."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.div_depth = 0
        self.heading = None  # {'level': int, 'parts': []}
        self.para = None  # {'num': int, 'parts': [], 'depth_at_open': int}
        self.suppress_heading = False  # True while inside an inner h4-h6 (the paragraph's own number label)

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in HEADING_TAGS:
            if self.para is not None:
                # this is the paragraph's own number label (e.g. <h4>929</h4>) - not a real heading
                self.suppress_heading = True
            else:
                self.heading = {'level': int(tag[1]), 'parts': []}
        elif tag == 'div':
            self.div_depth += 1
            if attrs_dict.get('class') == 'smythp' and self.para is None:
                m = re.match(r's(\d+)', attrs_dict.get('id', ''))
                self.para = {'num': int(m.group(1)) if m else 0, 'parts': [], 'depth_at_open': self.div_depth}

    def handle_endtag(self, tag):
        if tag in HEADING_TAGS:
            if self.suppress_heading:
                self.suppress_heading = False
            elif self.heading is not None:
                text = clean_ws("".join(self.heading['parts']))
                if text:
                    self.events.append(('heading', self.heading['level'], text))
                self.heading = None
        elif tag == 'div':
            if self.para is not None and self.div_depth == self.para['depth_at_open']:
                text = clean_ws("".join(self.para['parts']))
                self.events.append(('para', self.para['num'], text))
                self.para = None
            self.div_depth -= 1

    def handle_data(self, data):
        if self.heading is not None and not self.suppress_heading:
            self.heading['parts'].append(data)
        elif self.para is not None and not self.suppress_heading:
            self.para['parts'].append(data)


def group_events_into_topics(events, fallback_heading, source):
    """Groups a flat (heading|para) event stream into topic entries: every
    heading starts a new topic; paragraphs before the first heading in a
    file fall under that file's own top-level title."""
    topics = []
    current = {'heading': fallback_heading, 'nums': [], 'text_parts': []}
    for kind, a, b in events:
        if kind == 'heading':
            if current['nums']:
                topics.append(current)
            current = {'heading': b, 'nums': [], 'text_parts': []}
        else:
            num, text = a, b
            current['nums'].append(num)
            if text:
                current['text_parts'].append(text)
    if current['nums']:
        topics.append(current)
    for t in topics:
        t['source'] = source
        t['body'] = " ".join(t['text_parts'])
    return topics

def extract_foreign_word_index_from_html(content, source_name):
    """Positional scan (paragraph-start markers vs. foreign-word spans) to
    build a word -> [(source, paragraph number)] index. Deliberately
    independent of SmythParser's event walk above - this only needs word
    tokens and their nearest enclosing paragraph number, not full nesting."""
    para_starts = [(m.start(), int(m.group(1))) for m in re.finditer(r'<div class="smythp" id="s(\d+)"', content)]
    index = defaultdict(set)
    if not para_starts:
        return index
    pi = 0
    for m in re.finditer(r'<span class="foreign">([^<]*)</span>', content):
        pos = m.start()
        while pi + 1 < len(para_starts) and para_starts[pi + 1][0] <= pos:
            pi += 1
        if pos < para_starts[0][0]:
            continue
        token = m.group(1).strip()
        if token and ' ' not in token and 1 < len(token) <= 20:
            index[strip_accents(token)].add((source_name, para_starts[pi][1]))
    return index

def parse_smyth():
    topics = []
    word_index = defaultdict(set)
    files = sorted(glob.glob(os.path.join(SMYTH_HTML_DIR, '*.html')), key=natural_smyth_key)
    for path in files:
        content = open(path, encoding='utf-8', errors='ignore').read()
        title_match = re.search(r'<h1 class="maintitle">([^<]*)</h1>', content)
        fallback = clean_ws(title_match.group(1)) if title_match else "Smyth"

        parser = SmythParser()
        parser.feed(content)
        topics.extend(group_events_into_topics(parser.events, fallback, 'Smyth'))

        for word, refs in extract_foreign_word_index_from_html(content, 'Smyth').items():
            word_index[word].update(refs)

    return topics, word_index


# --- Goodwin: TEI XML parsing (Beta Code) ---

def _flatten_with_beta_conversion(el):
    """Flattens an element's text content, converting any <foreign> tag's
    Beta Code to Unicode at whatever depth it appears (not just direct
    children) - the rest of the tree is plain English prose."""
    parts = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag.split('}')[-1] == 'foreign':
            parts.append(beta_to_unicode("".join(child.itertext())))
        else:
            parts.append(_flatten_with_beta_conversion(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)

def parse_goodwin():
    tree = ET.parse(GOODWIN_XML_PATH)
    root = tree.getroot()
    topics = []
    word_index = defaultdict(set)

    body = root.find('.//body')
    if body is None:
        return topics, word_index

    current = {'heading': 'Goodwin', 'nums': [], 'text_parts': []}
    current_num = 0

    def flush():
        if current['nums']:
            current['source'] = 'Goodwin'
            current['body'] = " ".join(current['text_parts'])
            topics.append(dict(current))

    for el in body.iter():
        tag = el.tag.split('}')[-1]
        if tag == 'head':
            flush()
            # Headings are plain English (no embedded Greek here) - unlike
            # <p> body text, don't run this through beta_to_unicode.
            text = clean_ws("".join(el.itertext()))
            current = {'heading': text, 'nums': [], 'text_parts': []}
        elif tag == 'milestone' and el.attrib.get('unit') == 'smythp':
            current_num = int(el.attrib.get('n', current_num))
            current['nums'].append(current_num)
        elif tag == 'p':
            text = clean_ws(_flatten_with_beta_conversion(el))
            if text:
                current['text_parts'].append(text)
        elif tag == 'foreign':
            word = beta_to_unicode("".join(el.itertext())).strip()
            if word and ' ' not in word and 1 < len(word) <= 20:
                word_index[strip_accents(word)].add(('Goodwin', current_num))
    flush()
    return topics, word_index


# --- Citation index terms ---

def citation_terms(source, nums):
    """S./Smyth or G./Goodwin index terms for every paragraph number in a
    topic's range - so citing any paragraph within it, not just its first,
    finds the entry."""
    prefix = 'S' if source == 'Smyth' else 'G'
    full = 'Smyth' if source == 'Smyth' else 'Goodwin'
    terms = set()
    for n in nums:
        terms.add(f'{prefix}. {n}')
        terms.add(f'{prefix}.{n}')
        terms.add(f'{full} {n}')
    return terms

def citation_range(nums):
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    return f'{lo}–{hi}' if lo != hi else f'{lo}'


def build_grammar_reference_dictionary():
    print("📘 Parsing Smyth's A Greek Grammar for Colleges...")
    smyth_topics, smyth_words = parse_smyth()
    print(f"   {len(smyth_topics)} topic entries, {len(smyth_words)} indexed words")

    print("📗 Parsing Goodwin's Syntax of the Moods and Tenses...")
    goodwin_topics, goodwin_words = parse_goodwin()
    print(f"   {len(goodwin_topics)} topic entries, {len(goodwin_words)} indexed words")

    all_topics = smyth_topics + goodwin_topics

    with open(OUTPUT_XML_PATH, 'w', encoding='utf-8') as out:
        out.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')
        for i, t in enumerate(all_topics):
            entry_id = f'grammar_entry_{i}'
            title = t['heading']
            safe_title = title if title else "unknown"
            out.write(f'    <d:entry id="{entry_id}" d:title="{html_lib.escape(safe_title)}">\n')

            index_terms = {title}
            for part in re.split(r'\.\s+', title):
                part = part.strip().rstrip('.')
                if part:
                    index_terms.add(part)
                    index_terms.add(part.title())
            index_terms.add(title.title())
            index_terms.update(citation_terms(t['source'], t['nums']))
            for term in index_terms:
                if term:
                    out.write(f'        <d:index d:value="{html_lib.escape(term)}"/>\n')

            out.write(f'        <h1 class="grammar-heading">{html_lib.escape(title.title())}</h1>\n')
            prefix = 'S' if t['source'] == 'Smyth' else 'G'
            out.write(f'        <div class="grammar-citation">{t["source"]} §{html_lib.escape(citation_range(t["nums"]))}</div>\n')
            out.write(f'        <div class="grammar-body">{html_lib.escape(t["body"])}</div>\n')
            out.write('    </d:entry>\n\n')
        out.write('</d:dictionary>\n')
    print(f"🎉 Wrote {len(all_topics)} grammar reference entries to {OUTPUT_XML_PATH}")

    combined_index = defaultdict(set)
    for word, refs in smyth_words.items():
        combined_index[word].update(refs)
    for word, refs in goodwin_words.items():
        combined_index[word].update(refs)

    serializable = {word: sorted(refs) for word, refs in combined_index.items()}
    with open(WORD_INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False)
    print(f"💾 Wrote word index ({len(serializable)} distinct words) to {WORD_INDEX_PATH}")


if __name__ == '__main__':
    build_grammar_reference_dictionary()
