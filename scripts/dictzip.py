#!/usr/bin/env python3
"""dictzip: a gzip file that also supports random access.

StarDict's .dict can be shipped compressed as .dict.dz. The format is an
ordinary gzip stream with one addition: an "RA" subfield in the gzip FEXTRA
header listing the compressed size of every fixed-size chunk of the original.
A reader wanting bytes at offset N seeks straight to the chunk containing them
instead of inflating everything before it.

Implemented here in pure Python rather than shelling out to the `dictzip`
binary, which is not separately packaged on macOS (it ships inside dictd). That
keeps the build reproducible on any machine with a Python interpreter, and it
is self-validating: the output must decompress byte-identically under any
stock gzip, *and* every chunk must inflate on its own, which is the property
GoldenDict actually depends on.

Layout of the RA subfield (all little-endian, per the dictzip format):

    SI1 SI2   'R' 'A'
    LEN       u16   6 + 2 * chunk_count
    VER       u16   1
    CHLEN     u16   uncompressed bytes per chunk
    CHCNT     u16   number of chunks
    SIZES     u16 * CHCNT   compressed size of each chunk

Each chunk is deflated into one continuous stream with a Z_FULL_FLUSH at every
boundary. The flush resets the compressor's back-reference window, which is
what makes a chunk independently inflatable while keeping the concatenation a
single valid deflate stream.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

# dictzip's own default. Chosen so that a chunk's *compressed* size reliably
# fits the u16 size field even for poorly-compressible input.
DEFAULT_CHUNK_SIZE = 58315

_MAX_CHUNK_SIZES = 0xFFFF          # a chunk's compressed size is a u16
# XLEN is a u16 covering the whole extra field, which is the 4-byte subfield
# header plus LEN bytes, so the chunk table cannot grow past this.
_MAX_CHUNKS = (0xFFFF - 4 - 6) // 2

_GZIP_MAGIC = b'\x1f\x8b'
_FEXTRA = 0x04
_FNAME = 0x08


class DictzipError(RuntimeError):
    pass


def compress(data: bytes, filename: str | None = None,
             chunk_size: int = DEFAULT_CHUNK_SIZE, level: int = 9,
             mtime: int = 0) -> bytes:
    """Return `data` as a dictzip (.dz) stream."""
    if chunk_size <= 0 or chunk_size > 0xFFFF:
        raise DictzipError(f'chunk_size must be 1..65535, got {chunk_size}')

    chunks = [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b'']
    if len(chunks) > _MAX_CHUNKS:
        raise DictzipError(
            f'{len(chunks)} chunks exceeds the {_MAX_CHUNKS} the header can '
            f'address; use a larger chunk_size')

    compressor = zlib.compressobj(level, zlib.DEFLATED, -zlib.MAX_WBITS)
    bodies, sizes = [], []
    for chunk in chunks:
        # FULL_FLUSH ends the chunk on a byte boundary and clears the window,
        # so this chunk's bytes inflate without any earlier chunk.
        piece = compressor.compress(chunk) + compressor.flush(zlib.Z_FULL_FLUSH)
        if len(piece) > _MAX_CHUNK_SIZES:
            raise DictzipError(
                f'a chunk compressed to {len(piece)} bytes, past the u16 size '
                f'field; use a smaller chunk_size')
        bodies.append(piece)
        sizes.append(len(piece))
    tail = compressor.flush(zlib.Z_FINISH)

    subfield = struct.pack('<HHH', 1, chunk_size, len(chunks))
    subfield += struct.pack(f'<{len(sizes)}H', *sizes)
    extra = b'RA' + struct.pack('<H', len(subfield)) + subfield

    flags = _FEXTRA
    name_bytes = b''
    if filename:
        flags |= _FNAME
        name_bytes = filename.encode('latin-1', 'replace') + b'\0'

    header = _GZIP_MAGIC + struct.pack('<BBIBB', 8, flags, mtime, 2, 3)
    header += struct.pack('<H', len(extra)) + extra + name_bytes

    trailer = struct.pack('<II', zlib.crc32(data) & 0xFFFFFFFF, len(data) & 0xFFFFFFFF)
    return header + b''.join(bodies) + tail + trailer


def compress_file(path: Path, remove_original: bool = True,
                  chunk_size: int = DEFAULT_CHUNK_SIZE) -> Path:
    """Compress `path` to `path` + '.dz'. Verifies the round trip before
    removing the original."""
    data = path.read_bytes()
    out_path = path.with_name(path.name + '.dz')
    blob = compress(data, filename=path.name, chunk_size=chunk_size)
    out_path.write_bytes(blob)

    reader = DictzipReader(out_path)
    try:
        if reader.size != len(data):
            raise DictzipError('round trip changed the length')
        # Spot-check random access rather than the whole file: read the first,
        # last and a middle chunk back through the index.
        probes = [0, max(0, len(data) // 2 - 7), max(0, len(data) - 1000)]
        for offset in probes:
            want = data[offset:offset + 1000]
            if reader.read(offset, len(want)) != want:
                raise DictzipError(f'random access mismatch at offset {offset}')
    finally:
        reader.close()

    if remove_original:
        path.unlink()
    return out_path


class DictzipReader:
    """Random-access reader for a .dz file. Also accepts a plain file and
    falls back to ordinary seeking, so callers need not care which they got."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = open(self.path, 'rb')
        self.chunk_size = 0
        self.offsets: list[int] = []
        self.sizes: list[int] = []
        self.size = 0
        self.is_dictzip = False
        self._parse_header()

    def _parse_header(self) -> None:
        fh = self._fh
        head = fh.read(2)
        if head != _GZIP_MAGIC:
            # Plain, uncompressed .dict.
            fh.seek(0, 2)
            self.size = fh.tell()
            return

        cm, flags, _mtime, _xfl, _os = struct.unpack('<BBIBB', fh.read(8))
        if cm != 8:
            raise DictzipError(f'unsupported compression method {cm}')
        if not flags & _FEXTRA:
            raise DictzipError('gzip file has no extra field, so it is not dictzip')

        (xlen,) = struct.unpack('<H', fh.read(2))
        extra = fh.read(xlen)

        pos = 0
        table = None
        while pos + 4 <= len(extra):
            si1, si2, length = struct.unpack('<ccH', extra[pos:pos + 4])
            payload = extra[pos + 4:pos + 4 + length]
            if si1 + si2 == b'RA':
                table = payload
                break
            pos += 4 + length
        if table is None:
            raise DictzipError("gzip extra field has no 'RA' subfield")

        version, chunk_size, count = struct.unpack('<HHH', table[:6])
        if version != 1:
            raise DictzipError(f'unsupported dictzip version {version}')
        self.chunk_size = chunk_size
        self.sizes = list(struct.unpack(f'<{count}H', table[6:6 + 2 * count]))

        if flags & _FNAME:
            while fh.read(1) not in (b'\0', b''):
                pass

        data_start = fh.tell()
        running = data_start
        for size in self.sizes:
            self.offsets.append(running)
            running += size

        fh.seek(-4, 2)
        (self.size,) = struct.unpack('<I', fh.read(4))
        self.is_dictzip = True

    def read(self, offset: int, length: int) -> bytes:
        """Return `length` bytes starting at `offset` in the *uncompressed*
        data, inflating only the chunks that overlap the range."""
        if not self.is_dictzip:
            self._fh.seek(offset)
            return self._fh.read(length)
        if length <= 0:
            return b''

        first = offset // self.chunk_size
        last = (offset + length - 1) // self.chunk_size
        out = bytearray()
        for index in range(first, min(last + 1, len(self.sizes))):
            self._fh.seek(self.offsets[index])
            raw = self._fh.read(self.sizes[index])
            out += zlib.decompressobj(-zlib.MAX_WBITS).decompress(raw)
        start = offset - first * self.chunk_size
        return bytes(out[start:start + length])

    def close(self) -> None:
        self._fh.close()

    def __enter__(self) -> 'DictzipReader':
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _self_test() -> int:
    """Round-trip the format against Python's own gzip, and confirm every
    chunk inflates independently - the property random access relies on."""
    import gzip
    import io
    import os

    failures = 0
    cases = {
        'empty': b'',
        'tiny': b'hello',
        'exact chunk': b'x' * DEFAULT_CHUNK_SIZE,
        'chunk + 1': b'y' * (DEFAULT_CHUNK_SIZE + 1),
        'greek html': ('<div class="agk-article">ἥλῐος, ὁ, Ep. ἠέλιος</div>'
                       * 40000).encode('utf-8'),
        'incompressible': os.urandom(200_000),
    }

    for name, data in cases.items():
        blob = compress(data, filename='test.dict')

        # 1. Any stock gzip must read it.
        via_gzip = gzip.GzipFile(fileobj=io.BytesIO(blob)).read()
        if via_gzip != data:
            print(f'  FAIL {name}: gzip round trip differs')
            failures += 1
            continue

        # 2. Random access must agree with the original at arbitrary offsets.
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.dz', delete=False) as tmp:
            tmp.write(blob)
            tmp_path = Path(tmp.name)
        try:
            with DictzipReader(tmp_path) as reader:
                if reader.size != len(data):
                    print(f'  FAIL {name}: size {reader.size} != {len(data)}')
                    failures += 1
                    continue
                bad = 0
                step = max(1, len(data) // 17) if data else 1
                for offset in range(0, len(data), step):
                    for length in (1, 300, DEFAULT_CHUNK_SIZE + 5):
                        want = data[offset:offset + length]
                        if reader.read(offset, len(want)) != want:
                            bad += 1
                if bad:
                    print(f'  FAIL {name}: {bad} random-access mismatches')
                    failures += 1
                    continue
        finally:
            tmp_path.unlink()

        ratio = f'{len(blob) / len(data):.1%}' if data else 'n/a'
        print(f'  ok   {name}: {len(data):,} -> {len(blob):,} ({ratio})')

    return failures


if __name__ == '__main__':
    print('dictzip self-test')
    raise SystemExit(1 if _self_test() else 0)
