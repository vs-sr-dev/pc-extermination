#!/usr/bin/env python3
"""Turn the runtime's GS memory dumps (PS2X_DUMP_VRAM) into screenshots.

    python tools/recomp/vram_shot.py vram_*.bin [--out DIR] [--sheet sheet.png]

Each dump is 8 u64 (PMODE, SMODE2, DISPFB1, DISPLAY1, DISPFB2, DISPLAY2,
vsync tick, 0) followed by the 4 MB of GS local memory. The picture is read
from the buffer DISPFB1 points at, at the size DISPLAY1 gives (DW+1 / MAGH+1
by DH+1). A picture of 288 lines or fewer is doubled vertically, as a
television shows it. --sheet also lays all of them out on
one contact sheet, with the tick under each.
"""
import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ps2kit import gs, gsmem  # noqa: E402


def shot(path):
    raw = open(path, "rb").read()
    pmode, smode2, dispfb, display, _, _, tick, _ = struct.unpack_from("<8Q", raw)
    m = gsmem.GSMem()
    m.mem[:] = raw[64:64 + gsmem.MEM_SIZE]
    fbp = dispfb & 0x1FF
    fbw = (dispfb >> 9) & 0x3F
    psm = (dispfb >> 15) & 0x1F
    magh = ((display >> 23) & 0xF) + 1
    w = (((display >> 32) & 0xFFF) + 1) // magh
    h = ((display >> 44) & 0x7FF) + 1
    w = min(w, fbw * 64) or 640
    px = m.read(psm, fbp * 32, fbw, 0, 0, w, h)
    rgba = bytearray()
    for p in px:
        if psm in (gsmem.PSMCT16, 0x0A):  # PSMCT16, PSMCT16S
            rgba += bytes(((p & 31) << 3, ((p >> 5) & 31) << 3, ((p >> 10) & 31) << 3, 255))
        else:
            rgba += bytes((p & 255, (p >> 8) & 255, (p >> 16) & 255, 255))
    if h <= 288:  # one field's worth of lines (or a half-height frame)
        rows = [rgba[y * w * 4:(y + 1) * w * 4] for y in range(h)]
        rgba = b"".join(r + r for r in rows)
        h *= 2
    return tick, w, h, bytes(rgba)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dumps", nargs="+")
    ap.add_argument("--out", default=".", help="directory for one PNG per dump")
    ap.add_argument("--sheet", help="contact sheet PNG of all dumps, half size")
    args = ap.parse_args()
    shots = []
    for path in sorted(args.dumps):
        tick, w, h, rgba = shot(path)
        name = os.path.join(args.out, "shot_t%06d.png" % tick)
        gs.write_png(name, w, h, rgba)
        print(name, w, "x", h)
        shots.append((tick, w, h, rgba))
    if args.sheet and shots:
        cols = 4
        tw, th = 320, 224
        rows = (len(shots) + cols - 1) // cols
        sheet = bytearray(b"\x20\x20\x20\xff" * (cols * tw * rows * th))
        for i, (tick, w, h, rgba) in enumerate(shots):
            ox, oy = (i % cols) * tw, (i // cols) * th
            for y in range(th - 1):
                sy = y * h // th
                for x in range(tw - 1):
                    sx = x * w // tw
                    o = (sy * w + sx) * 4
                    d = ((oy + y) * cols * tw + ox + x) * 4
                    sheet[d:d + 4] = rgba[o:o + 4]
        gs.write_png(args.sheet, cols * tw, rows * th, bytes(sheet))
        print(args.sheet, "ticks", [s[0] for s in shots])


if __name__ == "__main__":
    main()
