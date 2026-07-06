import json
import os
import sqlite3
import html
import re
import xml.etree.ElementTree as ET
import unicodedata
from collections import defaultdict

# --- Paths ---
TEI_XML_DIR = 'data/lsj_unicode/'
MORPH_DB_PATH = 'data/morph.db'
OUTPUT_XML_PATH = 'src/GreekDictionary.xml'
GRAMMAR_WORD_INDEX_PATH = 'data/grammar_word_index.json'
# Below this many paragraph references across Smyth+Goodwin, a word is more
# likely a one-off example citation than an entry the grammars are actually
# *about* - particles/conjunctions/verbs-with-special-constructions clear
# this easily (ἄν: 370, μή: 253, βούλομαι: 15); ordinary vocabulary quoted
# once or twice in an illustrative sentence doesn't.
GRAMMAR_CROSSREF_MIN_REFS = 3

# Classical six principal parts shown first, in traditional order.
# Anything not in this set (Imperfect, Pluperfect, Future Perfect, etc.) goes to secondary.
# NOTE: the morphology DB reports voice as "middle/passive" (not separate
# "middle"/"passive" rows) for the present, imperfect, perfect, and pluperfect
# systems, since Greek middle and passive forms are identical there - they only
# diverge in the aorist and future systems. Matching on the combined label is
# required, or these principal parts silently fall through to "secondary".
PRINCIPAL_PARTS_ORDER = [
    'Present Active', 'Present Middle/Passive',
    'Future Active',  'Future Middle', 'Future Passive',
    'Aorist Active',  'Aorist Middle', 'Aorist Passive',
    'Perfect Active', 'Perfect Middle/Passive',
]
PRINCIPAL_PARTS_PRIMARY = frozenset(PRINCIPAL_PARTS_ORDER)

def sanitize_apple_key(text):
    if not text: return ""
    kw = text.strip()
    kw = unicodedata.normalize('NFC', kw)
    while kw and not unicodedata.category(kw[0]).startswith(('L', 'N')):
        kw = kw[1:]
    return kw

def clean_text_for_apple(text):
    """Removes hidden control codes and flattens white spaces to protect Apple's DDK."""
    if not text: return ""
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    text = text.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def strip_greek_vowel_lengths(text):
    """Removes dictionary-specific macrons and breves for clean searches."""
    if not text: return ""
    decomposed = unicodedata.normalize('NFD', text)
    filtered = "".join(ch for ch in decomposed if ord(ch) not in (0x0304, 0x0306))
    return unicodedata.normalize('NFC', filtered)

def normalize_grave_to_acute(text):
    """Converts grave accents to acute so text-selection Look Up matches dictionary entries."""
    if not text: return ""
    decomposed = unicodedata.normalize('NFD', text)
    normalized = decomposed.replace('\u0300', '\u0301')  # grave → acute
    return unicodedata.normalize('NFC', normalized)

def normalize_acute_to_grave(text):
    """Converts acute accents to grave; indexes both variants for robust lookup."""
    if not text: return ""
    decomposed = unicodedata.normalize('NFD', text)
    normalized = decomposed.replace('\u0301', '\u0300')  # acute → grave
    return unicodedata.normalize('NFC', normalized)

def strip_all_greek_accents(text):
    """Strips every combining diacritic for fully accent-insensitive fallback lookup."""
    if not text: return ""
    # Combining: grave 0300, acute 0301, circumflex 0302, macron 0304, breve 0306,
    # diaeresis 0308, smooth breathing 0313, rough breathing 0314, iota subscript 0345
    STRIP = {0x0300,0x0301,0x0302,0x0304,0x0306,0x0308,0x0313,0x0314,0x0345}
    decomposed = unicodedata.normalize('NFD', text)
    filtered = "".join(ch for ch in decomposed if ord(ch) not in STRIP)
    return unicodedata.normalize('NFC', filtered)

CAPITAL_LETTER_RE = re.compile(r'^[A-Z]\.?$')
ROMAN_NUM_RE = re.compile(r'^[IVXivx]+\.?$')
ARABIC_NUM_RE = re.compile(r'^\d+\.?$')
LOWER_LETTER_RE = re.compile(r'^[a-z]\.?$')

_CITATION_ABBR_DOTTED_RE = re.compile(r'^(?:[A-Za-z]+\.)+$')   # "Il.", "A.", "D.H.", "PMag.Leid.W."
_CITATION_ABBR_CAPS_RE = re.compile(r'^[A-Z]{2,4}$')            # "AP", "SIG", "CIG", "IG"
_CITATION_NUMERAL_RE = re.compile(r'^\d+[a-z]?(?:[.,]\d+[a-z]?)*$')  # "9.116", "342b", "5053,5119"

