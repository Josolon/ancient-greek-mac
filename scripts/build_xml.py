import sqlite3
import html
import os
import unicodedata
import json
from collections import defaultdict

# --- Paths ---
LSJ_DB_PATH = 'data/lsj.db'
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
    """Strips leading non-letters (like floating accents) so Apple DDK doesn't crash."""
    if not text: return ""
    kw = text.strip()
    kw = unicodedata.normalize('NFC', kw)
    while kw and not unicodedata.category(kw[0]).startswith(('L', 'N')):
        kw = kw[1:]
    return kw

def build_dictionary():
    print("🚀 Starting Apple Dictionary XML generation (UI Overhaul)...")
    
    if not os.path.exists(LSJ_DB_PATH) or not os.path.exists(MORPH_DB_PATH):
        print(f"❌ Error: Databases not found. Make sure {LSJ_DB_PATH} and {MORPH_DB_PATH} exist.")
        return

    lsj_conn = sqlite3.connect(LSJ_DB_PATH)
    morph_conn = sqlite3.connect(MORPH_DB_PATH)
    
    lsj_cursor = lsj_conn.cursor()
    morph_cursor = morph_conn.cursor()

    with open(OUTPUT_XML_PATH, 'w', encoding='utf-8') as xml:
        xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        xml.write('<d:dictionary xmlns="http://www.w3.org/1999/xhtml" xmlns:d="http://www.apple.com/DTDs/DictionaryService-1.0.rng">\n\n')

        print("📚 Fetching LSJ entries...")
        lsj_cursor.execute("SELECT id, lemma, lemma_normalized, definitions FROM definitions")
        entries = lsj_cursor.fetchall()
        
        total_entries = len(entries)
        print(f"🔍 Found {total_entries} entries. Building structures...")

        for index, row in enumerate(entries):
            entry_id = f"lsj_{row[0]}"
            raw_lemma = row[1]
            raw_lemma_norm = row[2]
            raw_def = row[3] 
            
            safe_title = sanitize_apple_key(raw_lemma)
            if not safe_title: safe_title = "unknown"

            xml.write(f'    <d:entry id="{entry_id}" d:title="{html.escape(safe_title)}">\n')
            search_indices = {raw_lemma, raw_lemma_norm}
            
            morph_cursor.execute("""
                SELECT form, form_normalized, pos, tense, voice, mood, person, number, case_name, gender 
                FROM morphology WHERE lemma = ?
            """, (raw_lemma,))
            morph_rows = morph_cursor.fetchall()

            # UI Data Structures
            is_verb = False
            is_noun_adj = False
            
            # [case][number] = set(forms)
            noun_grid = defaultdict(lambda: defaultdict(set))
            # [tense_voice] = set(forms)
            verb_principal_parts = defaultdict(set)
            # Fallback for weird POS
            generic_forms = defaultdict(list)

            for mr in morph_rows:
                raw_form = mr[0]
                raw_form_norm = mr[1]
                pos = mr[2]
                tense = mr[3]
                voice = mr[4]
                mood = mr[5]
                person = mr[6]
                number = mr[7]
                case_name = mr[8]
                
                # Add to invisible search index
                search_indices.add(raw_form)
                search_indices.add(raw_form_norm)
                
                display_form = html.escape(raw_form, quote=False)

                # Route data to the correct UI structure
                if pos == 'verb':
                    is_verb = True
                    # Only grab Principal Parts: 1st Person, Singular, Indicative
                    if person == '1st' and number == 'singular' and mood == 'indicative':
                        label = f"{str(tense).capitalize()} {str(voice).capitalize()}".strip()
                        verb_principal_parts[label].add(display_form)
                
                elif pos in ('noun', 'adjective', 'article', 'pronoun'):
                    is_noun_adj = True
                    if case_name and number:
                        noun_grid[case_name][number].add(display_form)
                
                else:
                    # Fallback for adverbs, particles, etc.
                    parsing_elements = [str(item) for item in mr[2:] if item]
                    parsing_str = " ".join(parsing_elements)
                    if parsing_str and parsing_str not in generic_forms[display_form]:
                        generic_forms[display_form].append(parsing_str)

            # Write sanitized indices
            valid_indices = set()
            for keyword in search_indices:
                clean_kw = sanitize_apple_key(keyword)
                if clean_kw: valid_indices.add(clean_kw)

            for keyword in valid_indices:
                xml.write(f'        <d:index d:value="{html.escape(keyword)}"/>\n')

            # --- CLEAN UP DEFINITIONS (Parse JSON Array) ---
            clean_definition = raw_def
            try:
                if raw_def.startswith('[') and raw_def.endswith(']'):
                    def_list = json.loads(raw_def)
                    # Join the array into a readable string
                    clean_definition = "; ".join([html.escape(d, quote=False) for d in def_list])
                else:
                    clean_definition = html.escape(raw_def, quote=False)
            except:
                clean_definition = html.escape(raw_def, quote=False)

            # --- MAIN ENTRY CONTENT ---
            xml.write(f'        <h1 class="entry-lemma">{html.escape(raw_lemma, quote=False)}</h1>\n')
            xml.write(f'        <div class="definition">\n')
            xml.write(f'            <p>{clean_definition}</p>\n')
            xml.write(f'        </div>\n')

            # --- DYNAMIC MORPHOLOGY PANE ---
            if is_noun_adj and noun_grid:
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Declension</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Case</th><th>Singular</th><th>Dual</th><th>Plural</th></tr>\n')

                for c in ['nominative', 'genitive', 'dative', 'accusative', 'vocative']:
                    if c in noun_grid:
                        sing = ", ".join(noun_grid[c].get('singular', ['\u2014']))
                        dual = ", ".join(noun_grid[c].get('dual', ['\u2014']))
                        plur = ", ".join(noun_grid[c].get('plural', ['\u2014']))
                        xml.write(f'                <tr><td class="case-label">{c.capitalize()}</td><td>{sing}</td><td>{dual}</td><td>{plur}</td></tr>\n')

                xml.write('            </table>\n')
                xml.write('        </div>\n')

            elif is_verb and verb_principal_parts:
                primary_parts = {k: v for k, v in verb_principal_parts.items() if k in PRINCIPAL_PARTS_PRIMARY}
                secondary_parts = {k: v for k, v in verb_principal_parts.items() if k not in PRINCIPAL_PARTS_PRIMARY}
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Principal Parts</p>\n')
                xml.write('            <table class="morphology-table">\n')
                xml.write('                <tr><th>Tense &amp; Voice</th><th>Form (1. sg. ind.)</th></tr>\n')

                for label in PRINCIPAL_PARTS_ORDER:
                    if label in primary_parts:
                        xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(primary_parts[label])}</td></tr>\n')
                if secondary_parts:
                    xml.write('                <tr class="morph-secondary-header"><td colspan="2">Additional attested forms</td></tr>\n')
                    for label, forms in sorted(secondary_parts.items()):
                        xml.write(f'                <tr><td class="case-label">{label}</td><td>{", ".join(forms)}</td></tr>\n')

                xml.write('            </table>\n')
                xml.write('        </div>\n')

            elif generic_forms:
                # Fallback for adverbs/particles
                xml.write('        <div class="morph-section">\n')
                xml.write('            <p class="morph-label">Forms</p>\n')
                xml.write('            <table class="morphology-table">\n')
                for m_form, m_parsings in generic_forms.items():
                    parsing_display = ", ".join(html.escape(p, quote=False) for p in m_parsings)
                    xml.write(f'                <tr><td class="case-label">{m_form}</td><td>{parsing_display}</td></tr>\n')
                xml.write('            </table>\n')
                xml.write('        </div>\n')

            xml.write('    </d:entry>\n\n')
            
            if (index + 1) % 5000 == 0:
                print(f"   ... Processed {index + 1} / {total_entries} entries")

        xml.write('</d:dictionary>\n')
        
    print(f"✅ Success! XML built at {OUTPUT_XML_PATH}")

    lsj_conn.close()
    morph_conn.close()

if __name__ == "__main__":
    build_dictionary()