#!/usr/bin/env python3
"""Read Extermination's DATA index and extract resources.

    python tools/ext_index.py E:/DATA/INDEX_IT.IDX --list
    python tools/ext_index.py E:/DATA/INDEX_IT.IDX --verify
    python tools/ext_index.py E:/DATA/INDEX_IT.IDX --dat E:/DATA/DATA_IT.DAT \\
        --extract out/ [--section 4]

INDEX_xx.IDX is an array of 0x800-byte sections, one per game section (areas,
system data, fonts...). Each section holds one main record at +0x000 and up to
N sub-records at +0x100 + 0x70*k (the rooms of an area). A record:

    +00 u32 id               section number, or sub-record number
    +04 u32 offset           into DATA_xx.DAT, bytes, sector aligned
    +08 u32 size             bytes
    +0C u32 flags            bit 0: sound bank present, bit 16: GS pack present
    +10 u32 uploads          extra (off, size) pairs after the packs (section 27)
    +14 u32 packs_size       bytes taken by the packs at the start of the record
    +18 u32 subrecords       number of sub-records (main record only)
    +1C u32 count            number of resources
    +20 [u32 off, u32 size]  sound bank, if flags bit 0
        [u32 off, u32 size]  GS pack, if flags bit 16
        [u32 off, u32 size]  x uploads, relative like resources; they overlap
                             resources and describe GS packets inside them
        u32 resources[count] (slot << 24) | offset, offset relative to
                             offset + packs_size

The sound bank carries an SShd header 0x3C-0x6C bytes in; the GS pack is an
upload packet (DMA tag + VIF DIRECT + GIF image transfers) with the record's
textures. Both packs sit at the start of the record, sound bank first, which
is why resource offsets are relative to offset + packs_size. A resource's
size is the distance to the next resource in offset order, or to the end of
the record.
Slot numbers are resource identifiers local to the section; the slot says
what the resource is used for, the bytes say what format it is in.
"""
import argparse
import os
import struct

SECTION = 0x800
SUB_BASE, SUB_SIZE = 0x100, 0x70
FLAG_SOUND, FLAG_GS = 0x1, 0x10000


class Record:
    def __init__(self, buf, at, section, sub):
        (self.id, self.offset, self.size, self.flags, uploads,
         self.packs_size, self.subrecords, count) = struct.unpack_from("<8I", buf, at)
        self.section, self.sub = section, sub
        p = at + 0x20
        self.packs = {}
        for bit, name in ((FLAG_SOUND, "sound"), (FLAG_GS, "gs")):
            if self.flags & bit:
                self.packs[name] = struct.unpack_from("<2I", buf, p)
                p += 8
        self.uploads = [struct.unpack_from("<2I", buf, p + 8 * i) for i in range(uploads)]
        p += 8 * uploads
        raw = struct.unpack_from("<%dI" % count, buf, p)
        self.resources = [(w >> 24, w & 0xFFFFFF) for w in raw]

    @property
    def name(self):
        return "s%02d" % self.section if self.sub < 0 else "s%02d_r%d" % (self.section, self.sub)

    def items(self):
        """Yield (label, absolute offset, size) for packs, then resources."""
        for name, (off, size) in self.packs.items():
            yield name, self.offset + off, size
        base = self.offset + self.packs_size
        order = sorted(self.resources, key=lambda r: r[1])
        for i, (slot, off) in enumerate(order):
            end = order[i + 1][1] if i + 1 < len(order) else self.size - self.packs_size
            yield "slot%02X" % slot, base + off, end - off


def load(idx_path):
    data = open(idx_path, "rb").read()
    records = []
    for s in range(len(data) // SECTION):
        buf = data[s * SECTION:(s + 1) * SECTION]
        main = Record(buf, 0, s, -1)
        records.append(main)
        for k in range(main.subrecords):
            records.append(Record(buf, SUB_BASE + SUB_SIZE * k, s, k))
    return records


def verify(records, dat_size=None):
    """Check the invariants the layout above claims. Returns a list of problems."""
    problems = []
    pos = 0
    for r in records:
        if r.offset != pos:
            problems.append("%s starts at %#x, expected %#x" % (r.name, r.offset, pos))
        pos = r.offset + r.size
        for off, size in r.uploads:
            if not any(o == off for _, o in r.resources):
                problems.append("%s: upload at %#x matches no resource" % (r.name, off))
        packs = sum(size for _, size in r.packs.values())
        if packs != r.packs_size:
            problems.append("%s: packs add up to %#x, header says %#x" % (r.name, packs, r.packs_size))
        for label, off, size in r.items():
            if size < 0 or off + size > r.offset + r.size:
                problems.append("%s %s runs past the record" % (r.name, label))
    if dat_size is not None and pos != dat_size:
        problems.append("records end at %#x, DATA file is %#x" % (pos, dat_size))
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("--dat")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--extract", metavar="DIR")
    ap.add_argument("--section", type=int)
    a = ap.parse_args()
    records = load(a.idx)
    if a.section is not None:
        records = [r for r in records if r.section == a.section]

    if a.list:
        for r in records:
            print("%-8s off=%08X size=%07X packs=%s resources=%d" % (
                r.name, r.offset, r.size,
                ",".join("%s:%X" % (k, v[1]) for k, v in r.packs.items()) or "-",
                len(r.resources)))
            for label, off, size in r.items():
                print("    %-7s %08X %7X" % (label, off, size))
    if a.verify:
        size = os.path.getsize(a.dat) if a.dat else None
        problems = verify(load(a.idx), size)
        print("\n".join(problems) or "index OK: %d records" % len(records))
    if a.extract:
        if not a.dat:
            ap.error("--extract needs --dat")
        with open(a.dat, "rb") as f:
            for r in records:
                d = os.path.join(a.extract, r.name)
                os.makedirs(d, exist_ok=True)
                for label, off, size in r.items():
                    f.seek(off)
                    with open(os.path.join(d, label + ".bin"), "wb") as o:
                        o.write(f.read(size))


if __name__ == "__main__":
    main()
