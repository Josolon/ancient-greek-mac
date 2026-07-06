"""Fetches the Smyth and Goodwin grammar reference sources used by
build_grammar_reference.py. Both are public domain / freely-redistributable
Perseus Digital Library texts (see README's Data Sources section); this just
vendors them locally into data/, matching how data/lsj_unicode/ is fetched
separately rather than committed (see .gitignore).
"""
import json
import os
import urllib.request

SMYTH_HTML_DIR = 'data/smyth_html/'
GOODWIN_XML_PATH = 'data/goodwin.xml'

SG_READER_API = 'https://api.github.com/repos/PerseusDL/sg_reader/contents/data'
GOODWIN_URL = 'https://www.perseus.tufts.edu/hopper/dltext?doc=Perseus%3Atext%3A1999.04.0065'


def fetch_smyth():
    os.makedirs(SMYTH_HTML_DIR, exist_ok=True)
    with urllib.request.urlopen(SG_READER_API) as resp:
        listing = json.loads(resp.read())
    html_files = [item for item in listing if item['name'].endswith('.html')]
    print(f"📚 Fetching {len(html_files)} Smyth chapter files from PerseusDL/sg_reader...")
    for item in html_files:
        dest = os.path.join(SMYTH_HTML_DIR, item['name'])
        with urllib.request.urlopen(item['download_url']) as resp:
            content = resp.read()
        with open(dest, 'wb') as f:
            f.write(content)
    print(f"✅ Wrote {len(html_files)} files to {SMYTH_HTML_DIR}")


def fetch_goodwin():
    print("📖 Fetching Goodwin's Syntax of the Moods and Tenses from Perseus...")
    with urllib.request.urlopen(GOODWIN_URL) as resp:
        content = resp.read()
    with open(GOODWIN_XML_PATH, 'wb') as f:
        f.write(content)
    print(f"✅ Wrote {GOODWIN_XML_PATH} ({len(content)} bytes)")


if __name__ == '__main__':
    fetch_smyth()
    fetch_goodwin()
