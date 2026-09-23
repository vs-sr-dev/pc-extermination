"""VIF packets: walk a VIF1 (or VIF0) code stream and replay its UNPACKs.

    python -m ps2kit.vif packet.bin [--offset N] [--size N]

A VIF code is a 32-bit word: CMD in bits 24-30 (bit 31 is the interrupt
flag), NUM in 16-23, IMMEDIATE in 0-15. Most codes stand alone; STMASK,
STROW/STCOL, MPG, DIRECT/DIRECTHL and UNPACK carry data after them.

walk() yields one VifCode per code with its payload. unpack() expands an
UNPACK payload to its vector components as the VIF writes them to VU memory
(without STMOD/STMASK processing, which the callers so far do not need).
"""
import argparse
import struct

NAMES = {0x00: "NOP", 0x01: "STCYCL", 0x02: "OFFSET", 0x03: "BASE", 0x04: "ITOP",
         0x05: "STMOD", 0x06: "MSKPATH3", 0x07: "MARK", 0x10: "FLUSHE",
         0x11: "FLUSH", 0x13: "FLUSHA", 0x14: "MSCAL", 0x15: "MSCALF",
         0x17: "MSCNT", 0x20: "STMASK", 0x30: "STROW", 0x31: "STCOL",
         0x4A: "MPG", 0x50: "DIRECT", 0x51: "DIRECTHL"}
# UNPACK vn/vl: components per vector and bits per component
UNPACK_FORMATS = {0x0: ("S-32", 1, 32), 0x1: ("S-16", 1, 16), 0x2: ("S-8", 1, 8),
                  0x4: ("V2-32", 2, 32), 0x5: ("V2-16", 2, 16), 0x6: ("V2-8", 2, 8),
                  0x8: ("V3-32", 3, 32), 0x9: ("V3-16", 3, 16), 0xA: ("V3-8", 3, 8),
                  0xC: ("V4-32", 4, 32), 0xD: ("V4-16", 4, 16), 0xE: ("V4-8", 4, 8),
                  0xF: ("V4-5", 4, 5)}


class VifCode:
    def __init__(self, offset, word):
        self.offset = offset
        self.word = word
        self.irq = word >> 31
        self.cmd = (word >> 24) & 0x7F
        self.num = (word >> 16) & 0xFF
        self.imm = word & 0xFFFF
        self.data = b""

    @property
    def is_unpack(self):
        return self.cmd & 0x60 == 0x60

    @property
    def name(self):
        if self.is_unpack:
            return "UNPACK " + UNPACK_FORMATS.get(self.cmd & 0xF, ("?",))[0]
        return NAMES.get(self.cmd, "?%02X" % self.cmd)

    # UNPACK fields
    @property
    def addr(self):
        return self.imm & 0x3FF

    @property
    def usn(self):
        return self.imm >> 14 & 1

    @property
    def flg(self):
        return self.imm >> 15 & 1

    def __repr__(self):
        s = "%06x %s" % (self.offset, self.name)
        if self.is_unpack:
            s += " num=%d addr=%#x%s%s" % (self.num or 256, self.addr,
                                            " usn" if self.usn else "", " flg" if self.flg else "")
        elif self.cmd == 0x01:
            s += " cl=%d wl=%d" % (self.imm & 0xFF, self.imm >> 8)
        elif self.cmd in (0x14, 0x15, 0x17, 0x02, 0x03, 0x04, 0x07):
            s += " %#x" % self.imm
        elif self.data:
            s += " (%d bytes)" % len(self.data)
        return s


def _payload_size(c):
    if c.is_unpack:
        _, vn, vl = UNPACK_FORMATS.get(c.cmd & 0xF, ("?", 4, 32))
        n = c.num or 256
        bits = n * vn * vl if vl != 5 else n * 16
        return (bits // 8 + 3) & ~3
    if c.cmd == 0x20:
        return 4
    if c.cmd in (0x30, 0x31):
        return 16
    if c.cmd == 0x4A:
        return (c.num or 256) * 8
    if c.cmd in (0x50, 0x51):
        return (c.imm or 65536) * 16
    return 0


def walk(buf, offset=0, end=None):
    """Yield the VifCodes of buf[offset:end], payloads attached."""
    p = offset
    end = len(buf) if end is None else end
    while p + 4 <= end:
        c = VifCode(p, struct.unpack_from("<I", buf, p)[0])
        p += 4
        n = _payload_size(c)
        if c.cmd in (0x50, 0x51):                     # DIRECT data is qword aligned
            p = (p + 15) & ~15
        c.data = buf[p:p + n]
        p += n
        yield c


def unpack(c):
    """Components of an UNPACK payload: a list of vectors (tuples).

    32-bit components come back as raw u32 (reinterpret as float if needed);
    16- and 8-bit ones sign- or zero-extended as the USN bit says."""
    fmt, vn, vl = UNPACK_FORMATS[c.cmd & 0xF]
    n = c.num or 256
    d = c.data
    if vl == 32:
        vals = struct.unpack_from("<%dI" % (n * vn), d)
    elif vl == 16:
        vals = struct.unpack_from("<%d%s" % (n * vn, "H" if c.usn else "h"), d)
    elif vl == 8:
        vals = struct.unpack_from("<%d%s" % (n * vn, "B" if c.usn else "b"), d)
    else:                                              # V4-5: RGBA 5551
        vals = []
        for (h,) in struct.iter_unpack("<H", d[:2 * n]):
            vals += [(h & 31) << 3, (h >> 5 & 31) << 3, (h >> 10 & 31) << 3, (h >> 15) << 7]
    return [tuple(vals[i:i + vn]) for i in range(0, n * vn, vn)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packet")
    ap.add_argument("--offset", type=lambda v: int(v, 0), default=0)
    ap.add_argument("--size", type=lambda v: int(v, 0))
    a = ap.parse_args()
    buf = open(a.packet, "rb").read()
    end = a.offset + a.size if a.size else None
    for c in walk(buf, a.offset, end):
        print(c)


if __name__ == "__main__":
    main()
