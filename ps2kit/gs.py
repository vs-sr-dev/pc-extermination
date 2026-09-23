"""GS upload packets and indexed textures uploaded through PSMCT32.

    python -m ps2kit.gs packet.bin --list
    python -m ps2kit.gs packet.bin --t8 0 --clut 0,352 --png out.png

Games commonly ship textures as ready-made path-2 packets: a DMA tag, VIF
DIRECT, then GIF tags that set BITBLTBUF/TRXPOS/TRXREG/TRXDIR and stream the
pixels with an IMAGE tag. walk() replays such a packet and returns every
image transfer with its registers.

A frequent trick is to upload 8-bit (and 4-bit) texel data through a PSMCT32
transfer: fewer, larger transfers. The bytes then sit in GS memory in the
PSMCT32 arrangement, and must be read back through the PSMT8 layout. For an
8-bit texture of w x h uploaded as a (w/2) x (h/2) PSMCT32 rectangle, the
pages and blocks of the two formats coincide, so a closed-form remap of the
transfer's raster order is enough: unswizzle8().

CLUTs travel the same way, as 16x16 PSMCT32 rectangles for 256 colours, with
entries in CSM1 order (entries 8-15 and 16-23 of every 32 swapped).
Alpha is 0-128, 128 meaning opaque.
"""
import argparse
import struct
import zlib

REG_BITBLTBUF, REG_TRXPOS, REG_TRXREG = 0x50, 0x51, 0x52
PSM_NAMES = {0x00: "PSMCT32", 0x01: "PSMCT24", 0x02: "PSMCT16", 0x0A: "PSMCT16S",
             0x13: "PSMT8", 0x14: "PSMT4", 0x1B: "PSMT8H", 0x24: "PSMT4HL",
             0x2C: "PSMT4HH"}


class Transfer:
    def __init__(self, regs, data):
        b = regs.get(REG_BITBLTBUF, 0)
        pos = regs.get(REG_TRXPOS, 0)
        reg = regs.get(REG_TRXREG, 0)
        self.dbp = (b >> 32) & 0x3FFF          # destination, in 256-byte blocks
        self.dbw = (b >> 48) & 0x3F            # width, in 64-pixel units
        self.dpsm = (b >> 56) & 0x3F
        self.dx, self.dy = (pos >> 32) & 0x7FF, (pos >> 48) & 0x7FF
        self.w, self.h = reg & 0xFFF, (reg >> 32) & 0xFFF
        self.data = data

    def __repr__(self):
        return "Transfer(%s %dx%d at block %#x, bw=%d, pos=%d,%d, %d bytes)" % (
            PSM_NAMES.get(self.dpsm, hex(self.dpsm)), self.w, self.h, self.dbp,
            self.dbw, self.dx, self.dy, len(self.data))


def walk(buf):
    """Replay a DMA/VIF/GIF packet; return its image transfers in order."""
    transfers, regs = [], {}
    p = 0
    while p + 16 <= len(buf):
        tag, = struct.unpack_from("<Q", buf, p)
        qwc, tid = tag & 0xFFFF, (tag >> 28) & 7
        q, end = p + 16, p + 16 + 16 * qwc
        while q < end:
            lo, hi = struct.unpack_from("<QQ", buf, q)
            q += 16
            nloop = lo & 0x7FFF
            flg = (lo >> 58) & 3
            nreg = (lo >> 60) & 15 or 16
            if flg == 0:                                         # PACKED
                order = [(hi >> (4 * i)) & 15 for i in range(nreg)]
                for _ in range(nloop):
                    for r in order:
                        data, addr = struct.unpack_from("<QQ", buf, q)
                        q += 16
                        if r == 0xE:                             # A+D
                            regs[addr & 0xFF] = data
            elif flg == 2:                                       # IMAGE
                transfers.append(Transfer(regs, buf[q:q + 16 * nloop]))
                q += 16 * nloop
            else:                                                # REGLIST, rarely used here
                q += 16 * nloop * (1 if flg == 3 else (nreg + 1) // 2)
        p = end
        if tid in (6, 7):                                        # ret / end
            break
    return transfers


def unswizzle8(ct32, w, h):
    """PSMT8 texels (w x h, bytes) from a (w/2 x h/2) PSMCT32 upload's raster."""
    out = bytearray(w * h)
    for y in range(h):
        swap = (((y + 2) >> 2) & 1) * 4
        row = (((y & ~3) >> 1) + (y & 1)) & 7
        base = (y & ~0xF) * w + row * w * 2
        byte_y = (y >> 1) & 1
        o = y * w
        for x in range(w):
            out[o + x] = ct32[base + (x & ~0xF) * 2 + ((x + swap) & 7) * 4
                              + byte_y + ((x >> 2) & 2)]
    return bytes(out)


def csm1(i):
    return (i & ~0x18) | ((i & 8) << 1) | ((i & 16) >> 1)


def clut256(ct32, width, x, y):
    """A 256-colour CLUT at (x, y) of a PSMCT32 raster `width` pixels wide.

    Returns 256 RGBA tuples, alpha scaled from 0-128 to 0-255."""
    raw = []
    for r in range(16):
        o = ((y + r) * width + x) * 4
        raw += [tuple(ct32[o + 4 * c:o + 4 * c + 4]) for c in range(16)]
    return [raw[csm1(i)][:3] + (min(raw[csm1(i)][3] * 2, 255),) for i in range(256)]


def write_png(path, w, h, rgba):
    """Minimal RGBA PNG writer (no dependencies)."""
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("packet")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--t8", type=int, metavar="N", help="read transfer N as PSMT8")
    ap.add_argument("--clut", metavar="X,Y", help="CLUT position in the same transfer's raster")
    ap.add_argument("--png")
    a = ap.parse_args()
    transfers = walk(open(a.packet, "rb").read())
    if a.list:
        for i, t in enumerate(transfers):
            print(i, t)
    if a.t8 is not None:
        t = transfers[a.t8]
        w, h = 2 * t.w, 2 * t.h
        texels = unswizzle8(t.data, w, h)
        if a.clut:
            cx, cy = (int(v) for v in a.clut.split(","))
            pal = [bytes(c) for c in clut256(t.data, t.w, cx, cy)]
        else:
            pal = [bytes((i, i, i, 255)) for i in range(256)]
        write_png(a.png, w, h, b"".join(pal[v] for v in texels))


if __name__ == "__main__":
    main()
