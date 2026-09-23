#!/usr/bin/env python3
"""Extract Extermination's textures as the GS would read them.

    python tools/ext_tex.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT --census
    python tools/ext_tex.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT \\
        --png out/ [--section 4]

The GS pack of a record only uploads 256-wide PSMCT32 pages. How they are
read back is written in the geometry: every vertex of the room meshes carries
the TEX0 register of its texture (64-byte vertices, TEX0 in the first
quadword with a zero upper half). This tool replays the record's GS pack into
a GS memory model, collects every distinct TEX0 from the record's resources,
checks that its texels and CLUT lie in uploaded memory, and renders it.

Rooms do not stand alone. The resident set is, as the game builds it:

* section 27's two "uploads" (GS packets inside its resources, kicked at
  boot): weapons, effects, pickups, HUD at blocks 0x1D00-0x24FF;
* one of section 3's slots 6-10, a character page at 0x1B80, picked by the
  area loader's tail (0x002012D0) from two globals. Slot 6 is a half page
  (256x32), slots 7-10 full pages (256x64); any full page resolves every
  texture of sections 3 and 28, so the default is slot 7.

Room packs load at 0x2A00 and up. The area loader (0x00200710) kicks the
area's main-record pack first, then the room's, and an area's own resources
stay loaded beside every room. So a room is read with its area's pack under
its own, and an area's resources count as resolved if they resolve in any of
its rooms. Every record is read on top of the resident set unless
--no-resident is given; --variant picks the section 3 slot.

Only textures whose texels and CLUT were uploaded are written as PNG.
The game stores its textures bottom-up (lettering reads upside down in GS
memory; the vertex UVs compensate), so PNGs are flipped upright unless --raw
is given.
Textures are named by the fields that decide their pixels:
    <tbp>_<psm>_<w>x<h>_c<cbp>[_a<csa>].png
"""
import argparse
import collections
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ps2kit import gs, gsmem  # noqa: E402
import ext_index  # noqa: E402


def find_tex0(buf):
    """Yield (offset, Tex0) for TEX0-looking quadwords: 16-aligned, upper half 0."""
    for o in range(0, len(buf) - 15, 16):
        v, z = struct.unpack_from("<QQ", buf, o)
        if z or not v:
            continue
        t = gsmem.Tex0(v)
        if t.plausible() and gsmem.index_bits(t.psm):
            yield o, t


RESIDENT_SECTION = 27
VARIANT_SECTION, VARIANT_SLOTS = 3, range(6, 11)


def resident(f, records, variant=7):
    """GS memory holding the resident set: section 27 uploads, a section 3 variant."""
    mem = gsmem.GSMem()
    for r in records:
        if r.sub >= 0:
            continue
        if r.section == RESIDENT_SECTION:
            base = r.offset + r.packs_size
            for off, size in r.uploads:
                f.seek(base + off)
                for t in gs.walk(f.read(size)):
                    mem.apply(t)
        if r.section == VARIANT_SECTION:
            for label, off, size in r.items():
                if label == "slot%02X" % variant:
                    f.seek(off)
                    for t in gs.walk(f.read(size)):
                        mem.apply(t)
    return mem


def gs_pack(f, r):
    if "gs" not in r.packs:
        return b""
    off, size = r.packs["gs"]
    f.seek(r.offset + off)
    return f.read(size)


def resources(f, r):
    res = {}
    for label, off, size in r.items():
        if label.startswith("slot"):
            f.seek(off)
            res[label] = f.read(size)
    return res


def memory(base, *packs):
    """GS memory: a copy of base (or empty) with the packs kicked in order."""
    mem = gsmem.GSMem()
    if base is not None:
        mem.mem[:] = base.mem
        mem.written[:] = base.written
    for p in packs:
        for t in gs.walk(p):
            mem.apply(t)
    return mem


def contexts(f, r, records, base):
    """The GS memory states a record's textures are drawn with."""
    main = next(m for m in records if m.section == r.section and m.sub < 0)
    rooms = [x for x in records if x.section == r.section and x.sub >= 0]
    if r.sub >= 0:
        return [memory(base, gs_pack(f, main), gs_pack(f, r))]
    if rooms:
        return [memory(base, gs_pack(f, r), gs_pack(f, x)) for x in rooms]
    return [memory(base, gs_pack(f, r))]


def survey(mems, res):
    """Distinct textures: {key: [Tex0, uses, slots, memory it resolves in or None]}."""
    tex = {}
    for label, data in res.items():
        for _, t in find_tex0(data):
            e = tex.setdefault(t.key(), [t, 0, set(), None])
            e[1] += 1
            e[2].add(label)
    for e in tex.values():
        t = e[0]
        for mem in mems:
            need = mem.blocks(t.psm, t.tbp, t.tbw, t.w, t.h)
            need |= mem.blocks(t.cpsm, t.cbp, 1, 16, 16 if gsmem.index_bits(t.psm) == 8 else 2)
            if all(mem.written[b] for b in need):
                e[3] = mem
                break
    return tex


def flip(rgba, w, h):
    s = 4 * w
    return b"".join(rgba[y * s:(y + 1) * s] for y in range(h - 1, -1, -1))


def name(t):
    s = "%04x_%s_%dx%d_c%04x" % (t.tbp, gsmem.NAMES[t.psm], t.w, t.h, t.cbp)
    return s + ("_a%d" % t.csa if t.csa else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--section", type=int)
    ap.add_argument("--census", action="store_true")
    ap.add_argument("--png", metavar="DIR")
    ap.add_argument("--no-resident", action="store_true")
    ap.add_argument("--raw", action="store_true", help="keep GS row order (bottom-up)")
    ap.add_argument("--variant", type=lambda v: int(v, 0), default=7,
                    choices=VARIANT_SLOTS, help="section 3 slot for the character page")
    a = ap.parse_args()
    records = ext_index.load(a.idx)
    with open(a.dat, "rb") as f:
        base = None if a.no_resident else resident(f, records, a.variant)
        for r in records:
            if a.section is not None and r.section != a.section:
                continue
            res = resources(f, r)
            tex = survey(contexts(f, r, records, base) if res else [], res)
            if not tex and "gs" not in r.packs:
                continue
            if a.census:
                fmt = collections.Counter("%s %dx%d" % (gsmem.NAMES[e[0].psm], e[0].w, e[0].h)
                                          for e in tex.values())
                missing = [e for e in tex.values() if not e[3]]
                slots = sorted({s for e in tex.values() for s in e[2]})
                print("%-7s gs=%-3s textures=%3d uses=%6d outside upload=%3d slots=%s" % (
                    r.name, "yes" if "gs" in r.packs else "no", len(tex),
                    sum(e[1] for e in tex.values()), len(missing), ",".join(slots)))
                if missing:
                    print("        e.g. %r" % missing[0][0])
                print("        " + ", ".join("%s: %d" % kv for kv in sorted(fmt.items())))
            if a.png:
                d = os.path.join(a.png, r.name)
                os.makedirs(d, exist_ok=True)
                for t, _, _, mem in tex.values():
                    if mem is None:
                        continue
                    rgba = mem.texture(t, tcc=1)
                    if not a.raw:
                        rgba = flip(rgba, t.w, t.h)
                    gs.write_png(os.path.join(d, name(t) + ".png"), t.w, t.h, rgba)


if __name__ == "__main__":
    main()
