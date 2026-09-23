#!/usr/bin/env python3
"""List and extract the streamed music and voice tracks.

    python tools/ext_stream.py E:/SCES_502.40 --list
    python tools/ext_stream.py E:/SCES_502.40 --stream E:/STREAM/MUSIC.DAT \\
        --kind music --extract out/music/ [--track 3]

STREAM/MUSIC.DAT and STREAM/VOICE.DAT carry no header and no end flags: every
SPU-ADPCM frame has flag byte 0x02, so the tracks cannot be found from the
data alone. Their bounds are two tables in the executable, 16 bytes a track,
read by the stream code at 0x1FB120 after it has stored each file's LSN
(0x284D08 music, 0x284D0C voice):

    +00 u32 start sector (relative to the file)
    +04 u32 start byte   (= start sector * 2048)
    +08 u32 size, bytes
    +0C u32 loop flag    (music only; 1 = loops)

Entry 0 is empty. Both tables tile their file exactly. The stream code
converts a music size to time at 0.0746667 s per sector, 48 000 samples/s.
The decoded data shows no interleave boundaries, so that is mono 48 kHz, and
the voice clips keep a faint 15.6 kHz line-scan whistle that only lands there
at 48 kHz.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ps2kit import adpcm                                     # noqa: E402
from ps2kit.elf import Elf                                   # noqa: E402

SECTOR = 2048
RATE = 48000
# PAL SCES-50240
TABLES = {"music": 0x25E8B0, "voice": 0x25ECE0}


def read_table(elf, va):
    """Entries from 1 while they chain sector to sector."""
    tracks = []
    expect = 0
    n = 1
    while True:
        lsn, byte, size, loop = struct.unpack_from("<4I", elf.read(va + 16 * n, 16))
        if lsn != expect or byte != lsn * SECTOR or size == 0 or size % SECTOR:
            break
        tracks.append(dict(n=n, lsn=lsn, size=size, loop=loop))
        expect = lsn + size // SECTOR
        n += 1
    return tracks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--kind", choices=TABLES, default="music")
    ap.add_argument("--stream", help="MUSIC.DAT or VOICE.DAT, to check or extract")
    ap.add_argument("--extract", metavar="DIR")
    ap.add_argument("--track", type=int)
    a = ap.parse_args()
    elf = Elf(a.elf)
    kinds = [a.kind] if (a.stream or a.extract) else list(TABLES)

    for kind in kinds:
        tracks = read_table(elf, TABLES[kind])
        total = sum(t["size"] for t in tracks)
        if a.list:
            print("%s: %d tracks, %d bytes, %.1f min" % (
                kind, len(tracks), total, total / 16 * 28 / RATE / 60))
            for t in tracks:
                print("  %3d  sector %6d  %8X bytes  %6.1f s%s" % (
                    t["n"], t["lsn"], t["size"], t["size"] / 16 * 28 / RATE,
                    "  loop" if t["loop"] else ""))
        if a.stream:
            size = os.path.getsize(a.stream)
            if size != total:
                print("warning: table covers %d bytes, %s is %d" % (total, a.stream, size))
        if a.extract:
            os.makedirs(a.extract, exist_ok=True)
            with open(a.stream, "rb") as f:
                for t in tracks:
                    if a.track is not None and t["n"] != a.track:
                        continue
                    f.seek(t["lsn"] * SECTOR)
                    pcm = adpcm.decode(f.read(t["size"]))
                    out = os.path.join(a.extract, "%s_%02d.wav" % (kind, t["n"]))
                    adpcm.write_wav(out, [pcm], RATE)
                    print(out)


if __name__ == "__main__":
    main()
