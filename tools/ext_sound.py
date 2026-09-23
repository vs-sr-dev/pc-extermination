#!/usr/bin/env python3
"""Split Extermination's sound banks into their SPU-ADPCM samples.

    python tools/ext_sound.py IDX DAT --list
    python tools/ext_sound.py IDX DAT --record s04_r0 --wav out/ [--rate 22050]

A sound bank is the first pack of a record (the loader hands it to the IOP
driver sndn2_driver through 0x001FBD00). Observed on every bank:

    +00 u32 total = hd size + bd size        +04 u32 0x20 + 16 n, offset of the hd
    +08 u32 0                                +0C u32 n, sub-banks
    +10 u32 hd size   +14 u32 bd size   +18 u32 hd size (bd offset from the hd)
    +20 n x { u32 bd size, u32 offset of the sub-bank's header (from the
              bank start), u32 kind (2 or 4), u32 0 }
    then the hd: n sub-bank headers, then the bd: n sample blocks, in order

A sub-bank header is `u32 size, u32 bd size, u32 0` and an "SShd" block:
128-entry maps, short MIDI-like sequences for the sound effects (`a0 nn 64
... ff 2f 00`), then 16-byte tones whose u16 at +2 is a sample's offset in
the sub-bank's bd / 8. Samples are plain SPU-ADPCM, each ended by a frame
with the end flag; this tool splits the bd at those flags.

The sample rate is not stored: the SPU plays a tone at 48 kHz * 2^((note -
centre) / 12), and the notes come from the sequences. --rate picks one.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ps2kit import adpcm  # noqa: E402
import ext_index  # noqa: E402


class Bank:
    def __init__(self, buf):
        self.total, hd_off, _, n = struct.unpack_from("<4I", buf, 0)
        self.hd_size, self.bd_size, _ = struct.unpack_from("<3I", buf, 0x10)
        if self.total != self.hd_size + self.bd_size or hd_off != 0x20 + 16 * n:
            raise ValueError("not a sound bank")
        self.subs = []            # (kind, header bytes, bd bytes)
        bd = hd_off + self.hd_size
        for k in range(n):
            size, off, kind, _ = struct.unpack_from("<4I", buf, 0x20 + 16 * k)
            hsize, bsize, _ = struct.unpack_from("<3I", buf, off)
            if bsize != size:
                raise ValueError("sub-bank %d: sizes disagree" % k)
            self.subs.append((kind, buf[off + 12:off + 12 + hsize], buf[bd:bd + size]))
            bd += size
        if bd != hd_off + self.total:
            raise ValueError("sample blocks do not add up")


def samples(bd):
    """(offset, bytes) of each sample: runs of frames up to an end flag."""
    out, start = [], 0
    for i in range(0, len(bd) - 15, 16):
        if bd[i + 1] & 1:
            if any(bd[start:i + 16]):
                out.append((start, bd[start:i + 16]))
            start = i + 16
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--record")
    ap.add_argument("--wav", metavar="DIR")
    ap.add_argument("--rate", type=int, default=22050)
    a = ap.parse_args()
    records = ext_index.load(a.idx)
    with open(a.dat, "rb") as f:
        for r in records:
            if "sound" not in r.packs or (a.record and r.name != a.record):
                continue
            off, size = r.packs["sound"]
            f.seek(r.offset + off)
            bank = Bank(f.read(size))
            counts = [len(samples(bd)) for _, _, bd in bank.subs]
            if a.list:
                print("%-8s %6X bytes, sub-banks %s, samples %s" % (
                    r.name, bank.total, [k for k, _, _ in bank.subs], counts))
            if a.wav:
                d = os.path.join(a.wav, r.name)
                os.makedirs(d, exist_ok=True)
                for k, (_, _, bd) in enumerate(bank.subs):
                    for s_off, data in samples(bd):
                        pcm = adpcm.decode(data)
                        adpcm.write_wav(os.path.join(d, "b%d_%05X.wav" % (k, s_off)), [pcm], a.rate)


if __name__ == "__main__":
    main()