def _is_citation_abbr_atom(tok):
    """A token that looks like an LSJ citation siglum (author/work abbreviation)."""
    if not tok or not tok[0].isupper():
        return False
    if ROMAN_NUM_RE.match(tok.rstrip('.,;:')):
        return False  # sense cross-refs (II, III...) aren't citation sigla
    if _CITATION_ABBR_DOTTED_RE.match(tok):
        return True
    return bool(_CITATION_ABBR_CAPS_RE.match(tok.rstrip(',;:')))

def _is_citation_numeral_atom(tok):
    """A token that looks like a citation locator (book/line/page number)."""
    core = tok.rstrip('.,;:()')
    return bool(core) and bool(_CITATION_NUMERAL_RE.match(core))

def strip_citation_apparatus(text, min_offset=5, lookahead=3):
    """Cut brief text at the start of LSJ's citation apparatus.

    Unlike parenthetical citations like "(Pl. ...)", LSJ's bare citations
    (e.g. "Il. 9.116", "AP 7", "CIG 5053,5119") aren't wrapped in anything
    distinctive, so a plain regex either misses them (no trailing period on
    "AP") or clips grammatical register labels that share the same shape
    ("Act.", "Dim.", "Pass." at the very start of a gloss). Instead, scan
    token by token for a citation siglum that is itself followed - within a
    short lookahead, skipping over further sigla - by a numeral; that
    combination (siglum + locator) is the actual signature of a citation,
    not just a capitalized abbreviation on its own.
    """
    tokens = text.split(' ')
    offsets = []
    pos = 0
    for t in tokens:
        offsets.append(pos)
        pos += len(t) + 1

    for i, tok in enumerate(tokens):
        if not _is_citation_abbr_atom(tok) or offsets[i] <= min_offset:
            continue
        found_numeral, ok = False, True
        for t2 in tokens[i + 1: i + 1 + lookahead]:
            if _is_citation_numeral_atom(t2):
                found_numeral = True
                break
            if not _is_citation_abbr_atom(t2):
                ok = False
                break
        if ok and found_numeral:
            return " ".join(tokens[:i]).rstrip(' ,;')
    return text

def sense_depth_from_n(n_val):
    """Infer visual indentation depth from the TEI sense n-attribute.
    
    Hierarchy:
    - Bullet (•) = special marker, rendered as intro text (no depth)
    - Roman numerals (I, II, III) = depth 1 (major senses) — MUST check BEFORE capitals!
    - Capital letters (A, B, C) = depth 0 (top-level, case-governance headers)
    - Arabic numerals (1, 2, 3) = depth 2 (sub-senses)
    - Lowercase letters (a, b, c) = depth 3 (sub-sub-senses)
    """
    if not n_val:
        return 1   # No n-attribute — treat as major sense (like Roman numerals)
    n = n_val.strip().rstrip('.')
    if n == '•':
        return -1  # Bullet — special marker, not a sense level
    if ROMAN_NUM_RE.match(n):
        return 1   # I, II, III … — major sense (CHECK BEFORE capitals!)
    if CAPITAL_LETTER_RE.match(n):
        return 0   # A, B, C … — top-level (after Roman check)
    if ARABIC_NUM_RE.match(n):
        return 2   # 1, 2, 3 … — sub-sense
    if LOWER_LETTER_RE.match(n):
        return 3   # a, b, c … — sub-sub-sense
    return 4       # anything deeper

def _clean_and_truncate_brief(text, max_chars=200, for_overview=False):
    """Shared cleanup/truncation logic for brief summaries: strips citations and
    cross-references, then truncates to a sensible length. Used both for
    per-sense summaries and for synthetic-heading preamble summaries.
    
    Args:
        text: Raw, already-flattened text to clean up
        max_chars: Maximum characters (200 for full, 150 for overview)
        for_overview: If True, use a shorter limit and stop at the first sentence
    """
    # Remove citations and cross-references more aggressively
    text = strip_citation_apparatus(text)  # bare citations, e.g. "Il. 9.116", "AP 7"
    text = re.sub(r'\s+\(cf\..*?\)', '', text, flags=re.DOTALL)  # (cf. ...)
    text = re.sub(r'\s+\([A-Z][a-z]+\..*?\)', '', text, flags=re.DOTALL)  # (Pl. ...), (Hdt. ...), etc
    text = re.sub(r'\s+v\.\s+.*$', '', text, flags=re.DOTALL)  # v. ref
    text = re.sub(r'\s*(cf\.|etc\.)\s*.*$', '', text, flags=re.IGNORECASE | re.DOTALL)  # cf., etc.
    text = re.sub(r'\s+;.*$', '', text)  # Remove everything after semicolon
    
    text = re.sub(r'\s+', ' ', text).strip()
    
    # For overview, use a longer-but-still-brief limit and stop at the first
    # full sentence (period) rather than the first comma, so the reader gets
    # at least "the first line" of meaningful context rather than one word.
    # A bare "first period in the string" is the wrong test: LSJ is full of
    # abbreviation dots that aren't sentence ends (author sigla like "Hdt.",
    # "S.", or a self-referential single-letter shorthand for the entry's own
    # headword, e.g. "λ." standing in for λόγος inside its own definition) -
    # matching on those truncates mid-thought and leaves a dangling letter.
    # A real sentence boundary in these glosses is followed by a capitalized
    # English word (the next clause) or is the end of the string outright.
    if for_overview:
        max_chars = min(150, max_chars)
        match = re.search(r'\.(?=\s+[A-Z]|\s*$)', text)
        if match and match.start() > 5:  # Only if meaningful content before
            text = text[:match.start()].strip()
    
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + '\u2026'
    
    return text

