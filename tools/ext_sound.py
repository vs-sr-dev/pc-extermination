#!/usr/bin/env python3
"""Split Extermination's sound banks into their samples, at their real rates.

    python tools/ext_sound.py IDX DAT --list
    python tools/ext_sound.py IDX DAT --tones --record s04_r0
    python tools/ext_sound.py IDX DAT --record s04_r0 --wav out/

A sound bank is the first pack of a record (the loader hands it to the IOP
driver sndn2_driver through 0x001FBD00). Observed on every bank:

    +00 u32 total = hd size + bd size        +04 u32 0x20 + 16 n, first sub-bank header
    +08 u32 0                                +0C u32 n, sub-banks
    +10 u32 hd size (this header included)   +14 u32 bd size
    +18 u32 offset of the bd (= hd size)
    +20 n x { u32 bd size, u32 offset of the sub-bank's header (from the
              bank start), u32 kind (2 or 4), u32 0 }
    then n sub-bank headers, then the bd: n sample blocks, in order

The upload code (0x001FBD70) reads the samples from bank + [+0x18] and puts
each block in SPU memory at a base chosen by its kind (table at 0x00265400;
kind 4 blocks are shared across rooms). A sub-bank header runs to the next
one (or the end of the hd). The game's
sequencer runs on the EE (0x001152D8, once a frame) and reads it directly;
the IOP driver only receives voice commands. Offsets are from the start of
the sub-bank header (the base the EE registers with 0x00119528):

    +00 u32 ?   +04 u32 bd size   +08 u32 0   +0C "SShd"
    +10 u32 music programs (-1: none)          +14 u32 velocity table: u16, u8[128]
    +18 u32 LFO wave (-1: none)                +1C u32 effect table
    +20 u32 effect channels: 16 bytes, 48 x 16-byte channel states, then
            u16 last program, u16 offset of each program (from +24's target)
    +24 u32 program list

A program is 8 bytes, `u8 mode (0xFF: one tone per key), volume, pan, 0, bend
range, 0x7F, first key, last key`, then one 16-byte tone per key:

    +0 u8 lowest voice, u8 highest voice    +2 u8 centre note, s8 fine (1/16 semitone)
    +4 u16 sample offset in the bd / 8      +6 u16 ADSR1, u16 ADSR2
    +A u8 ?, u8 volume, u8 pan, u8 bend range, u8 0x7F, u8 flags

The effect table is `u16 last group`, then per group a u16 offset (from the
table; 0xFFFF: none) of `u16 last index, u16 offset of each sequence`.
0x00119EA0(bank, group, index) starts one. A sequence is MIDI-like, with a
variable-length delta after every event: `a0 key velocity program` (velocity
0: key off), `b0 cc a b program key` (07 volume, 0A pan, 41 pitch glide) or
`b0 60 a b c` (loop), `ff 2f` end.

The key picks the tone (key - first key) and, against the tone's centre
note, the pitch: 0x00117918 reads a table of 16 steps a semitone
(0x002428F0) where 0x1000 is the centre, and 0x00115850 scales the result by
44100 / 48000 for the 48 kHz SPU2. Each tone therefore plays its sample at

    44100 * 2 ** ((key - centre) / 12 + fine / 192) Hz

which comes out at 8 000, 16 000 or 32 000 Hz (to the 1/16 semitone) for
most samples; some tones replay a sample lower or higher for variety. --wav
writes each sample at the rate of the tone the sequences key most often.
"""
import argparse
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ps2kit import adpcm  # noqa: E402
import ext_index  # noqa: E402

NONE = 0xFFFFFFFF


class Tone:
    def __init__(self, program, key, raw):
        self.program, self.key = program, key
        (self.voice_lo, self.voice_hi, self.centre, self.fine, off,
         self.adsr1, self.adsr2, _, self.volume, self.pan, self.bend,
         _, self.flags) = struct.unpack("<BBBbHHHBBBBBB", raw)
        self.sample = off * 8

    @property
    def rate(self):
        return 44100 * 2 ** ((self.key - self.centre) / 12 + self.fine / 192)


