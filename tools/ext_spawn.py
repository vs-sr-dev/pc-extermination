#!/usr/bin/env python3
"""Read Extermination's actor spawn tables; place a room's actors in glTF.

    python tools/ext_spawn.py SCES_502.40 OVERLAY/AREA00.BIN IDX --area 0 --list
    python tools/ext_spawn.py SCES_502.40 OVERLAY/AREA00.BIN IDX --area 0 --room 0 \\
        --dat DAT --gltf out/room.gltf

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
model: 0x001B1590 takes table[0x35][model] (the resident models of section
27), 0x001B1670 takes table[0x43][model] (the room's props). Pickups
(0x0015AFB0) use the room's props when (+0x03 & 0xF) == 1; the container
behaviour 0x0021A0D0 when +0x03 == 0 and +0x2E == 0x28. Other classes are
exported as empties named after their fields.
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
BEHAVIOURS = {0x0015AFB0: "pickup", 0x0021A0D0: "container", 0x00128C00: "human",
              0x0012A5C0: "human2", 0x001E4720: "debris", 0x0015AB10: "debris2",
              0x001551B0: "prop04"}


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

    @property
    def model_slot(self):
        """(slot, index) of the model, where the code says it; else None."""
        m = self.model & 0xFF
        if self.behaviour == 0x0015AFB0:
            return (0x43 if self.a03 & 0xF == 1 else 0x35), m
        if self.behaviour == 0x0021A0D0:
            return (0x43 if self.a03 == 0 and self.a2e == 0x28 else 0x35), m
        return None

    @property
    def name(self):
        return "%s_t%02X_m%02X_%06X" % (BEHAVIOURS.get(self.behaviour, "b%06X" % self.behaviour),
                                        self.type & 0xFF, self.model & 0xFF, self.va & 0xFFFFFF)

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
                a += RECORD
            out[room].append((t, recs))
            lst += 4
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("exe")
    ap.add_argument("overlay")
    ap.add_argument("idx")
    ap.add_argument("--area", type=int, required=True)
    ap.add_argument("--room", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dat")
    ap.add_argument("--gltf")
    a = ap.parse_args()
    mem = Memory(elf.Elf(a.exe), mwo3.Overlay(open(a.overlay, "rb").read()))
    records = ext_index.load(a.idx)
    main_rec = next(r for r in records if r.section == a.area + 4 and r.sub < 0)
    rooms = tables(mem, a.area, main_rec.subrecords)
    if a.list:
        for room, tbls in rooms.items():
            for t, recs in tbls:
                print("room %d: table %08X, %d records" % (room, t, len(recs)))
                for s in recs:
                    print("  %08X c%d p%04X type %02X +03=%02X +2E=%02X model %02X %04X %04X %04X"
                          " pos (%7.1f %6.1f %7.1f) rot (%5.2f %5.2f %5.2f) %08X" % (
                              (s.va, s.condition, s.p, s.type, s.a03, s.a2e, s.model, s.param,
                               s.p54, s.p56) + s.pos + s.rot + (s.behaviour,)))
    if a.gltf:
        room_rec = next(r for r in records if r.section == a.area + 4 and r.sub == a.room)
        resident = next(r for r in records if r.section == ext_tex.RESIDENT_SECTION and r.sub < 0)
        with open(a.dat, "rb") as f:
            res = ext_tex.resources(f, room_rec)
            res35 = ext_tex.resources(f, resident)["slot35"]
            mem_gs = ext_tex.contexts(f, room_rec, records, ext_tex.resident(f, records))[0]
        doc = ext_mesh.Gltf(a.gltf, mem_gs)
        room_node = {"name": room_rec.name, "mesh": doc.mesh("geometry", ext_mesh.objects(res["slot44"]))}
        doc.node(room_node)
        models = {0x43: ext_mesh.objects(res["slot43"]), 0x35: ext_mesh.objects(res35)}
        cache = {}
        for t, recs in rooms.get(a.room, []):
            for s in recs:
                tr, q = ext_anim.to_trs(s.matrix())
                node = {"name": s.name, "translation": tr, "rotation": q}
                ms = s.model_slot
                if ms and ms[1] < len(models[ms[0]]):
                    if ms not in cache:
                        cache[ms] = doc.mesh("slot%02X_%02X" % ms, [models[ms[0]][ms[1]]])
                    if cache[ms] is not None:
                        node["mesh"] = cache[ms]
                doc.node(node)
        doc.save()


if __name__ == "__main__":
    main()