def brief_sense_text(node, max_chars=200, for_overview=False):
    """Extract a meaningful snippet from a sense node for the overview.
    
    Includes text from inline children (bold, italic, citations) but not
    from nested sense sub-nodes.
    
    Args:
        node: The sense element
        max_chars: Maximum characters (200 for full, 150 for overview)
        for_overview: If True, use shorter limit and stop at first sentence
    """
    # Collect text from direct node content + inline children, skipping nested senses
    parts = []
    if node.text:
        parts.append(node.text)
    for child in node:
        if child.tag.split('}')[-1] != 'sense':  # Skip nested senses
            parts.append("".join(child.itertext()))
            if child.tail:
                parts.append(child.tail)
    text = clean_text_for_apple("".join(parts).strip())
    return _clean_and_truncate_brief(text, max_chars=max_chars, for_overview=for_overview)

def extract_preamble_text(entry, head_node, max_chars=200, for_overview=False):
    """Extract the free-form content TEI leaves directly under the entry before
    its first <sense> child - typically the principal-parts/tense-form preamble
    that precedes the first definition (e.g. a verb's "impf. ἔλειπον ...: fut.
    λείψω ...:"). Used to give a synthetic top-level heading (e.g. "A") real
    content when no wrapping <sense> exists for it in the TEI source at all.
    """
    children = list(entry)
    if head_node not in children:
        return ""
    parts = []
    if head_node.tail:
        parts.append(head_node.tail)
    for child in children[children.index(head_node) + 1:]:
        if child.tag.split('}')[-1] == 'sense':
            break  # Stop at the first real sense
        parts.append("".join(child.itertext()))
        if child.tail:
            parts.append(child.tail)
    text = clean_text_for_apple("".join(parts).strip())
    # Drop the leftover leading punctuation from the head's trailing comma/colon
    text = re.sub(r'^[\s,;:.\u2014-]+', '', text)
    return _clean_and_truncate_brief(text, max_chars=max_chars, for_overview=for_overview)

GENDER_LABELS = {
    'ὁ': 'masc.', 'οἱ': 'masc. pl.',
    'ἡ': 'fem.', 'αἱ': 'fem. pl.', 'ἁ': 'fem.',
    'τό': 'neut.', 'τά': 'neut. pl.',
}
POS_LABELS = {
    'Adv.': 'adverb', 'adv.': 'adverb',
    'Adj.': 'adjective',
    'Subst.': 'substantive',
}
GRAM_TYPE_LABELS = {
    'dialect': None,  # already a human-readable abbreviation, e.g. "Ep.", "Dor." - shown as-is
    'voice': 'voice',
    'comp': 'comparative',
    'dim': 'diminutive',
    'var': 'variant',
}

def get_preamble_children(entry, head_node):
    """The entry's preamble: children directly under the entry, after the
    headword and before the first <sense>. This is where ~90%+ of grammar/
    etymology tags live (the rest are per-sense notes, e.g. "as Subst." on
    one numbered sense - see extract_grammar_and_etymology, which handles
    both regions with the same logic)."""
    children = list(entry)
    if head_node not in children:
        return []
    preamble_nodes = []
    for child in children[children.index(head_node) + 1:]:
        if child.tag.split('}')[-1] == 'sense':
            break
        preamble_nodes.append(child)
    return preamble_nodes

def _flatten_region(nodes):
    """Flatten a list of elements into themselves plus all descendants,
    without crossing into a nested <sense> - those are rendered as their
    own independent sense blocks elsewhere, so their grammar/etymology tags
    belong to that sense's own extraction call, not this region's."""
    out = []
    for node in nodes:
        if node.tag.split('}')[-1] == 'sense':
            continue
        out.append(node)
        out.extend(_flatten_region(list(node)))
    return out

