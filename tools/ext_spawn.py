#!/usr/bin/env python3
"""Read Extermination's actor spawn tables; place a room's actors in glTF.

    python tools/ext_spawn.py SCES_502.40 OVERLAY/AREA00.BIN IDX --area 0 --list
    python tools/ext_spawn.py SCES_502.40 OVERLAY/AREA00.BIN IDX --area 0 --room 0 \\
        --dat DAT --gltf out/room.gltf
    python tools/ext_spawn.py SCES_502.40 OVERLAY IDX --dat DAT --all out/

The chain, from the code (PAL addresses):

    0x0024E3A0  u32 per area: address of a room table (0: none)
    room table  u32 per room: address of a NULL-terminated list of spawn tables
    spawn table 44-byte records, walked by 0x001B6E30 when a room starts
                (0x001B70E0), ended by a record whose first u16 is 0xFFFF

The addresses point into the area's overlay (whose file is read whole, header
included, to 0x00826080) or into the executable's data. A record:

    +00 u16 condition   0 always; 1 unless flag[p] is set (a pickup taken,
                        an enemy killed); 2-6 other tests on the tables at
                        0x008132D8 and 0x00813358, indexed by p >> 8
    +02 u16 p           low byte -> actor +0x9A (the actor's flag number)
    +04 u16 type        low byte: the actor class allocated by 0x001B0260
    +06 u16             low byte -> actor +0x03, high byte -> actor +0x2E
    +08 u16 model       low byte -> actor +0x0D: a model index, see below
    +0A u16             -> actor +0x0E (class 2: +0x9E, with the room)
    +0C u16             -> actor +0x54
    +0E u16             -> actor +0x56
    +10 f32 x, y, z     -> actor +0xB0, position in room space (y up)
    +1C f32 rx, ry, rz  -> actor +0xC0, radians
    +28 u32             -> actor +0x10, the behaviour function, run every frame

The actor's matrix is T * Rz * Ry * Rx * S (0x001C9CA0). Behaviours pick the
model on their first frame; every path ends in 0x001CADD0 (actor +0x44 =
mesh). The ones on the disc:

    table[0x35][model]   0x001B1590: resident models (section 27)
    table[0x43][model]   0x001B1670: the room's props
    table[slot]          0x001B1880(actor, mesh slot, animation slot): the
                         creatures, whose class init picks the slot from
                         the model byte (bit 7, bit 0) - see CLASSES
    table[slot]          0x001D1470(actor, mesh): 0x1A and 0x20 (section 3)

Pickups (0x0015AFB0) use the room's props when (+0x03 & 0xF) == 1; the
container behaviour 0x0021A0D0 when +0x03 == 0 and +0x2E == 0x28. Two common
classes draw no mesh: 0x001E4720 is a sprite emitter with a sound (0x411 +
model), 0x0015AB10 a volume sized from the table at 0x00248E10. Classes in
the overlays (0x0082xxxx) are in OVERLAY_CLASSES, by area; the few not read
yet are exported as empties.

A slot is looked up as the loader fills the table: the room record, the
area's main record, then the resident sections (27, 28, 3, 0-2). Two globals
switch creatures to their other variant (0x00813388) and the larva to slot
0x0E (0x00813308); the export assumes neither is set.
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ps2kit import elf, mwo3  # noqa: E402
import ext_anim  # noqa: E402
import ext_index  # noqa: E402
import ext_mesh  # noqa: E402
import ext_tex  # noqa: E402

AREA_TABLE = 0x0024E3A0          # PAL SCES-502.40
RECORD = 44
RESIDENT_SECTIONS = (27, 28, 3, 0, 1, 2)
OVERLAY_OF_AREA = {5: 4, 9: 8, 10: 8, 12: 11}    # cut areas reuse the previous file


def _pair(first, second, bit0=None):
    """Creature init: the model byte's bit 7 picks the second mesh; bit 0,
    when given, picks another pair."""
    def rule(s):
        a, b = bit0 if bit0 and s.model & 1 else (first, second)
        return (b if s.model & 0x80 else a), None
    return rule


# behaviour -> (name, rule(spawn) -> (slot, index or None for the whole resource))
CLASSES = {
    0x0015AFB0: ("pickup", lambda s: ((0x43 if s.a03 & 0xF == 1 else 0x35), s.model & 0xFF)),
    0x0021A0D0: ("container", lambda s: ((0x43 if s.a03 == 0 and s.a2e == 0x28 else 0x35),
                                         s.model & 0xFF)),
    0x0021A3F0: ("prop", lambda s: (0x43, s.model & 0xFF)),
    0x001C50A0: ("prop", lambda s: (0x43, s.model & 0xFF)),
    0x001551B0: ("breakable", lambda s: (0x43, s.model & 0xFF)),
    0x001C0EB0: ("resident", lambda s: (0x35, s.model & 0xFF)),
    0x00128C00: ("larva", lambda s: (0x0D, None)),
    0x0012A5C0: ("larva", lambda s: (0x0D, None)),
    0x0012E390: ("creature", _pair(0x72, 0x74, (0x6E, 0x70))),
    0x001383B0: ("bat", _pair(0x79, 0x7B)),
    0x0013D2C0: ("crawler", _pair(0x75, 0x77)),
    0x00141D10: ("dog", _pair(0x7D, 0x7E)),
    0x00147380: ("mutant", _pair(0x82, 0x83)),
    0x001C1800: ("growth", lambda s: (0x24, None)),
    0x001BF490: ("flesh", lambda s: (0x1A, None)),
    0x001BFE80: ("eggs", lambda s: (0x20, None)),
    0x001C0AB0: ("eggs", lambda s: (0x20, None)),
    0x001E4720: ("emitter", None),
    0x0015AB10: ("volume", None),
}

_prop = lambda s: (0x43, s.model & 0xFF)          # noqa: E731
# (area, behaviour) -> (name, rule) for classes in the overlays, whose
# addresses repeat from one overlay to the next. Most are doors and props
# built by ActorInitRoomProp (the same pair of functions in every overlay).
OVERLAY_CLASSES = {
    (0, 0x00827A20): ("larva", lambda s: (0x0D, None)),
    (1, 0x008284D0): ("a01_model", lambda s: (s.model & 0xFF, None)),    # 'G' 0x47, 'K' 0x4B
    (3, 0x008264B0): ("door", _prop), (3, 0x00827E10): ("prop", _prop),
    (4, 0x00826C80): ("a04_4E", lambda s: (0x4E, None)),
    (7, 0x00826B00): ("door", _prop), (7, 0x00828550): ("prop", _prop),
    (11, 0x008284C0): ("door", _prop), (11, 0x0082A010): ("prop", _prop),
    (13, 0x00827730): ("door", _prop), (13, 0x00829220): ("prop", _prop),
    (14, 0x00826B40): ("door", _prop), (14, 0x00828620): ("prop", _prop),
    (17, 0x00828C40): ("resident", lambda s: (0x35, s.model & 0xFF)),
    (19, 0x0082A950): ("door", _prop), (19, 0x0082C450): ("prop", _prop),
    (20, 0x00826FC0): ("door", _prop), (20, 0x00828AA0): ("prop", _prop),
}


class Memory:
    """The executable and one overlay, addressed as the EE sees them."""

    def __init__(self, exe, overlay):
        self.exe, self.ov = exe, overlay

    def read(self, va, n):
        if self.ov.load <= va < self.ov.data_va + self.ov.data_size:
            return self.ov.read(va, n)
        return self.exe.read(va, n)

    def u32(self, va):
        return struct.unpack("<I", self.read(va, 4))[0]


class Spawn:
    def __init__(self, raw, va):
        self.va = va
        (self.condition, self.p, self.type, w6, self.model, self.param,
         self.p54, self.p56) = struct.unpack_from("<8H", raw)
        self.a03, self.a2e = w6 & 0xFF, w6 >> 8
        self.pos = struct.unpack_from("<3f", raw, 0x10)
        self.rot = struct.unpack_from("<3f", raw, 0x1C)
        self.behaviour, = struct.unpack_from("<I", raw, 0x28)

    area = None                                     # set by tables()

    @property
    def cls(self):
        return (OVERLAY_CLASSES.get((self.area, self.behaviour)) or
                CLASSES.get(self.behaviour) or ("b%06X" % self.behaviour, None))

    @property
    def model_slot(self):
        """(slot, index or None) of the model, where the code says it; else None."""
        rule = self.cls[1]
        return rule(self) if rule else None

    @property
    def name(self):
        cls = self.cls[0]
        return "%s_t%02X_m%02X_%06X" % (cls, self.type & 0xFF, self.model & 0xFF,
                                        self.va & 0xFFFFFF)

    def matrix(self):
        """T * Rz * Ry * Rx as a row-major list of 16 (column vectors)."""
        (cx, cy, cz), (sx, sy, sz) = ([math.cos(a) for a in self.rot],
                                      [math.sin(a) for a in self.rot])
        rx = [1, 0, 0, 0, 0, cx, -sx, 0, 0, sx, cx, 0, 0, 0, 0, 1]
        ry = [cy, 0, sy, 0, 0, 1, 0, 0, -sy, 0, cy, 0, 0, 0, 0, 1]
        rz = [cz, -sz, 0, 0, sz, cz, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        m = ext_mesh.matmul(rz, ext_mesh.matmul(ry, rx))
        m[3], m[7], m[11] = self.pos
        return m


def tables(mem, area, rooms):
    """{room: [(table address, [Spawn])]} for one area of `rooms` rooms (the
    room table has no terminator: the count is the index's)."""
    rooms_va = mem.u32(AREA_TABLE + 4 * area)
    out = {}
    if not rooms_va:
        return out
    for room in range(rooms):
        lst = mem.u32(rooms_va + 4 * room)
        out[room] = []
        while True:
            t = mem.u32(lst)
            if not t:
                break
            recs, a = [], t
            while struct.unpack("<H", mem.read(a, 2))[0] != 0xFFFF:
                recs.append(Spawn(mem.read(a, RECORD), a))
                recs[-1].area = area
                a += RECORD
            out[room].append((t, recs))
            lst += 4
    return out


class Slots:
    """table[slot] for one room, filled as the loader fills it."""

    def __init__(self, f, records, room_rec):
        main = next(r for r in records if r.section == room_rec.section and r.sub < 0)
        order = [room_rec] + ([main] if main is not room_rec else [])
        order += [r for sec in RESIDENT_SECTIONS for r in records
                  if r.section == sec and r.sub < 0]
        self.res = {}
        for r in order:
            for label, data in ext_tex.resources(f, r).items():
                self.res.setdefault(int(label[4:], 16), data)
        self.objs = {}

    def objects(self, slot):
        if slot not in self.objs:
            data = self.res.get(slot)
            try:
                self.objs[slot] = ext_mesh.objects(data) if data else []
            except Exception:
                self.objs[slot] = []
        return self.objs[slot]


def export_room(f, records, rooms, area, room, path, resident_gs):
    """Room geometry and every actor that has a mesh; the rest as empties.
    Returns (actors, with a mesh)."""
    room_rec = next((r for r in records if r.section == area + 4 and r.sub == room), None)
    if room_rec is None:                                # areas with no rooms
        room_rec = next(r for r in records if r.section == area + 4 and r.sub < 0)
    slots = Slots(f, records, room_rec)
    mem_gs = ext_tex.contexts(f, room_rec, records, resident_gs)[0]
    doc = ext_mesh.Gltf(path, mem_gs)
    doc.node({"name": room_rec.name, "mesh": doc.mesh("geometry", slots.objects(0x44))})
    cache, n, placed = {}, 0, 0
    for t, recs in rooms.get(room, []):
        for s in recs:
            n += 1
            tr, q = ext_anim.to_trs(s.matrix())
            node = {"name": s.name, "translation": tr, "rotation": q}
            ms = s.model_slot
            if ms:
                objs = slots.objects(ms[0])
                if ms[1] is not None:
                    objs = objs[ms[1]:ms[1] + 1]
                if objs:
                    if ms not in cache:
                        cache[ms] = doc.mesh("slot%02X_%s" % (ms[0], "all" if ms[1] is None
                                                               else "%02X" % ms[1]), objs)
                    if cache[ms] is not None:
                        node["mesh"] = cache[ms]
                        placed += 1
            doc.node(node)
    doc.save()
    return n, placed


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exe")
    ap.add_argument("overlay", help="the area's overlay, or the OVERLAY directory with --all")
    ap.add_argument("idx")
    ap.add_argument("--area", type=int)
    ap.add_argument("--room", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dat")
    ap.add_argument("--gltf")
    ap.add_argument("--all", metavar="DIR", help="export every room of every area")
    a = ap.parse_args()
    exe = elf.Elf(a.exe)
    records = ext_index.load(a.idx)

    def area_rooms(area, overlay):
        main_rec = next(r for r in records if r.section == area + 4 and r.sub < 0)
        mem = Memory(exe, mwo3.Overlay(open(overlay, "rb").read()))
        return tables(mem, area, max(main_rec.subrecords, 1))

    if a.all:
        with open(a.dat, "rb") as f:
            resident_gs = ext_tex.resident(f, records)
            for area in range(23):
                ov = os.path.join(a.overlay, "AREA%02d.BIN" % OVERLAY_OF_AREA.get(area, area))
                if area in OVERLAY_OF_AREA or not os.path.exists(ov):
                    continue
                rooms = area_rooms(area, ov)
                for room in rooms:
                    name = "area%02d_room%d" % (area, room)
                    path = os.path.join(a.all, name, name + ".gltf")
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    n, placed = export_room(f, records, rooms, area, room, path, resident_gs)
                    print("%s: %d actors, %d with a mesh" % (name, n, placed))
        return
    rooms = area_rooms(a.area, a.overlay)
    if a.list:
        for room, tbls in rooms.items():
            for t, recs in tbls:
                print("room %d: table %08X, %d records" % (room, t, len(recs)))
                for s in recs:
                    print("  %08X c%d p%04X type %02X +03=%02X +2E=%02X model %02X %04X %04X %04X"
                          " pos (%7.1f %6.1f %7.1f) rot (%5.2f %5.2f %5.2f) %08X %s" % (
                              (s.va, s.condition, s.p, s.type, s.a03, s.a2e, s.model, s.param,
                               s.p54, s.p56) + s.pos + s.rot + (s.behaviour, s.name.split("_")[0])))
    if a.gltf:
        with open(a.dat, "rb") as f:
            n, placed = export_room(f, records, rooms, a.area, a.room, a.gltf,
                                    ext_tex.resident(f, records))
        print("%d actors, %d with a mesh" % (n, placed))


if __name__ == "__main__":
    main()
