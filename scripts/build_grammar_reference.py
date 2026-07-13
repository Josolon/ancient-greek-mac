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
import urllib.parse
import xml.etree.ElementTree as ET
from collections import defaultdict
from html.parser import HTMLParser

SMYTH_HTML_DIR = 'data/smyth_html/'
GOODWIN_XML_PATH = 'data/goodwin.xml'
OUTPUT_XML_PATH = 'src/GrammarReference.xml'
WORD_INDEX_PATH = 'data/grammar_word_index.json'
# Must match src/GrammarReference.plist's CFBundleIdentifier and the copy of
# this same constant in build_unabridged_xml.py.
GRAMMAR_DICT_BUNDLE_ID = 'com.jonatansolon.dictionary.GreekGrammarReference'

# h7 is not a native HTML tag, but Smyth's deepest-nested dialect/footnote
# sub-paragraphs (e.g. "508 D") use it anyway - see SmythParser.
HEADING_TAGS = {'h2', 'h3', 'h4', 'h5', 'h6', 'h7'}

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
    # Circumflex is 0342 (COMBINING GREEK PERISPOMENI), not 0302 (the generic/
    # Latin combining circumflex) - see build_unabridged_xml.py's strip_all_greek_accents.
    STRIP = {0x0300, 0x0301, 0x0304, 0x0306, 0x0308, 0x0313, 0x0314, 0x0342, 0x0345}
    decomposed = unicodedata.normalize('NFD', text)
    filtered = "".join(ch for ch in decomposed if ord(ch) not in STRIP)
    return unicodedata.normalize('NFC', filtered)

def natural_smyth_key(path):
    name = os.path.basename(path)
    m = re.match(r'body\.1_div1\.(\d+)(?:_div2\.(\d+))?\.html', name)
    return (int(m.group(1)), int(m.group(2)) if m.group(2) else -1)


# --- Smyth: HTML parsing ---

# Inline tags encountered inside a paragraph that are worth preserving in the
# rendered output, mapped to the (open, close) markup we emit instead of the
# source's own tag/attributes. Everything else (id-only spans, <a> links,
# layout-only divs, meta/nav cruft) is transparent: its content still comes
# through via handle_data, just without a wrapper.
_PARA_TAG_MARKUP = {
    'b': ('<b>', '</b>'),
    'i': ('<i>', '</i>'),
    'table': ('<table class="grammar-table"><tbody>', '</tbody></table>'),
    'tr': ('<tr>', '</tr>'),
    'td': ('<td>', '</td>'),
}

def render_para_parts(parts):
    """Joins a paragraph's (kind, text) parts into one HTML string - 'text'
    parts get escaped, 'html' parts (our own inserted markup) don't - then
    collapses whitespace runs the way clean_ws does for plain text. Safe to
    collapse globally because none of the markup we insert contains internal
    multi-space runs.

    A source line break used only for HTML readability (e.g. a newline
    between a Greek word's closing </span> and the next <span class="gloss">)
    collapses to a single plain space here - but Apple's build_dict.sh then
    treats that lone space as an insignificant whitespace-only text node
    (standard XML/XSLT behavior, since a bare ' ' between two tags looks
    identical to pretty-printing indentation) and silently drops it, gluing
    the Greek word straight onto its English gloss with no space at all. A
    literal U+00A0 in its place isn't XML whitespace, so it survives - this
    only ever fires exactly where a tag-to-tag gap held nothing but
    whitespace to begin with, never inside a real running sentence."""
    buf = [html_lib.escape(val) if kind == 'text' else val for kind, val in parts]
    joined = re.sub(r'\s+', ' ', "".join(buf)).strip()
    return re.sub(r'> <', '> <', joined)

def plain_text_of_parts(parts):
    return clean_ws("".join(val for kind, val in parts if kind == 'text'))