def extract_grammar_and_etymology(region_nodes):
    """Pull structured grammar (part of speech, gender, declension class,
    dialect/voice/comparative/diminutive/variant labels) and etymology
    (LSJ's bare "derived from X" cross-reference) out of a region of the
    entry - either its preamble (get_preamble_children) or a single sense's
    own content (its direct children, excluding nested sub-senses).
    """
    flat = _flatten_region(region_nodes)

    def collect(tag):
        seen, out = set(), []
        for node in flat:
            if node.tag.split('}')[-1] == tag:
                val = clean_text_for_apple("".join(node.itertext())).strip()
                if val and val not in seen:
                    seen.add(val)
                    out.append(val)
        return out

    gram_pairs = []
    seen_gram = set()
    for node in flat:
        if node.tag.split('}')[-1] == 'gram':
            gtype = node.attrib.get('type', '')
            gtext = clean_text_for_apple("".join(node.itertext())).strip()
            key = (gtype, gtext)
            if gtext and key not in seen_gram:
                seen_gram.add(key)
                gram_pairs.append(key)

    return {
        'pos': collect('pos'),
        'gen': collect('gen'),
        'itype': collect('itype'),
        'gram': gram_pairs,
        'etym': collect('etym'),
    }

def _build_grammar_badges(info):
    """Turn extract_grammar_and_etymology's output into a list of human-
    readable badge labels (part of speech, gender, declension suffix,
    dialect/voice/comparative/diminutive/variant)."""
    badges = []
    for pos in info.get('pos', []):
        badges.append(POS_LABELS.get(pos, pos))
    for gen in info.get('gen', []):
        badges.append(GENDER_LABELS.get(gen, gen))
    if info.get('itype'):
        badges.append('decl. ' + ', '.join(info['itype']))
    for gtype, gtext in info.get('gram', []):
        label = GRAM_TYPE_LABELS.get(gtype, gtype)
        badges.append(gtext if label is None else f'{label}: {gtext}')
    return badges

def render_grammar_html(info):
    """Build the labeled 'Grammar' badge row for the whole entry, sourced
    from its preamble. Returns "" if there's nothing to show."""
    badges = _build_grammar_badges(info)
    if not badges:
        return ""
    spans = "".join(f'<span class="gram-badge">{html.escape(b)}</span>' for b in badges)
    return f'        <div class="entry-grammar">{spans}</div>\n'

def render_sense_grammar_badges(info):
    """Same badge content as render_grammar_html, but as bare inline spans
    (no wrapping block div) meant to sit inside a single sense's own div,
    right before its body text - for grammar tags nested on one specific
    numbered sense (e.g. "as Subst." on just sense II) rather than the whole
    entry. Returns "" if there's nothing to show."""
    badges = _build_grammar_badges(info)
    if not badges:
        return ""
    return "".join(f'<span class="sense-gram-badge">{html.escape(b)}</span> ' for b in badges)

def render_etymology_html(info):
    """Build the 'Related to: X' etymology line. Returns "" if there's nothing
    to show. LSJ's <etym> is a bare cross-reference, not prose derivation
    history, so this is intentionally a single labeled line, not a narrative."""
    etyms = info.get('etym', [])
    if not etyms:
        return ""
    words = ", ".join(f'<b class="gk-word">{html.escape(e)}</b>' for e in etyms)
    return f'        <div class="entry-etymology"><span class="etym-label">Related to:</span> {words}</div>\n'

def load_grammar_word_index():
    """Loads the word -> [(source, paragraph number), ...] index built by
    build_grammar_reference.py from Smyth's and Goodwin's grammars. Optional:
    the main LSJ build still works without it (e.g. before that script has
    been run), just without the cross-reference line."""
    if not os.path.exists(GRAMMAR_WORD_INDEX_PATH):
        print(f"⚠️  {GRAMMAR_WORD_INDEX_PATH} not found - skipping grammar cross-references "
              f"(run scripts/build_grammar_reference.py first to enable them).")
        return {}
    with open(GRAMMAR_WORD_INDEX_PATH, encoding='utf-8') as f:
        raw = json.load(f)
    return {word.lower(): [tuple(ref) for ref in refs] for word, refs in raw.items()}

def render_grammar_crossref_html(refs):
    """Build the 'Grammar & Syntax: see Smyth/Goodwin' line for a headword
    that Smyth and/or Goodwin discuss by name (particles, conjunctions, and
    verbs taking special constructions - not ordinary vocabulary, which this
    is filtered against via GRAMMAR_CROSSREF_MIN_REFS before being called).
    Only cites a handful of paragraphs per source plus a total count, since
    some particles (e.g. ἄν) have hundreds of references."""
    by_source = defaultdict(list)
    for source, num in refs:
        by_source[source].append(num)
    parts = []
    for source in ('Smyth', 'Goodwin'):
        nums = sorted(set(by_source.get(source, [])))
        if not nums:
            continue
        shown = ", ".join(str(n) for n in nums[:5])
        suffix = f', et al. ({len(nums)} total)' if len(nums) > 5 else ''
        parts.append(f'{source} §{shown}{suffix}')
    if not parts:
        return ""
    return f'        <div class="entry-grammar-crossref"><span class="etym-label">Grammar &amp; Syntax:</span> {"; ".join(parts)}</div>\n'

