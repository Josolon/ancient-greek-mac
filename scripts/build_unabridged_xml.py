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

# Classical six principal parts shown first, in traditional order.
# Anything not in this set (Imperfect, Pluperfect, Future Perfect, etc.) goes to secondary.
PRINCIPAL_PARTS_ORDER = [
    'Present Active', 'Present Middle', 'Present Passive',
    'Future Active',  'Future Middle',
    'Aorist Active',  'Aorist Middle',
    'Perfect Active',
    'Perfect Middle', 'Perfect Passive',
    'Aorist Passive',
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

ROMAN_NUM_RE = re.compile(r'^[IVXivx]+\.?$')
ARABIC_NUM_RE = re.compile(r'^\d+\.?$')
LOWER_LETTER_RE = re.compile(r'^[a-z]\.?$')

def sense_depth_from_n(n_val):
    """Infer visual indentation depth from the TEI sense n-attribute."""
    if not n_val:
        return 0   # No n-attribute — treat as top-level (often definition intro)
    n = n_val.strip().rstrip('.')
    if ROMAN_NUM_RE.match(n):
        return 0   # I, II, III … — top-level
    if ARABIC_NUM_RE.match(n_val.strip()):
        return 1   # 1, 2, 3 … — sub-sense
    if LOWER_LETTER_RE.match(n_val.strip()):
        return 2   # a, b, c … — sub-sub-sense
    return 3       # anything deeper

def brief_sense_text(node, max_chars=200):
    """Extract a meaningful snippet from a sense node for the overview.
    
    Includes sufficient context without becoming too verbose.
    """
    # Extract text content, stopping at citations but preserving definition
    text = node.text if node.text else ""
    text = clean_text_for_apple(text.strip())
    
    # Include more context but still stop before citations
    # Stop at: 'cf.', 'v.', '(with', 'also', 'but', when followed by heavy punctuation
    text = re.sub(r'\s+\(cf\..*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\s+v\.\s+.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'\s*(cf\.|v\.|etc\.)\s*.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Truncate to max length
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + '\u2026'
    
    return text

def parse_sense_node(node, depth=0, num_override=None, is_functional_header=False):
    """
    Recursively processes mixed-content TEI sense blocks, translating
    inline language tags to clean, stylized HTML presentation layers.
    
    Args:
        node: The TEI sense element
        depth: Visual indentation depth (0=top, 1=sub, 2=sub-sub, etc.)
        num_override: Custom number label to use instead of n-attribute
        is_functional_header: If True, render as a section header (e.g., "WITH GEN. prop...")
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
    
    # Render functional header if needed (e.g., "WITH GEN. prop.")
    if is_functional_header and inline_content:
        sense_html += f'<div class="case-governance-header"><strong>{inline_content}</strong></div>'
        return sense_html
    
    is_major = bool(depth == 0 and num_marker and ROMAN_NUM_RE.match(num_marker.strip()))
    
    if num_marker or inline_content:
        depth_class = f'sense-depth-{min(depth, 4)}'
        major_class = ' sense-major' if is_major else ''
        sense_html += f'<div class="sense {depth_class}{major_class}">'
        if num_marker:
            sense_html += f'<span class="sense-num">{html.escape(num_marker)}</span> '
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
                            label = f"{str(tense).capitalize()} {str(voice).capitalize()}".strip()
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
                out_xml.write('        <div class="definition">\n')
                
                all_senses = [c for c in entry.iter() if c.tag.split('}')[-1] == 'sense']

                # Find first unnumbered sense if any (for auto-labeling as "I")
                first_unnumbered_idx = None
                for idx, s in enumerate(all_senses):
                    n = clean_text_for_apple(s.attrib.get('n', ''))
                    if not n:
                        first_unnumbered_idx = idx
                        break

                # Helper function to detect functional headers (capital letters with keywords)
                def is_func_header_candidate(sense_text):
                    """Check if text looks like a functional/case-governance header."""
                    text = clean_text_for_apple(sense_text or '').strip().lower()
                    if len(text) < 8:  # Minimum meaningful length
                        return False
                    # Check for explicit case governance or relational keywords
                    keywords = ['with gen', 'with acc', 'introducing', 'denoting', 'forming',
                               'absol.', 'of place', 'in predicative', 'governing', 'c. gen',
                               'c. acc']
                    return any(text.startswith(kw.lower()) for kw in keywords)
                
                # Build overview from Roman numeral senses (always, regardless of functional headers)
                overview_items = []
                seen_roman_numerals = set()
                all_roman_numerals = []
                
                for idx, s in enumerate(all_senses):
                    num = clean_text_for_apple(s.attrib.get('n', ''))
                    # Include first unnumbered sense as "I" in overview
                    if idx == first_unnumbered_idx and not num:
                        num = 'I'
                    if num and ROMAN_NUM_RE.match(num.strip()):
                        all_roman_numerals.append(num)
                        # Only add the FIRST occurrence of each Roman numeral
                        if num not in seen_roman_numerals:
                            brief = brief_sense_text(s)
                            if brief:
                                overview_items.append((num, brief))
                                seen_roman_numerals.add(num)
                
                # Only show overview if we have good unique numerals (not many duplicates)
                has_many_duplicates = len(all_roman_numerals) > len(overview_items) * 1.5
                if len(overview_items) > 1 and not has_many_duplicates:
                    out_xml.write('        <div class="sense-overview">\n')
                    for ov_num, ov_brief in overview_items:
                        out_xml.write(f'          <span class="overview-item"><span class="sense-num">{html.escape(ov_num)}</span> {html.escape(ov_brief)}</span>\n')
                    out_xml.write('        </div>\n')

                definitions_html = ""
                for idx, s in enumerate(all_senses):
                    n_val = clean_text_for_apple(s.attrib.get('n', ''))
                    # Auto-label the first unnumbered sense as "I" for clarity
                    if idx == first_unnumbered_idx and not n_val:
                        n_val = 'I'
                    
                    # Check if this is a functional header (capital letter with grammatical text)
                    # Capital letters A, B, C indicate case-governance or functional groupings
                    is_header = (
                        LOWER_LETTER_RE.match(n_val.strip()) and
                        is_func_header_candidate(s.text)
                    )
                    
                    depth = sense_depth_from_n(n_val)
                    definitions_html += parse_sense_node(s, depth=depth, num_override=n_val, is_functional_header=is_header)
                
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