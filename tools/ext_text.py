#!/usr/bin/env python3
"""Dump the game's text for one or all languages.

    python tools/ext_text.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT
    python tools/ext_text.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT --section 4

Text lives in slot 0x3F of each area section and in slots 0x40/0x41 of
section 57. A text resource holds, among other tables, a string table:

    u32 ?  u32 count  u32 pool_size  u32 1
    count x { u32 offset, u32 offset, u32 length, u32 length + 1 }
    pool_size bytes of NUL-terminated strings, '\\n' for line breaks

The string table is found by that shape rather than by a fixed offset: the
tables before it (per-line records and short command records, such as
{3, 0, n, -1}) are not decoded yet. Empty strings separate groups of lines.

Text is Windows-1252 (the French use 0x9C for oe). Shift-JIS pairs with lead
0x81 supply a few symbols (0x8163 ellipsis, 0x815E slash, 0x8183/0x8184 angle
brackets): the font engine is Japanese. 0x80, 0x8D, 0x8E, 0x8F and 0x90 are
glyphs of the game's own font, printed as {XX}: pad buttons and card-key
symbols, by context. English has no subtitles, so its dialogue strings are
empty: only names, signs and messages remain.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ext_index                                            # noqa: E402

TEXT_SLOTS = {0x3F, 0x40, 0x41}
GLYPHS = {0x80, 0x8D, 0x8E, 0x8F, 0x90}


def find_string_tables(d):
    """Yield (records_offset, pool_offset, count) for every string table."""
    for o in range(0, len(d) - 32, 16):
        _, count, pool_size, one = struct.unpack_from("<4I", d, o)
        if one != 1 or not 0 < count < 4096:
            continue
        rec = o + 16
        pool = rec + 16 * count
        if pool + pool_size > len(d):
            continue
        ok = True
        for i in range(count):
            a, b, n, m = struct.unpack_from("<4I", d, rec + 16 * i)
            if a != b or m != n + 1 or a + m > pool_size:
                ok = False
                break
        if ok and struct.unpack_from("<I", d, rec)[0] == 0:
            yield rec, pool, count


def decode(raw):
    """cp1252 with Shift-JIS symbol pairs; font glyph bytes as {XX}.

    A string holding kana (a 0x82/0x83 lead) is Japanese throughout and is
    decoded as cp932 whole: a few untranslated lines survive that way.
    """
    i = 0
    while i < len(raw) - 1:
        if raw[i] == 0x81:                  # symbol pair: skip its trail byte
            i += 2
            continue
        if raw[i] in (0x82, 0x83) and 0x40 <= raw[i + 1] <= 0xFC:
            try:
                return raw.decode("cp932")
            except UnicodeDecodeError:
                break
        i += 1
    out, i = [], 0
    while i < len(raw):
        c = raw[i]
        if c == 0x81 and i + 1 < len(raw):
            out.append(raw[i:i + 2].decode("cp932", "replace"))
            i += 2
            continue
        if c in GLYPHS:
            out.append("{%02X}" % c)
        else:
            out.append(bytes([c]).decode("cp1252", "replace"))
        i += 1
    return "".join(out)


def strings(d):
    out = []
    for rec, pool, count in find_string_tables(d):
        for i in range(count):
            off, _, n, _ = struct.unpack_from("<4I", d, rec + 16 * i)
            out.append(decode(d[pool + off:pool + off + n]))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--section", type=int)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    with open(a.dat, "rb") as f:
        for r in ext_index.load(a.idx):
            if a.section is not None and r.section != a.section:
                continue
            for label, off, size in r.items():
                if not label.startswith("slot") or int(label[4:], 16) not in TEXT_SLOTS:
                    continue
                f.seek(off)
                lines = strings(f.read(size))
                print("== %s %s: %d strings" % (r.name, label, len(lines)))
                for i, s in enumerate(lines):
                    if s:
                        print("%4d  %s" % (i, s.replace("\n", " / ")))


if __name__ == "__main__":
    main()