def parse_sense_node(node, depth=0, num_override=None):
    """
    Recursively processes mixed-content TEI sense blocks, translating
    inline language tags to clean, stylized HTML presentation layers.

    Args:
        node: The TEI sense element
        depth: Visual indentation depth (0=top, 1=sub, 2=sub-sub, etc.)
        num_override: Custom number label to use instead of n-attribute
    """
    sense_html = ""
    num_marker = num_override if num_override else clean_text_for_apple(node.attrib.get('n', ''))
    
    fragments = []
    if node.text:
        fragments.append(html.escape(clean_text_for_apple(node.text)))
        
    for child in node:
        tag_local = child.tag.split('}')[-1]
        if tag_local == 'sense': 
            continue  # Sub-senses are handled recursively below
            
        # Safely extract all embedded text strings inside this node
        child_text = "".join(child.itertext())
        child_text = clean_text_for_apple(child_text)
        
        # Apply professional structural typography styling
        if tag_local in ('foreign', 'orth', 'headword'):
            fragments.append(f'<b class="gk-word">{html.escape(child_text)}</b>')
        elif tag_local in ('hi', 'title', 'author'):
            fragments.append(f'<i>{html.escape(child_text)}</i>')
        elif tag_local in ('bibl', 'cit'):
            fragments.append(f'<span class="citation">{html.escape(child_text)}</span>')
        else:
            fragments.append(html.escape(child_text))
            
        if child.tail:
            fragments.append(html.escape(clean_text_for_apple(child.tail)))
            
    inline_content = " ".join(fragments)
    inline_content = re.sub(r'\s+', ' ', inline_content).strip()

    # Grammar tags nested on this specific sense (e.g. "as Subst." marking
    # just one numbered sense as a different part of speech) - the majority
    # of <pos>/<gramGrp> occurrences are here rather than in the entry
    # preamble, so they need their own extraction pass per sense.
    sense_grammar_badges = render_sense_grammar_badges(extract_grammar_and_etymology(list(node)))

    # Mark Roman numerals (depth 1) as major sense sections
    is_major = bool(depth == 1 and num_marker and ROMAN_NUM_RE.match(num_marker.strip()))

    if num_marker or inline_content:
        depth_class = f'sense-depth-{min(depth, 4)}'
        major_class = ' sense-major' if is_major else ''
        sense_html += f'<div class="sense {depth_class}{major_class}">'
        if num_marker:
            sense_html += f'<span class="sense-num">{html.escape(num_marker)}</span> '
        if sense_grammar_badges:
            sense_html += sense_grammar_badges
        if inline_content:
            sense_html += f'<span class="sense-body">{inline_content}</span>'
        sense_html += '</div>'

    return sense_html