class SmythParser(HTMLParser):
    """Walks a chapter file's HTML in document order, emitting a flat event
    list of ('heading', level, text) and ('para', num, html). Paragraph
    content keeps a whitelisted set of inline tags (Greek word spans, glosses,
    embedded paradigm tables, bold/italic) so long grammar discussions render
    with real structure instead of one flattened wall of text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.div_depth = 0
        self.heading = None  # {'level': int, 'parts': []}
        self.para = None  # {'num': int|None, 'parts': [(kind, str)], 'depth_at_open': int}
        self.suppress_heading = False  # True while inside an inner h4-h6 (the paragraph's own number label)
        self.label_parts = None  # collects that inner label's text, to recover num when the id doesn't parse
        self.last_num = 0  # last successfully resolved paragraph number, as a final fallback
        self.tag_stack = []  # [(tag, close_markup_or_None)] - tracks what to emit on the matching end tag
        self.foreign_depth = 0  # >0 inside a <span class="foreign"> - suppresses the source's own redundant nested <b>

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in HEADING_TAGS:
            if self.para is not None:
                # this is the paragraph's own number label (e.g. <h4>929</h4>) - not a real heading
                self.suppress_heading = True
                self.label_parts = []
            else:
                self.heading = {'level': int(tag[1]), 'parts': []}
            return
        if tag == 'div':
            self.div_depth += 1
            if attrs_dict.get('class') == 'smythp' and self.para is None:
                m = re.match(r's(\d+)$', attrs_dict.get('id', ''))
                # Dialect/footnote sub-paragraphs (e.g. "500. 1. D", "503 D") use
                # the full hierarchical div path as their id instead of "sNNN" -
                # their number only shows up in the label text, recovered below
                # when that label tag closes.
                num = int(m.group(1)) if m else None
                self.para = {'num': num, 'parts': [], 'depth_at_open': self.div_depth}
            elif self.para is not None:
                self.tag_stack.append(('div', None))
            return
        if self.para is None:
            return
        if tag == 'span' and attrs_dict.get('class') == 'foreign':
            self.para['parts'].append(('html', '<b class="gk-word">'))
            self.tag_stack.append((tag, '</b>'))
            self.foreign_depth += 1
        elif tag == 'span' and attrs_dict.get('class') == 'gloss':
            self.para['parts'].append(('html', '<i class="grammar-gloss">'))
            self.tag_stack.append((tag, '</i>'))
        elif tag == 'br':
            self.para['parts'].append(('html', '<br/>'))
            self.tag_stack.append((tag, None))
        elif tag == 'b' and self.foreign_depth > 0:
            # the source often double-marks a Greek word - <span
            # class="foreign"><b>...</b></span> - already bold via gk-word,
            # so treat this inner <b> as transparent rather than nesting
            self.tag_stack.append((tag, None))
        elif tag in _PARA_TAG_MARKUP:
            open_markup, close_markup = _PARA_TAG_MARKUP[tag]
            self.para['parts'].append(('html', open_markup))
            self.tag_stack.append((tag, close_markup))
        else:
            # transparent wrapper (id-only span, <a>, <p>, ...): its own text
            # still comes through via handle_data, just unstyled
            self.tag_stack.append((tag, None))

    def handle_endtag(self, tag):
        if tag in HEADING_TAGS:
            if self.suppress_heading:
                self.suppress_heading = False
                if self.para is not None and self.para['num'] is None:
                    label_text = clean_ws("".join(self.label_parts or []))
                    m = re.match(r'(\d+)', label_text)
                    self.para['num'] = int(m.group(1)) if m else self.last_num
                self.label_parts = None
            elif self.heading is not None:
                text = clean_ws("".join(self.heading['parts']))
                if text:
                    self.events.append(('heading', self.heading['level'], text))
                self.heading = None
            return
        if tag == 'div':
            if self.para is not None and self.div_depth == self.para['depth_at_open']:
                if self.para['num'] is None:
                    # No label tag at all resolved this - last resort: a leading
                    # number in the paragraph's own text, else just inherit the
                    # previous real paragraph number rather than ever emitting
                    # an unresolved/bogus one.
                    m = re.match(r'(\d+)', plain_text_of_parts(self.para['parts']))
                    self.para['num'] = int(m.group(1)) if m else self.last_num
                html_frag = render_para_parts(self.para['parts'])
                if html_frag:
                    self.events.append(('para', self.para['num'], html_frag))
                self.last_num = self.para['num']
                self.para = None
            elif self.tag_stack and self.tag_stack[-1][0] == 'div':
                self.tag_stack.pop()
            self.div_depth -= 1
            return
        if self.para is None:
            return
        if self.tag_stack and self.tag_stack[-1][0] == tag:
            _, close_markup = self.tag_stack.pop()
            if close_markup:
                self.para['parts'].append(('html', close_markup))
            if tag == 'span' and close_markup == '</b>':
                self.foreign_depth -= 1

    def handle_data(self, data):
        if self.suppress_heading:
            if self.label_parts is not None:
                self.label_parts.append(data)
        elif self.heading is not None:
            self.heading['parts'].append(data)
        elif self.para is not None:
            self.para['parts'].append(('text', data))


def group_events_into_topics(events, fallback_heading, source):
    """Groups a flat (heading|para) event stream into topic entries: every
    heading starts a new topic; paragraphs before the first heading in a
    file fall under that file's own top-level title. Each topic keeps its
    paragraphs as separate (num, html) pairs rather than one joined blob, so
    they can be rendered as distinct, numbered, spaced-out blocks."""
    topics = []
    current = {'heading': fallback_heading, 'nums': [], 'paras': []}
    for kind, a, b in events:
        if kind == 'heading':
            if current['nums']:
                topics.append(current)
            current = {'heading': b, 'nums': [], 'paras': []}
        else:
            num, html_frag = a, b
            current['nums'].append(num)
            if html_frag:
                current['paras'].append((num, html_frag))
    if current['nums']:
        topics.append(current)
    for t in topics:
        t['source'] = source
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

def _render_para_html(el):
    """Renders an element's content to safe HTML: plain English text is
    escaped, and any <foreign> tag's Beta Code is converted to Unicode Greek
    and wrapped for styling - at whatever depth it appears, not just direct
    children."""
    parts = []
    if el.text:
        parts.append(html_lib.escape(el.text))
    for child in el:
        if child.tag.split('}')[-1] == 'foreign':
            greek = beta_to_unicode("".join(child.itertext()))
            parts.append(f'<b class="gk-word">{html_lib.escape(greek)}</b>')
        else:
            parts.append(_render_para_html(child))
        if child.tail:
            parts.append(html_lib.escape(child.tail))
    return "".join(parts)

def parse_goodwin():
    tree = ET.parse(GOODWIN_XML_PATH)
    root = tree.getroot()
    topics = []
    word_index = defaultdict(set)

    body = root.find('.//body')
    if body is None:
        return topics, word_index

    current = {'heading': 'Goodwin', 'nums': [], 'paras': []}
    current_num = 0

    def flush():
        if current['nums']:
            current['source'] = 'Goodwin'
            topics.append(dict(current))

    for el in body.iter():
        tag = el.tag.split('}')[-1]
        if tag == 'head':
            flush()
            # Headings are plain English (no embedded Greek here) - unlike
            # <p> body text, don't run this through beta_to_unicode.
            text = clean_ws("".join(el.itertext()))
            current = {'heading': text, 'nums': [], 'paras': []}
        elif tag == 'milestone' and el.attrib.get('unit') == 'smythp':
            current_num = int(el.attrib.get('n', current_num))
            current['nums'].append(current_num)
        elif tag == 'p':
            html_frag = re.sub(r'\s+', ' ', _render_para_html(el)).strip()
            if re.sub(r'<[^>]+>', '', html_frag).strip():
                current['paras'].append((current_num, html_frag))
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

# --- In-prose cross-reference links ---

# Smyth and Goodwin both cross-reference their own other paragraphs with a
# bare section number after "see", "see also", or "cf." (e.g. "see 348",
# "cf. 2420") rather than any markup - so this is a plain-text convention we
# have to recognize, not something already tagged in the source. The clause
# capture stops at '<' so it never reaches into a following tag's markup.
_CROSSREF_CLAUSE_RE = re.compile(r'\b(see also|see|cf\.)(\s+)([^<>.;)\n]*?)(?=[.;)<\n]|$)')
_CROSSREF_NUM_RE = re.compile(r'\b\d+\b')

def linkify_crossrefs(html_frag, prefix, valid_nums):
    """Turns bare-number cross-references after 'see'/'see also'/'cf.' into
    x-dictionary:d: links to that paragraph's own entry in this same
    dictionary. Only numbers that are themselves indexed paragraph numbers
    elsewhere in the same grammar (valid_nums) get linked, so a stray count
    or footnote digit that happens to follow 'see' doesn't turn into a dead
    link."""
    def link_number(m):
        n = m.group(0)
        if int(n) not in valid_nums:
            return n
        term = f'{prefix}. {n}'
        href = f'x-dictionary:d:{urllib.parse.quote(term)}:{GRAMMAR_DICT_BUNDLE_ID}'
        return f'<a href="{href}">{n}</a>'

    def link_clause(m):
        keyword, space, clause = m.group(1), m.group(2), m.group(3)
        return f'{keyword}{space}{_CROSSREF_NUM_RE.sub(link_number, clause)}'

    return _CROSSREF_CLAUSE_RE.sub(link_clause, html_frag)

def valid_paragraph_numbers(topics):
    nums = set()
    for t in topics:
        nums.update(t['nums'])
    return nums

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
    valid_nums_by_source = {
        'Smyth': valid_paragraph_numbers(smyth_topics),
        'Goodwin': valid_paragraph_numbers(goodwin_topics),
    }

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
            # Every paragraph gets its own numbered, spaced-out block rather
            # than being joined into one wall of text - the source's own
            # section numbers (e.g. "768.") act as signposts through a long
            # multi-paragraph discussion like an irregular verb's full paradigm.
            multi_para = len(t['paras']) > 1
            valid_nums = valid_nums_by_source[t['source']]
            for num, html_frag in t['paras']:
                html_frag = linkify_crossrefs(html_frag, prefix, valid_nums)
                out.write('        <div class="grammar-para">')
                if multi_para:
                    out.write(f'<span class="para-num">{prefix}. {num}</span> ')
                out.write(f'{html_frag}</div>\n')
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
