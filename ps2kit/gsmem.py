"""A model of GS local memory: write transfers as the GS does, read back in any format.

    python -m ps2kit.gsmem packet.bin [packet.bin ...] --read BP,BW,PSM,W,H \\
        [--clut CBP,CPSM[,CSA]] --png out.png

GS memory is 4 MB, addressed in 256-byte blocks (BP) grouped into 8 KB pages.
Each pixel format lays a page out differently:

    format    page       block     block order in the page
    PSMCT32   64 x 32    8 x 8     8 wide x 4 tall   (table A)
    PSMCT16   64 x 64    16 x 8    4 wide x 8 tall   (table B)
    PSMT8     128 x 64   16 x 16   8 wide x 4 tall   (table A)
    PSMT4     128 x 128  32 x 16   4 wide x 8 tall   (table B)

A block is four 64-byte columns. Inside a column the 32-bit words follow one
fixed pattern (PSMCT32: 8 x 2 pixels, word = x/2*4 + y*2 + x%2); the other
formats pack their pixels into those same words:

* PSMCT16: pixel x of 16 takes the half-word x/8 of the word for (x%8, y).
* PSMT8 and PSMT4: a column is 16 x 4 (32 x 4) pixels. Pixel x takes the
  byte (nibble) x/8*2 + (y/2)%2 of the word for ((x + s)%8, y%2), where the
  shift s is 4 when bit 1 of y differs from the column's parity, else 0.

PSMCT24, PSMT8H and PSMT4HL/HH share the PSMCT32 layout and use part of the
word. PSMCT16S and the Z formats use their own block tables and are not
modelled yet.

Everything is plain arithmetic on (x, y); no per-format lookup table copied
from elsewhere. The layouts are checked against a real disc: the PSMT8 read
of a PSMCT32 upload reproduces gs.unswizzle8, which was verified on a title
page.
"""
import argparse
import struct

PSMCT32, PSMCT24, PSMCT16 = 0x00, 0x01, 0x02
PSMT8, PSMT4, PSMT8H, PSMT4HL, PSMT4HH = 0x13, 0x14, 0x1B, 0x24, 0x2C
NAMES = {PSMCT32: "PSMCT32", PSMCT24: "PSMCT24", PSMCT16: "PSMCT16",
         PSMT8: "PSMT8", PSMT4: "PSMT4", PSMT8H: "PSMT8H",
         PSMT4HL: "PSMT4HL", PSMT4HH: "PSMT4HH"}
BY_NAME = {v: k for k, v in NAMES.items()}

MEM_SIZE = 4 * 1024 * 1024
BLOCKS = MEM_SIZE // 256

# Block number inside a page, [row][col].
TABLE_A = [[0, 1, 4, 5, 16, 17, 20, 21],
           [2, 3, 6, 7, 18, 19, 22, 23],
           [8, 9, 12, 13, 24, 25, 28, 29],
           [10, 11, 14, 15, 26, 27, 30, 31]]
TABLE_B = [[0, 2, 8, 10], [1, 3, 9, 11], [4, 6, 12, 14], [5, 7, 13, 15],
           [16, 18, 24, 26], [17, 19, 25, 27], [20, 22, 28, 30], [21, 23, 29, 31]]

# Per base format: page w, page h, block w, block h, block table, bits/pixel.
GEOMETRY = {
    PSMCT32: (64, 32, 8, 8, TABLE_A, 32),
    PSMCT16: (64, 64, 16, 8, TABLE_B, 16),
    PSMT8: (128, 64, 16, 16, TABLE_A, 8),
    PSMT4: (128, 128, 32, 16, TABLE_B, 4),
}
# Formats that share a base layout: (base, bit shift in the unit, mask).
FORMATS = {
    PSMCT32: (PSMCT32, 0, 0xFFFFFFFF),
    PSMCT24: (PSMCT32, 0, 0x00FFFFFF),
    PSMT8H: (PSMCT32, 24, 0xFF),
    PSMT4HL: (PSMCT32, 24, 0xF),
    PSMT4HH: (PSMCT32, 28, 0xF),
    PSMCT16: (PSMCT16, 0, 0xFFFF),
    PSMT8: (PSMT8, 0, 0xFF),
    PSMT4: (PSMT4, 0, 0xF),
}