def build_unabridged_dictionary():
    print("🏗️  Initializing Chicago Unicode TEI-XML Lexicon compiler...")
    
    if not os.path.exists(MORPH_DB_PATH):
        print(f"❌ Error: Morphology database not found at {MORPH_DB_PATH}")
        return

    morph_conn = sqlite3.connect(MORPH_DB_PATH)
    morph_cursor = morph_conn.cursor()

    grammar_word_index = load_grammar_word_index()

    if not os.path.exists(TEI_XML_DIR):
        print(f"❌ Error: Target repository path missing at {TEI_XML_DIR}")
        return
        
    xml_files = []
    for root_dir, _, files in os.walk(TEI_XML_DIR):
        for f in files:
            if f.endswith('.xml'):
                xml_files.append(os.path.join(root_dir, f))
                
    if not xml_files:
        print("❌ Error: No XML source chunks discovered in Chicago repository.")
        return
        
    print(f"📚 Found {len(xml_files)} Unicode XML segments to digest.")
    entry_counter = 0

    with open(OUTPUT_XML_PATH, 'w', encoding='utf-8') as out_xml:
        out_xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        out_xml.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')

        for file_idx, xml_path in enumerate(sorted(xml_files)):
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
            except Exception:
                continue

            # UNIVERSAL SELECTOR: Targets Chicago's <div2> elements alongside standard entry tags
            entries = [n for n in root.iter() if n.tag.split('}')[-1] in ('div2', 'entry', 'entryFree')]
            if not entries: continue
            
            parent_map = {c: p for p in root.iter() for c in p}
            
            for entry in entries:
                head_node = None
                for sub in entry.iter():
                    tag_local = sub.tag.split('}')[-1]
                    if tag_local in ('head', 'headword', 'orth'):
                        head_node = sub
                        break
                        
                if head_node is None: 
                    continue
                
                raw_lemma = clean_text_for_apple("".join(head_node.itertext()))
                # Ignore metadata structures or plain numeric page breaks
                if not raw_lemma or raw_lemma.replace('-', '').isdigit() or "Preface" in raw_lemma:
                    continue
                
                lookup_lemma = strip_greek_vowel_lengths(raw_lemma)
                safe_title = sanitize_apple_key(lookup_lemma)
                if not safe_title: safe_title = "unknown"
                
                entry_counter += 1
                entry_id = f"lsj_entry_{entry_counter}"
                
                out_xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(safe_title)}">\n')
                
                search_indices = {raw_lemma, lookup_lemma}
                # Also index grave→acute, acute→grave, and fully unaccented forms so macOS
                # Look Up works regardless of accent variant in running text.
                search_indices.add(normalize_grave_to_acute(raw_lemma))
                search_indices.add(normalize_acute_to_grave(raw_lemma))
                search_indices.add(strip_all_greek_accents(raw_lemma))
                morph_cursor.execute("SELECT form, form_normalized, pos, tense, voice, mood, person, number, case_name FROM morphology WHERE lemma = ?", (lookup_lemma,))
                morph_rows = morph_cursor.fetchall()
                
                is_verb, is_noun_adj = False, False
                noun_grid = defaultdict(lambda: defaultdict(set))
                verb_principal_parts = defaultdict(set)
                
                for mr in morph_rows:
                    f_form, f_norm, pos, tense, voice, mood, person, number, case_name = mr
                    if f_form:
                        f_clean = clean_text_for_apple(f_form)
                        search_indices.add(f_clean)
                        search_indices.add(strip_greek_vowel_lengths(f_clean))
                        search_indices.add(normalize_grave_to_acute(f_clean))
                        search_indices.add(normalize_acute_to_grave(f_clean))
                        search_indices.add(strip_all_greek_accents(f_clean))
                    if f_norm:
                        n_clean = clean_text_for_apple(f_norm)
                        search_indices.add(n_clean)
                        search_indices.add(strip_greek_vowel_lengths(n_clean))
                        search_indices.add(normalize_grave_to_acute(n_clean))
                        search_indices.add(normalize_acute_to_grave(n_clean))
                        search_indices.add(strip_all_greek_accents(n_clean))
                    
                    disp_form = html.escape(clean_text_for_apple(f_form))
                    if pos == 'verb':
                        is_verb = True
                        if person == '1st' and number == 'singular' and mood == 'indicative':
                            # Title-case each word so multi-word tenses ("future
                            # perfect") and combined voices ("middle/passive",
                            # which is how identical middle/passive forms in the
                            # present/perfect systems are stored) render cleanly.
                            tense_display = " ".join(w.capitalize() for w in str(tense).split())
                            voice_display = "/".join(w.capitalize() for w in str(voice).split("/"))
                            label = f"{tense_display} {voice_display}".strip()
                            verb_principal_parts[label].add(disp_form)
                    elif pos in ('noun', 'adjective', 'article', 'pronoun'):
                        is_noun_adj = True
                        if case_name and number:
                            noun_grid[case_name][number].add(disp_form)

                for keyword in search_indices:
                    clean_kw = sanitize_apple_key(keyword)
                    if clean_kw:
                        out_xml.write(f'        <d:index d:value="{html.escape(clean_kw)}"/>\n')

                out_xml.write(f'        <h1 class="entry-lemma">{html.escape(raw_lemma)}</h1>\n')

                grammar_info = extract_grammar_and_etymology(get_preamble_children(entry, head_node))
                out_xml.write(render_grammar_html(grammar_info))
                out_xml.write(render_etymology_html(grammar_info))

                grammar_refs = grammar_word_index.get(strip_all_greek_accents(raw_lemma).lower(), [])
                if len(grammar_refs) >= GRAMMAR_CROSSREF_MIN_REFS:
                    out_xml.write(render_grammar_crossref_html(grammar_refs))

                out_xml.write('        <div class="definition">\n')
                
                all_senses = [c for c in entry.iter() if c.tag.split('}')[-1] == 'sense']

                # Build overview:
                # - If entry has capitals: show ONLY capitals
                # - If entry has NO capitals: show ONLY Romans
                overview_items = []

                def clean_n(sense_node):
                    return clean_text_for_apple(sense_node.attrib.get('n', '')).strip()

                non_bullet_senses = [s for s in all_senses if clean_n(s) != '•']

                # First check: do we have any capitals?
                # IMPORTANT: Check ROMAN_NUM_RE before CAPITAL_LETTER_RE to avoid matching I, V, X
                has_capitals = any(
                    CAPITAL_LETTER_RE.match(clean_n(s))
                    for s in non_bullet_senses
                    if clean_n(s) and not ROMAN_NUM_RE.match(clean_n(s))
                )
                has_romans = any(ROMAN_NUM_RE.match(clean_n(s)) for s in non_bullet_senses if clean_n(s))
                has_explicit_A = any(clean_n(s).rstrip('.') == 'A' for s in non_bullet_senses)
                has_explicit_I = any(clean_n(s).rstrip('.') == 'I' for s in non_bullet_senses)

                # The Chicago TEI source frequently leaves the very first top-level
                # division either blank (n="") or entirely unwrapped (no <sense> at
                # all before it). Printed LSJ always labels that leading division as
                # the first letter/numeral of whichever scheme the entry uses ("A"
                # for capital-lettered entries, "I" for Roman-numbered ones). Without
                # this reconstruction, that first heading (and its summary) silently
                # disappears from both the overview box and the main content.
                #
                # Two distinct situations occur in the source:
                #  - A placeholder <sense n=""> exists holding the real definition
                #    text (e.g. ἀγαθός: "good:", πηρός: "disabled in a limb..."). By
                #    print convention this leading division is ALWAYS "A" - the top
                #    of the LSJ hierarchy - no matter what scheme (Roman, Arabic, or
                #    nothing) is used further down inside the entry.
                #  - No placeholder sense exists at all (e.g. λείπω, where content
                #    jumps straight to arabic sub-senses). Only then do we fall back
                #    to inspecting the entry's actual capital/Roman scheme to decide
                #    whether a bare "A"/"I" heading needs to be injected.
                first_non_bullet = next((s for s in all_senses if clean_n(s) != '•'), None)
                first_is_placeholder = first_non_bullet is not None and clean_n(first_non_bullet) == ''

                synthetic_label = None
                if first_is_placeholder:
                    if not has_explicit_A:
                        synthetic_label = 'A'
                elif has_capitals and not has_explicit_A:
                    synthetic_label = 'A'
                elif not has_capitals and has_romans and not has_explicit_I:
                    synthetic_label = 'I'

                # Resolve the render order + label for every sense. If a leading
                # empty-n placeholder sense exists, absorb the synthetic label into
                # it (its body text is preserved). If no placeholder sense exists at
                # all, inject a bare heading immediately before the first real sense.
                render_items = []  # (sense_or_None, label_or_None, is_synthetic)
                synthetic_applied = (synthetic_label is None)
                for s in all_senses:
                    n_val = clean_n(s)
                    if n_val == '•':
                        render_items.append((s, None, False))
                        continue
                    if not synthetic_applied:
                        if n_val == '':
                            render_items.append((s, synthetic_label, False))
                            synthetic_applied = True
                            continue
                        else:
                            render_items.append((None, synthetic_label, True))
                            render_items.append((s, n_val, False))
                            synthetic_applied = True
                            continue
                    render_items.append((s, n_val, False))

                # Entry-level preamble (pronunciation, dialect variants, gender
                # endings) sits directly under the entry before its first <sense>
                # and is otherwise silently dropped. Show it once, either as its
                # own intro line, or - if it was already absorbed into a Type-2
                # synthetic heading below (no placeholder sense existed) - skip it
                # here to avoid printing the same text twice.
                leading_is_synthetic_injection = bool(render_items) and render_items[0][2] is True
                if not leading_is_synthetic_injection:
                    entry_preamble = extract_preamble_text(entry, head_node, max_chars=300, for_overview=False)
                    if entry_preamble:
                        out_xml.write(f'        <div class="entry-preamble">{html.escape(entry_preamble)}</div>\n')

                # Decide the overview scheme from the RESOLVED labels (i.e. after
                # the synthetic "A"/"I" reconstruction above), not the raw source
                # letters. Two shapes occur:
                #  - Multi-capital entries (A, B, C... e.g. παρά, εἰμί): each
                #    capital re-starts its own Roman sub-numbering (I, II... under
                #    A, then I, II... again under B). Those Romans are nested
                #    sub-divisions, so only the capitals belong in the overview.
                #  - Single-capital entries (just "A", real or synthesized, e.g.
                #    ἀγαθός, μανθάνω, παιδεύω): the Roman numerals that follow are
                #    NOT a nested sub-scheme restarting under a sibling capital -
                #    they're peers continuing the same top-level enumeration. Both
                #    the singleton "A" and every Roman numeral belong in the
                #    overview, otherwise real, important senses (e.g. μανθάνω's
                #    "A learn, esp. by study...") silently vanish from the box.
                capital_labels_resolved = {
                    label.rstrip('.') for _, label, _ in render_items
                    if label and CAPITAL_LETTER_RE.match(label) and not ROMAN_NUM_RE.match(label)
                }
                capitals_only_scheme = len(capital_labels_resolved) >= 2

                for s, label, is_synth in render_items:
                    if not label or label == '•':
                        continue
                    # IMPORTANT: Check ROMAN_NUM_RE before CAPITAL_LETTER_RE to prevent I/V/X confusion
                    is_roman = bool(ROMAN_NUM_RE.match(label))
                    is_capital = (not is_roman) and bool(CAPITAL_LETTER_RE.match(label))
                    if not (is_capital or is_roman):
                        continue
                    if capitals_only_scheme and not is_capital:
                        continue  # nested Roman sub-division under a sibling capital
                    brief = extract_preamble_text(entry, head_node, for_overview=True) if is_synth else brief_sense_text(s, for_overview=True)
                    if is_roman:
                        # Always add Roman numerals to overview, even without text
                        overview_items.append((label, brief if brief else ""))
                    elif brief or is_synth:
                        overview_items.append((label, brief))
                
                # Show overview if we have good content (at least 1 item)
                if len(overview_items) >= 1:
                    out_xml.write('        <div class="sense-overview">\n')
                    for ov_num, ov_brief in overview_items:
                        out_xml.write(f'          <span class="overview-item"><span class="sense-num">{html.escape(ov_num)}</span> {html.escape(ov_brief)}</span>\n')
                    out_xml.write('        </div>\n')

                definitions_html = ""
                for s, label, is_synth in render_items:
                    if is_synth:
                        # Inject a heading for an implicit leading division that has
                        # no wrapping <sense> element at all in the source (e.g. a
                        # preamble of principal parts precedes the first arabic
                        # sense). Fill it with that preamble text so the heading
                        # isn't left bare - it still describes what falls under it.
                        depth = sense_depth_from_n(label)
                        major_class = ' sense-major' if depth == 1 else ''
                        preamble_text = extract_preamble_text(entry, head_node, max_chars=200, for_overview=False)
                        body_html = f' <span class="sense-body">{html.escape(preamble_text)}</span>' if preamble_text else ''
                        definitions_html += f'<div class="sense sense-depth-{min(depth, 4)}{major_class}"><span class="sense-num">{html.escape(label)}</span>{body_html}</div>'
                        continue
                    if label is None:
                        continue  # bullet marker (•) - skip entirely
                    
                    # Determine sense depth from the resolved label
                    depth = sense_depth_from_n(label)
                    
                    # Render as regular sense
                    definitions_html += parse_sense_node(s, depth=depth, num_override=label)
                
                if not definitions_html:
                    fallback_text = "".join(entry.itertext()).strip()
                    fallback_text = clean_text_for_apple(fallback_text.replace(raw_lemma, "", 1))
                    definitions_html = f"<div>{html.escape(fallback_text)}</div>"
                    
                out_xml.write(f'{definitions_html}\n')
                out_xml.write('        </div>\n')

                if is_noun_adj and noun_grid:
                    out_xml.write('        <div class="morph-section">\n')
                    out_xml.write('            <p class="morph-label">Declension</p>\n')
                    out_xml.write('            <table class="morphology-table">\n')
                    out_xml.write('                <tr><th>Case</th><th>Singular</th><th>Dual</th><th>Plural</th></tr>\n')
                    for c in ['nominative', 'genitive', 'dative', 'accusative', 'vocative']:
                        sing = ", ".join(noun_grid[c].get('singular', ['\u2014']))
                        dual = ", ".join(noun_grid[c].get('dual', ['\u2014']))
                        plur = ", ".join(noun_grid[c].get('plural', ['\u2014']))
                        out_xml.write(f'                <tr><td class="case-label">{c.capitalize()}</td><td>{sing}</td><td>{dual}</td><td>{plur}</td></tr>\n')
                    out_xml.write('            </table>\n')
                    out_xml.write('        </div>\n')

                elif is_verb and verb_principal_parts:
                    primary_parts = {k: v for k, v in verb_principal_parts.items() if k in PRINCIPAL_PARTS_PRIMARY}
                    secondary_parts = {k: v for k, v in verb_principal_parts.items() if k not in PRINCIPAL_PARTS_PRIMARY}
                    out_xml.write('        <div class="morph-section">\n')
                    out_xml.write('            <p class="morph-label">Principal Parts</p>\n')
                    out_xml.write('            <table class="morphology-table">\n')
                    out_xml.write('                <tr><th>Tense &amp; Voice</th><th>Form (1. sg. ind.)</th></tr>\n')
                    for label in PRINCIPAL_PARTS_ORDER:
                        if label in primary_parts:
                            out_xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(primary_parts[label])}</td></tr>\n')
                    if secondary_parts:
                        out_xml.write('                <tr class="morph-secondary-header"><td colspan="2">Additional attested forms</td></tr>\n')
                        for label, forms in sorted(secondary_parts.items()):
                            out_xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(forms)}</td></tr>\n')
                    out_xml.write('            </table>\n')
                    out_xml.write('        </div>\n')

                out_xml.write('    </d:entry>\n\n')
                
            print(f"📖 Segment [{file_idx+1}/{len(xml_files)}]: {os.path.basename(xml_path)} -> Cumulative entries written: {entry_counter}")

        out_xml.write('</d:dictionary>\n')
        
    morph_conn.close()
    print(f"\n🎉 Success! Total of {entry_counter} unabridged entries written to {OUTPUT_XML_PATH}")

if __name__ == "__main__":
    build_unabridged_dictionary()