class SubBank:
    """One sub-bank: its SShd header (programs, tones, sequences) and samples."""

    def __init__(self, kind, hd, bd):
        self.kind, self.hd, self.bd = kind, hd, bd
        if hd[12:16] != b"SShd":
            raise ValueError("no SShd header")
        self.programs = {}                      # program -> [Tone]
        self.sequences = {}                     # (group, index) -> bytes offset
        chan, plist = self.u32(0x20), self.u32(0x24)
        if chan != NONE and plist != NONE:
            last = self.u16(plist)
            for p in range(last + 1):
                po = plist + self.u16(plist + 2 + 2 * p)
                first, final = hd[po + 6], hd[po + 7]
                self.programs[p] = [Tone(p, first + t, hd[po + 8 + 16 * t:po + 24 + 16 * t])
                                    for t in range(final - first + 1)]
        table = self.u32(0x1C)
        if table != NONE:
            for g in range(self.u16(table) + 1):
                go = self.u16(table + 2 + 2 * g)
                if go == 0xFFFF:
                    continue
                for i in range(self.u16(table + go) + 1):
                    so = self.u16(table + go + 2 + 2 * i)
                    if so != 0xFFFF:
                        self.sequences[(g, i)] = table + so

    def u16(self, off):
        return struct.unpack_from("<H", self.hd, off)[0]

    def u32(self, off):
        return struct.unpack_from("<I", self.hd, off)[0]

    def events(self, off):
        """The events of the sequence at off: (status, data bytes)."""
        h, run, out = self.hd, None, []
        while True:
            if h[off] & 0x80:
                run, off = h[off], off + 1
            if run == 0xFF:
                if h[off] == 0x2F:
                    return out
                size = 3 if h[off] == 0x51 else None
            elif run & 0xF0 == 0xA0:
                size = 3
            elif run & 0xF0 == 0xB0:
                size = 4 if h[off] == 0x60 else 5
            else:
                size = None
            if size is None:
                raise ValueError("unknown event %02X at %X" % (run, off))
            out.append((run, h[off:off + size]))
            off += size
            while h[off] & 0x80:                        # delta time
                off += 1
            off += 1

    def tone(self, program, key):
        tones = self.programs.get(program, [])
        t = key - tones[0].key if tones else -1
        return tones[t] if 0 <= t < len(tones) else None

    def key_ons(self):
        """Counter of the tones the effect sequences key on."""
        c = collections.Counter()
        for off in self.sequences.values():
            for status, data in self.events(off):
                if status & 0xF0 == 0xA0 and data[1]:
                    t = self.tone(data[2], data[0])
                    if t:
                        c[t] += 1
        return c

    def sample_rates(self):
        """{sample offset: rate} from the tone keyed most often per sample."""
        best = {}
        for t, n in self.key_ons().items():
            if t.sample not in best or n > best[t.sample][0]:
                best[t.sample] = (n, t.rate)
        for tones in self.programs.values():            # tones no sequence plays
            for t in tones:
                best.setdefault(t.sample, (0, t.rate))
        return {off: r for off, (_, r) in best.items()}


class Bank:
    def __init__(self, buf):
        self.total, hd_off, _, n = struct.unpack_from("<4I", buf, 0)
        self.hd_size, self.bd_size, bd = struct.unpack_from("<3I", buf, 0x10)
        if (self.total != self.hd_size + self.bd_size or hd_off != 0x20 + 16 * n
                or bd != self.hd_size):
            raise ValueError("not a sound bank")
        entries = [struct.unpack_from("<4I", buf, 0x20 + 16 * k) for k in range(n)]
        ends = [e[1] for e in entries[1:]] + [self.hd_size]
        self.subs = []
        for (size, off, kind, _), end in zip(entries, ends):
            if struct.unpack_from("<I", buf, off + 4)[0] != size:
                raise ValueError("sub-bank at %X: sizes disagree" % off)
            self.subs.append(SubBank(kind, buf[off:end], buf[bd:bd + size]))
            bd += size
        if bd != self.total:
            raise ValueError("sample blocks do not add up")


def samples(bd):
    """(offset, bytes) of each sample: runs of frames up to an end flag.

    Samples are followed by Sony's end frame, `00 07 77 77 ...`, which is
    skipped."""
    out, start = [], 0
    for i in range(0, len(bd) - 15, 16):
        if bd[i + 1] & 1:
            if any(bd[start:i + 16]) and not (i == start and bd[i + 2:i + 16] == b"w" * 14):
                out.append((start, bd[start:i + 16]))
            start = i + 16
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--tones", action="store_true", help="list programs and tones")
    ap.add_argument("--record")
    ap.add_argument("--wav", metavar="DIR")
    ap.add_argument("--rate", type=int, default=0,
                    help="force one rate for every sample (default: each tone's)")
    a = ap.parse_args()
    records = ext_index.load(a.idx)
    with open(a.dat, "rb") as f:
        for r in records:
            if "sound" not in r.packs or (a.record and r.name != a.record):
                continue
            off, size = r.packs["sound"]
            f.seek(r.offset + off)
            bank = Bank(f.read(size))
            if a.list:
                print("%-8s %6X bytes, sub-banks %s, samples %s, programs %s, sequences %s" % (
                    r.name, bank.total, [s.kind for s in bank.subs],
                    [len(samples(s.bd)) for s in bank.subs],
                    [len(s.programs) for s in bank.subs],
                    [len(s.sequences) for s in bank.subs]))
            if a.tones:
                for k, sub in enumerate(bank.subs):
                    used = sub.key_ons()
                    for p, tones in sub.programs.items():
                        for t in tones:
                            print("%s b%d p%d key %02X  centre %02X fine %4d  sample %05X"
                                  "  %6.0f Hz  vol %3d pan %3d  flags %02X  keyed %d" % (
                                      r.name, k, p, t.key, t.centre, t.fine, t.sample,
                                      t.rate, t.volume, t.pan, t.flags, used[t]))
            if a.wav:
                d = os.path.join(a.wav, r.name)
                os.makedirs(d, exist_ok=True)
                for k, sub in enumerate(bank.subs):
                    rates = sub.sample_rates()
                    for s_off, data in samples(sub.bd):
                        rate = a.rate or round(rates.get(s_off, 22050))
                        pcm = adpcm.decode(data)
                        adpcm.write_wav(os.path.join(d, "b%d_%05X_%d.wav" % (k, s_off, rate)),
                                        [pcm], rate)


if __name__ == "__main__":
    main()