def _word32(x, y):
    """Word index (0-15) of PSMCT32 pixel (x%8, y%2) inside a column."""
    return (x >> 1 & 3) << 2 | (y & 1) << 1 | (x & 1)


def _in_block(base, x, y):
    """Bit offset of pixel (x, y) inside its block (x, y already block-local)."""
    if base == PSMCT32:
        return ((y >> 1) * 16 + _word32(x, y)) * 32
    if base == PSMCT16:
        return ((y >> 1) * 16 + _word32(x & 7, y)) * 32 + (x >> 3) * 16
    col = y >> 2
    shift = 4 if ((y >> 1) & 1) != (col & 1) else 0
    word = col * 16 + _word32((x + shift) & 7, y)
    sub = (x >> 3) * 2 + ((y >> 1) & 1)
    return word * 32 + sub * (8 if base == PSMT8 else 4)


def _tables(base):
    pw, ph, bw_, bh, table, _ = GEOMETRY[base]
    inblock = [[_in_block(base, x, y) for x in range(bw_)] for y in range(bh)]
    return pw, ph, bw_, bh, table, inblock


_TABLES = {b: _tables(b) for b in GEOMETRY}


def pixel_bits(psm, bp, bw, x, y):
    """Absolute bit address in GS memory of pixel (x, y) of a buffer.

    bw is the buffer width in 64-pixel units, as in BITBLTBUF and TEX0."""
    base = FORMATS[psm][0]
    pw, ph, bw_, bh, table, inblock = _TABLES[base]
    pages_per_row = max(1, bw * 64 // pw)
    page = (y // ph) * pages_per_row + x // pw
    block = bp + page * 32 + table[(y % ph) // bh][(x % pw) // bw_]
    return (block % BLOCKS) * 2048 + inblock[y % bh][x % bw_]


class Tex0:
    """The TEX0_1/TEX0_2 register: where a texture is and how to read it."""

    def __init__(self, v):
        self.value = v
        self.tbp, self.tbw, self.psm = v & 0x3FFF, v >> 14 & 63, v >> 20 & 63
        self.tw, self.th = v >> 26 & 15, v >> 30 & 15
        self.w, self.h = 1 << self.tw, 1 << self.th
        self.tcc, self.tfx = v >> 34 & 1, v >> 35 & 3
        self.cbp, self.cpsm, self.csm = v >> 37 & 0x3FFF, v >> 51 & 15, v >> 55 & 1
        self.csa, self.cld = v >> 56 & 31, v >> 61 & 7

    def plausible(self):
        """A loose filter for hunting TEX0 values in unknown data."""
        return self.psm in NAMES and 2 <= self.tw <= 10 and 2 <= self.th <= 10 \
            and self.tbw and self.cpsm in (PSMCT32, PSMCT16)

    def key(self):
        """The fields that decide the texels: address, format, size, CLUT."""
        return self.value & ((1 << 34) - 1) | self.value & (0x7FFFFFF << 37)

    def __repr__(self):
        return "Tex0(%s %dx%d at %#x bw=%d, clut %#x %s csa=%d, tcc=%d tfx=%d)" % (
            NAMES.get(self.psm, hex(self.psm)), self.w, self.h, self.tbp, self.tbw,
            self.cbp, NAMES.get(self.cpsm, hex(self.cpsm)), self.csa, self.tcc, self.tfx)


class GSMem:
    def __init__(self):
        self.mem = bytearray(MEM_SIZE)
        self.written = bytearray(BLOCKS)     # 1 where a transfer has stored data

    # -- raw access -----------------------------------------------------------
    def _address_rows(self, psm, bp, bw, x0, y0, w, h):
        """Yield, row by row, the bit addresses of a w x h rectangle."""
        base = FORMATS[psm][0]
        pw, ph, bw_, bh, table, inblock = _TABLES[base]
        ppr = max(1, bw * 64 // pw)
        for y in range(y0, y0 + h):
            prow = (y // ph) * ppr
            trow = table[(y % ph) // bh]
            irow = inblock[y % bh]
            yield [(((bp + (prow + x // pw) * 32 + trow[(x % pw) // bw_]) % BLOCKS) << 11)
                   + irow[x % bw_] for x in range(x0, x0 + w)]

    def write(self, psm, bp, bw, x0, y0, w, h, data):
        """Store a host-to-local transfer; data is the raw IMAGE payload."""
        mem = self.mem
        base, shift, mask = FORMATS[psm]
        if psm == PSMCT24:
            vals = iter(int.from_bytes(data[i:i + 3], "little")
                        for i in range(0, len(data) - 2, 3))
        elif base == PSMCT32:
            vals = iter(struct.unpack_from("<%dI" % (len(data) // 4), data))
        elif base == PSMCT16:
            vals = iter(struct.unpack_from("<%dH" % (len(data) // 2), data))
        elif base == PSMT8:
            vals = iter(data)
        else:
            vals = iter(b >> s & 15 for b in data for s in (0, 4))
        written = self.written
        for row in self._address_rows(psm, bp, bw, x0, y0, w, h):
            for a in row:
                written[a >> 11] = 1
                v = next(vals, None)
                if v is None:
                    return
                if base == PSMCT32 and mask == 0xFFFFFFFF:
                    struct.pack_into("<I", mem, a >> 3, v)
                elif base == PSMCT32:
                    o = a >> 3
                    cur = struct.unpack_from("<I", mem, o)[0]
                    cur = (cur & ~(mask << shift)) | ((v & mask) << shift)
                    struct.pack_into("<I", mem, o, cur & 0xFFFFFFFF)
                elif base == PSMCT16:
                    struct.pack_into("<H", mem, a >> 3, v)
                elif base == PSMT8:
                    mem[a >> 3] = v
                else:
                    o, s = a >> 3, a & 4
                    mem[o] = (mem[o] & (0xF0 >> s)) | (v << s)

    def read(self, psm, bp, bw, x0, y0, w, h):
        """Read a rectangle back; returns a flat list of pixel values."""
        mem = self.mem
        base, shift, mask = FORMATS[psm]
        out = []
        for row in self._address_rows(psm, bp, bw, x0, y0, w, h):
            if base == PSMCT32:
                out += [(int.from_bytes(mem[a >> 3:(a >> 3) + 4], "little") >> shift) & mask
                        for a in row]
            elif base == PSMCT16:
                out += [mem[a >> 3] | mem[(a >> 3) + 1] << 8 for a in row]
            elif base == PSMT8:
                out += [mem[a >> 3] for a in row]
            else:
                out += [(mem[a >> 3] >> (a & 4)) & 15 for a in row]
        return out

    # -- convenience ----------------------------------------------------------
    def apply(self, transfer):
        """Apply a gs.Transfer (host to local)."""
        t = transfer
        self.write(t.dpsm, t.dbp, t.dbw, t.dx, t.dy, t.w, t.h, t.data)

    def clut(self, cbp, cpsm=PSMCT32, csm=0, csa=0, entries=256):
        """Read a CLUT as RGBA tuples (alpha 0-128 scaled to 0-255).

        CSM1 only: the CLUT buffer is a 16 x 16 rectangle at cbp holding 256
        entries with 8-15 and 16-23 of every 32 swapped. A 16-colour palette
        is entries csa*16 to csa*16+15 of that buffer: an 8 x 2 rectangle."""
        if csm:
            raise NotImplementedError("CSM2")
        raw = self.read(cpsm, cbp, 1, 0, 0, 16, 16)
        return [to_rgba(raw[csm1(i & 255)], cpsm) for i in range(csa * 16, csa * 16 + entries)]

    def blocks(self, psm, bp, bw, w, h):
        """The set of blocks a w x h buffer touches."""
        return {a >> 11 for row in self._address_rows(psm, bp, bw, 0, 0, w, h) for a in row}

    def texture(self, t, tcc=None):
        """RGBA bytes of a texture described by a Tex0.

        With tcc 0 (the default follows the register) alpha is forced opaque,
        as the GS does when TCC says RGB only."""
        tex = self.read(t.psm, t.tbp, t.tbw, 0, 0, t.w, t.h)
        base = FORMATS[t.psm][0]
        bits = index_bits(t.psm)
        if bits:
            colours = self.clut(t.cbp, t.cpsm, t.csm, t.csa, 1 << bits)
        else:
            colours = [to_rgba(v, t.psm) for v in tex]
        if (t.tcc if tcc is None else tcc) == 0:
            colours = [c[:3] + (255,) for c in colours]
        if bits:
            return render(tex, colours)
        return b"".join(bytes(c) for c in colours)


def csm1(i):
    """Position in a CSM1 CLUT buffer of entry i."""
    return i & ~0x18 | (i & 8) << 1 | (i & 16) >> 1


def index_bits(psm):
    """8 or 4 for the indexed formats, 0 for direct colour."""
    return {PSMT8: 8, PSMT8H: 8, PSMT4: 4, PSMT4HL: 4, PSMT4HH: 4}.get(psm, 0)


def to_rgba(v, psm):
    if FORMATS[psm][0] == PSMCT16:
        r, g, b = (v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3
        return (r | r >> 5, g | g >> 5, b | b >> 5, 255 if v & 0x8000 else 0)
    a = v >> 24 & 0xFF if psm == PSMCT32 else 128
    return (v & 0xFF, v >> 8 & 0xFF, v >> 16 & 0xFF, min(a * 2, 255))


def render(texels, palette):
    """RGBA bytes from indices and a palette of RGBA tuples."""
    lut = [bytes(c) for c in palette]
    return b"".join(lut[v] for v in texels)


def grey(texels, bits):
    step = 255 // ((1 << bits) - 1)
    return render(texels, [(i * step,) * 3 + (255,) for i in range(1 << bits)])


def main():
    from . import gs
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packets", nargs="+")
    ap.add_argument("--read", required=True, metavar="BP,BW,PSM,W,H",
                    help="BP and BW as in TEX0 (hex allowed), PSM by name or number")
    ap.add_argument("--at", default="0,0", metavar="X,Y")
    ap.add_argument("--clut", metavar="CBP,CPSM[,CSA]")
    ap.add_argument("--png", required=True)
    a = ap.parse_args()
    m = GSMem()
    for p in a.packets:
        for t in gs.walk(open(p, "rb").read()):
            m.apply(t)
    bp, bw, psm, w, h = a.read.split(",")
    bp, bw, w, h = int(bp, 0), int(bw, 0), int(w, 0), int(h, 0)
    psm = BY_NAME.get(psm.upper(), None) if not psm[0].isdigit() else int(psm, 0)
    x, y = (int(v, 0) for v in a.at.split(","))
    tex = m.read(psm, bp, bw, x, y, w, h)
    bits = index_bits(psm)
    if bits and a.clut:
        f = a.clut.split(",")
        cbp, cpsm = int(f[0], 0), BY_NAME.get(f[1].upper(), PSMCT32)
        csa = int(f[2], 0) if len(f) > 2 else 0
        rgba = render(tex, m.clut(cbp, cpsm, csa=csa, entries=1 << bits))
    elif bits:
        rgba = grey(tex, bits)
    else:
        rgba = b"".join(bytes(to_rgba(v, psm)) for v in tex)
    gs.write_png(a.png, w, h, rgba)


if __name__ == "__main__":
    main()
