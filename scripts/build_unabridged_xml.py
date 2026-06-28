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

ROMAN_NUM_RE = re.compile(r'^[IVXivx]+\.?$')

def parse_sense_node(node, depth=0):
    """
    Recursively processes mixed-content TEI sense blocks, translating
    inline language tags to clean, stylized HTML presentation layers.
    """
    sense_html = ""
    num_marker = clean_text_for_apple(node.attrib.get('n', ''))
    
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
    
    indent = depth * 20
    is_major = bool(depth == 0 and num_marker and ROMAN_NUM_RE.match(num_marker.strip()))
    
    if num_marker or inline_content:
        depth_class = f'sense-depth-{min(depth, 4)}'
        major_class = ' sense-major' if is_major else ''
        sense_html += f'<div class="sense {depth_class}{major_class}" style="margin-left: {indent}px;">'
        if num_marker:
            sense_html += f'<span class="sense-num">{html.escape(num_marker)}</span> '
        if inline_content:
            sense_html += f'<span class="sense-body">{inline_content}</span>'
        sense_html += '</div>'
        
    for child in node:
        if child.tag.split('}')[-1] == 'sense':
            sense_html += parse_sense_node(child, depth + 1)
            
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
                morph_cursor.execute("SELECT form, form_normalized, pos, tense, voice, mood, person, number, case_name FROM morphology WHERE lemma = ?", (lookup_lemma,))
                morph_rows = morph_cursor.fetchall()
                
                is_verb, is_noun_adj = False, False
                noun_grid = defaultdict(lambda: defaultdict(set))
                verb_principal_parts = defaultdict(set)
                
                for mr in morph_rows:
                    f_form, f_norm, pos, tense, voice, mood, person, number, case_name = mr
                    if f_form: 
                        search_indices.add(clean_text_for_apple(f_form))
                        search_indices.add(strip_greek_vowel_lengths(clean_text_for_apple(f_form)))
                    if f_norm: 
                        search_indices.add(clean_text_for_apple(f_norm))
                        search_indices.add(strip_greek_vowel_lengths(clean_text_for_apple(f_norm)))
                    
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
                
                def is_top_level_sense(s_node):
                    curr = s_node
                    while curr in parent_map and curr != entry:
                        curr = parent_map[curr]
                        if curr != entry and curr.tag.split('}')[-1] == 'sense':
                            return False
                    return True

                definitions_html = ""
                for child in entry.iter():
                    if child.tag.split('}')[-1] == 'sense':
                        if is_top_level_sense(child):
                            definitions_html += parse_sense_node(child, depth=0)
                
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