#!/usr/bin/env python3
"""Convert the Apple Dictionary source XML into StarDict format.

This is the Linux/Windows delivery path. GoldenDict-ng reads StarDict on all
three desktop platforms, and its Scan Popup gives the same select-a-word-and-
look-it-up experience as macOS's built-in Look Up.

The Apple XML is already almost portable: entry bodies are plain XHTML and the
headword/inflection lists are a flat run of <d:index> elements. Only two things
are genuinely Apple-specific and get rewritten here:

  * ``x-dictionary:d:TERM:BUNDLE_ID`` cross-dictionary links become ``bword:TERM``.
    GoldenDict searches every enabled dictionary, so the bundle id is dropped.
  * The stylesheet, which StarDict has no slot for, ships separately as
    ``article-style.css`` (hand-maintained in src/GoldenDictArticle.css).

Diacritic folding is deliberately NOT done here. GoldenDict normalises accents
and case at search time, so emitting folded duplicates of 4.5M inflected forms
would double the index for nothing.

Usage:
    python3 scripts/build_stardict.py src/GreekDictionary.xml \
        --out dist/goldendict --name AncientGreekLSJ \
        --bookname "Ancient Greek (LSJ)"
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dictzip  # noqa: E402

D_NS = 'http://www.apple.com/DTDs/DictionaryService-1.0.rng'
XHTML_NS = 'http://www.w3.org/1999/xhtml'

D_ENTRY = f'{{{D_NS}}}entry'
D_INDEX = f'{{{D_NS}}}index'
D_TITLE = f'{{{D_NS}}}title'
D_VALUE = f'{{{D_NS}}}value'

# StarDict orders its index with g_ascii_strcasecmp, which lowercases ASCII
# A-Z only and leaves every other byte alone - so Greek sorts by raw UTF-8.
_ASCII_LOWER = bytes.maketrans(bytes(range(0x41, 0x5B)), bytes(range(0x61, 0x7B)))

# x-dictionary:d:S.%20338:com.jonatansolon.dictionary.GreekGrammarReference
# The term is percent-encoded, so a bare ':' can only be a delimiter.
_XDICT_LINK = re.compile(r'x-dictionary:d:([^:"\']*):[^"\']*')


def _fold(word: bytes) -> bytes:
    """StarDict's primary sort key. Returns the original object when unchanged
    so the common (non-ASCII) case does not pay for a second copy."""
    lowered = word.translate(_ASCII_LOWER)
    return word if lowered == word else lowered


def _strip_namespaces(el: ET.Element) -> None:
    for node in el.iter():
        if isinstance(node.tag, str) and node.tag.startswith('{'):
            node.tag = node.tag.rsplit('}', 1)[1]
        for key in [k for k in node.attrib if k.startswith('{')]:
            node.attrib[key.rsplit('}', 1)[1]] = node.attrib.pop(key)


def iter_entries(xml_path: Path, limit: int | None = None):
    """Yield (title, [index values], body_html) for each <d:entry>.

    Streams the document - GreekDictionary.xml is ~450 MB - and clears each
    entry as soon as it has been serialised.
    """
    context = ET.iterparse(str(xml_path), events=('end',))
    count = 0
    for event, el in context:
        if el.tag != D_ENTRY:
            continue

        title = el.get(D_TITLE) or ''
        indices = []
        parts = []
        for child in el:
            if child.tag == D_INDEX:
                value = child.get(D_VALUE)
                if value:
                    indices.append(value)
                continue
            _strip_namespaces(child)
            parts.append(ET.tostring(child, encoding='unicode', method='html'))

        body = ''.join(parts).strip()
        body = _XDICT_LINK.sub(r'bword:\1', body)
        # A wrapper gives article-style.css something to scope to, so the two
        # dictionaries can be styled independently inside one GoldenDict config.
        yield title, indices, f'<div class="agk-article">{body}</div>'

        el.clear()
        count += 1
        if limit and count >= limit:
            break


def write_stardict(xml_path: Path, out_dir: Path, name: str, bookname: str,
                   description: str, author: str, website: str,
                   limit: int | None = None, use_dictzip: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dict_path = out_dir / f'{name}.dict'

    entries: list[tuple[bytes, int, int]] = []      # (title, offset, size)
    synonyms: list[tuple[bytes, bytes, int]] = []   # (foldkey, word, ordinal)

    with open(dict_path, 'wb') as dictf:
        for ordinal, (title, indices, body) in enumerate(iter_entries(xml_path, limit)):
            payload = body.encode('utf-8')
            offset = dictf.tell()
            dictf.write(payload)
            entries.append((title.encode('utf-8'), offset, len(payload)))

            seen = {title}
            for value in indices:
                if value in seen:
                    continue
                seen.add(value)
                word = value.encode('utf-8')
                synonyms.append((_fold(word), word, ordinal))

            if ordinal and ordinal % 20000 == 0:
                print(f'  ... {ordinal:,} entries', file=sys.stderr)

    # StarDict binary-searches the index, so it must be sorted; .syn then points
    # at positions in that sorted order, not at our original entry ordinals.
    order = sorted(range(len(entries)),
                   key=lambda i: (_fold(entries[i][0]), entries[i][0]))
    position_of = [0] * len(entries)
    for position, original in enumerate(order):
        position_of[original] = position

    idx_path = out_dir / f'{name}.idx'
    with open(idx_path, 'wb') as idxf:
        for original in order:
            word, offset, size = entries[original]
            idxf.write(word + b'\0' + struct.pack('>II', offset, size))
    idx_size = idx_path.stat().st_size

    synonyms.sort(key=lambda t: (t[0], t[1]))
    syn_path = out_dir / f'{name}.syn'
    with open(syn_path, 'wb') as synf:
        for _fold_key, word, ordinal in synonyms:
            synf.write(word + b'\0' + struct.pack('>I', position_of[ordinal]))

    dict_size = dict_path.stat().st_size
    compressed_size = None
    if use_dictzip:
        # compress_file verifies the round trip before it deletes the original.
        dz_path = dictzip.compress_file(dict_path)
        compressed_size = dz_path.stat().st_size

    ifo_lines = [
        "StarDict's dict ifo file",
        'version=3.0.0',
        f'bookname={bookname}',
        f'wordcount={len(entries)}',
        f'synwordcount={len(synonyms)}',
        f'idxfilesize={idx_size}',
        'sametypesequence=h',
        f'author={author}',
        f'description={description}',
        f'website={website}',
    ]
    (out_dir / f'{name}.ifo').write_text('\n'.join(ifo_lines) + '\n', encoding='utf-8')

    return {
        'name': name,
        'entries': len(entries),
        'synonyms': len(synonyms),
        'dict_bytes': dict_size,
        'idx_bytes': idx_size,
        'dz_bytes': compressed_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('xml', type=Path, help='Apple Dictionary source XML')
    parser.add_argument('--out', type=Path, default=Path('dist/goldendict'))
    parser.add_argument('--name', required=True, help='Base filename for the .ifo/.idx/.dict/.syn set')
    parser.add_argument('--bookname', required=True, help='Title shown in GoldenDict')
    parser.add_argument('--description', default='')
    parser.add_argument('--author', default='Jónatan Sólon')
    parser.add_argument('--website', default='https://github.com/Josolon/ancient-greek-dictionary')
    parser.add_argument('--limit', type=int, default=None,
                        help='Only convert the first N entries (for smoke tests)')
    parser.add_argument('--no-dictzip', action='store_true')
    args = parser.parse_args()

    if not args.xml.exists():
        print(f'error: {args.xml} not found - run the XML builder first', file=sys.stderr)
        return 1

    print(f'Converting {args.xml} -> {args.out}/{args.name}.*', file=sys.stderr)
    stats = write_stardict(
        args.xml, args.out, args.name, args.bookname,
        args.description, args.author, args.website,
        limit=args.limit, use_dictzip=not args.no_dictzip,
    )
    line = (f"  {stats['entries']:,} entries, {stats['synonyms']:,} synonyms, "
            f"dict {stats['dict_bytes'] / 1e6:.1f} MB")
    if stats['dz_bytes']:
        ratio = stats['dz_bytes'] / stats['dict_bytes']
        line += f" -> {stats['dz_bytes'] / 1e6:.1f} MB dictzipped ({ratio:.0%})"
    print(line, file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
