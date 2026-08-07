#!/usr/bin/env python3
"""Read a StarDict set back independently of the writer and report on it.

Parses .ifo/.idx/.syn/.dict from scratch so that a bug in build_stardict.py
cannot hide behind shared code. Checks sort order, offset integrity and
UTF-8 validity, and can dump an article or resolve a headword.

Usage:
    python3 scripts/verify_stardict.py dist/goldendict/AncientGreekLSJ
    python3 scripts/verify_stardict.py dist/goldendict/AncientGreekLSJ --lookup ἐποίησεν
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dictzip  # noqa: E402

_ASCII_LOWER = bytes.maketrans(bytes(range(0x41, 0x5B)), bytes(range(0x61, 0x7B)))


def read_ifo(path: Path) -> dict:
    lines = path.read_text(encoding='utf-8').splitlines()
    if lines[0] != "StarDict's dict ifo file":
        raise SystemExit(f'bad magic line: {lines[0]!r}')
    return dict(line.split('=', 1) for line in lines[1:] if '=' in line)


def read_idx(path: Path) -> list[tuple[bytes, int, int]]:
    blob = path.read_bytes()
    out, pos = [], 0
    while pos < len(blob):
        end = blob.index(b'\0', pos)
        word = blob[pos:end]
        offset, size = struct.unpack('>II', blob[end + 1:end + 9])
        out.append((word, offset, size))
        pos = end + 9
    return out


def read_syn(path: Path) -> list[tuple[bytes, int]]:
    if not path.exists():
        return []
    blob = path.read_bytes()
    out, pos = [], 0
    while pos < len(blob):
        end = blob.index(b'\0', pos)
        word = blob[pos:end]
        (target,) = struct.unpack('>I', blob[end + 1:end + 5])
        out.append((word, target))
        pos = end + 5
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('base', type=Path, help='path without extension')
    ap.add_argument('--lookup', help='headword or inflected form to resolve')
    ap.add_argument('--dump', type=int, help='print the Nth article')
    args = ap.parse_args()

    ifo = read_ifo(args.base.with_suffix('.ifo'))
    idx_path = args.base.with_suffix('.idx')
    idx = read_idx(idx_path)
    syn = read_syn(args.base.with_suffix('.syn'))
    dict_path = args.base.with_suffix('.dict')
    dz_path = dict_path.with_name(dict_path.name + '.dz')

    problems = []
    reader = None
    if dz_path.exists():
        reader = dictzip.DictzipReader(dz_path)
        data = reader.read(0, reader.size)
        compression = f'{dz_path.stat().st_size / reader.size:.0%} of raw'
    elif dict_path.exists():
        data = dict_path.read_bytes()
        compression = 'uncompressed'
    else:
        raise SystemExit(f'neither {dict_path} nor {dz_path} exists')

    if int(ifo['wordcount']) != len(idx):
        problems.append(f"wordcount={ifo['wordcount']} but .idx holds {len(idx)}")
    if int(ifo.get('synwordcount', 0)) != len(syn):
        problems.append(f"synwordcount={ifo.get('synwordcount')} but .syn holds {len(syn)}")
    if int(ifo['idxfilesize']) != idx_path.stat().st_size:
        problems.append('idxfilesize does not match the actual .idx size')

    # Sort order: StarDict binary-searches, so a single inversion breaks lookup.
    def key(w: bytes) -> tuple[bytes, bytes]:
        return (w.translate(_ASCII_LOWER), w)

    for i in range(1, len(idx)):
        if key(idx[i - 1][0]) > key(idx[i][0]):
            problems.append(f'.idx not sorted at {i}: {idx[i-1][0]!r} > {idx[i][0]!r}')
            break
    for i in range(1, len(syn)):
        if key(syn[i - 1][0]) > key(syn[i][0]):
            problems.append(f'.syn not sorted at {i}: {syn[i-1][0]!r} > {syn[i][0]!r}')
            break

    # Every offset/size pair must land inside the .dict and decode as UTF-8.
    covered = 0
    for word, offset, size in idx:
        if offset + size > len(data):
            problems.append(f'{word!r} points past end of .dict')
            break
        covered += size
    else:
        try:
            for word, offset, size in idx:
                data[offset:offset + size].decode('utf-8')
        except UnicodeDecodeError as exc:
            problems.append(f'article for {word!r} is not valid UTF-8: {exc}')

    for word, target in syn:
        if target >= len(idx):
            problems.append(f'synonym {word!r} points at index {target} (out of range)')
            break

    # Random access is the whole point of dictzip, so check that seeking to an
    # article gives the same bytes as reading the file straight through.
    if reader is not None:
        step = max(1, len(idx) // 50)
        for i in range(0, len(idx), step):
            word, offset, size = idx[i]
            if reader.read(offset, size) != data[offset:offset + size]:
                problems.append(f'dictzip random access disagrees for {word!r}')
                break
        reader.close()

    print(f"bookname : {ifo.get('bookname')}")
    print(f'entries  : {len(idx):,}')
    print(f'synonyms : {len(syn):,}')
    print(f'dict     : {len(data):,} bytes ({covered:,} covered by the index), {compression}')

    if args.dump is not None:
        word, offset, size = idx[args.dump]
        print(f'\n--- article {args.dump}: {word.decode()} ---')
        print(data[offset:offset + size].decode('utf-8')[:2000])

    if args.lookup:
        needle = args.lookup.encode('utf-8')
        hits = [i for i, (w, _, _) in enumerate(idx) if w == needle]
        via_syn = [t for w, t in syn if w == needle]
        print(f'\nlookup {args.lookup!r}: {len(hits)} headword hit(s), '
              f'{len(via_syn)} via synonyms')
        for target in dict.fromkeys(hits + via_syn):
            word, offset, size = idx[target]
            print(f'  -> {word.decode()}')

    if problems:
        print('\nPROBLEMS:', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        return 1
    print('\nAll structural checks passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
