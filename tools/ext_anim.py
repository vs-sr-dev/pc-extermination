#!/usr/bin/env python3
"""Decode Extermination's skeletal animations; export skinned characters.

    python tools/ext_anim.py IDX DAT --record s28 --slot 3A --list
    python tools/ext_anim.py IDX DAT --record s28 --slot 3A \\
        --mesh s28:39 --gltf out/body.gltf [--anims 0-20] [--bind 0]

An animation set is a resource `u32 n, u32 offset[n]`, one animation each
(some sets hold other entries too; they are skipped). An animation:

    +00 u16 bones   +02 u16 frames
    +04 u16 at the end: 0xFFFF loop, 0xFFFE hold, else the animation to chain to
    +06 u16 frames of the blend into the chained animation
    +08 u32 rotations   +0C u32 translations   +10 u32 scales   (offsets)
    +14 u32 events (offset, 0 if none): u16 count, then {u16 frame, u16 flags}
    +18 8 bytes 0
    +20 i32 parent[bones]        -1 for the root; parents come first

Each of the three blocks is `u32 offset[bones]` (from the block start), one
key track per bone. A key is 12 bytes: 80 bits of packed values, then u16
frame; frame 0xFFFF ends the track. The values are small floats with the
IEEE layout and bias 127, packed from bit 0 up:

    rotation      4 x 20 bits (sign, 8 exponent, 11 mantissa): quaternion x, y, z, w
    translation   3 x 26 bits (sign, 8 exponent, 17 mantissa), 2 bits unused
    scale         3 x 26 bits

A bone's local transform is T * R * S relative to its parent; translations
put a child at the end of its parent (bone lengths lie along x). The game
builds row-vector matrices (the VU0 library's convention), so in the usual
column-vector terms the stored quaternion is the conjugate: Animation keeps
(-x, -y, -z, w). Character space has y up, feet on the root (the squad's
hips sit 10.9 units above it), like the world. Keys are
sparse: every track has keys on frame 0 and the last two frames, and the
rest where the motion needs them; values in between are interpolated.

Meshes bind to bones vertex by vertex: w's low mantissa bits hold bone * 8,
and positions and normals are local to that bone (see ext_mesh.py). The
object header's word at +08 is the skeleton's bone count.
"""
import argparse
import math
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import ext_index  # noqa: E402
import ext_mesh  # noqa: E402
import ext_tex  # noqa: E402
from ext_mesh import apply, matmul  # noqa: E402

LAYOUT = ((4, 20), (3, 26), (3, 26))      # rotation, translation, scale


def unpack_float(v, mbits):
    e = v >> mbits & 0xFF
    if e == 0:
        return 0.0
    f = (1 + (v & (1 << mbits) - 1) / (1 << mbits)) * 2.0 ** (e - 127)
    return -f if v >> (mbits + 8) & 1 else f


class Animation:
    def __init__(self, buf, off):
        (self.bones, self.frames, self.loop, self.blend, *blocks,
         self.events) = struct.unpack_from("<4H4I", buf, off)
        self.parents = struct.unpack_from("<%di" % self.bones, buf, off + 0x20)
        self.tracks = []          # [rotation, translation, scale][bone] -> [(frame, values)]
        for start, (comps, width) in zip(blocks, LAYOUT):
            base = off + start
            per_bone = []
            for t in struct.unpack_from("<%dI" % self.bones, buf, base):
                p, keys = base + t, []
                while True:
                    frame, = struct.unpack_from("<H", buf, p + 10)
                    if frame == 0xFFFF:
                        break
                    bits = int.from_bytes(buf[p:p + 10], "little")
                    mask = (1 << width) - 1
                    v = tuple(unpack_float(bits >> width * i & mask, width - 9) for i in range(comps))
                    if comps == 4:            # row-vector quaternion -> column-vector
                        v = (-v[0], -v[1], -v[2], v[3])
                    keys.append((frame, v))
                    p += 12
                per_bone.append(keys)
            self.tracks.append(per_bone)

    def sample(self, kind, bone, frame):
        """Value of a track at a frame: linear between keys (nlerp for rotations)."""
        keys = self.tracks[kind][bone]
        if frame <= keys[0][0]:
            return keys[0][1]
        for (f0, a), (f1, b) in zip(keys, keys[1:]):
            if f0 <= frame <= f1:
                u = (frame - f0) / (f1 - f0)
                if kind == 0 and sum(x * y for x, y in zip(a, b)) < 0:
                    b = tuple(-x for x in b)
                v = tuple(x + (y - x) * u for x, y in zip(a, b))
                if kind == 0:
                    n = math.sqrt(sum(x * x for x in v)) or 1.0
                    v = tuple(x / n for x in v)
                return v
        return keys[-1][1]

    def pose(self, frame):
        """World matrices (4x4, row-major lists) of every bone at a frame."""
        world = []
        for b in range(self.bones):
            m = trs(self.sample(1, b, frame), self.sample(0, b, frame), self.sample(2, b, frame))
            p = self.parents[b]
            world.append(m if p < 0 else matmul(world[p], m))
        return world


def is_animation(buf, off):
    if off + 0x20 > len(buf):
        return False
    bones, _, _, _, rot, trans, scale = struct.unpack_from("<4H3I", buf, off)
    return 0 < bones < 256 and rot == 0x20 + 4 * bones and rot < trans < scale < len(buf) - off


def animations(buf):
    """{index: Animation} of an animation set (or of a single animation)."""
    if is_animation(buf, 0):
        return {0: Animation(buf, 0)}
    n, = struct.unpack_from("<I", buf, 0)
    if not 0 < n < 0x10000 or 4 + 4 * n > len(buf):
        return {}
    offs = struct.unpack_from("<%dI" % n, buf, 4)
    return {i: Animation(buf, o) for i, o in enumerate(offs) if is_animation(buf, o)}


# --- 4x4 matrices as row-major lists of 16 floats

def trs(t, q, s):
    x, y, z, w = q
    r = [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
         2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
         2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]
    return [r[0] * s[0], r[1] * s[1], r[2] * s[2], t[0],
            r[3] * s[0], r[4] * s[1], r[5] * s[2], t[1],
            r[6] * s[0], r[7] * s[1], r[8] * s[2], t[2],
            0.0, 0.0, 0.0, 1.0]


def rigid_inverse(m):
    """Inverse of a rotation + translation matrix (scales are 1 in the bind pose)."""
    r = [m[0], m[4], m[8], m[1], m[5], m[9], m[2], m[6], m[10]]
    t = (m[3], m[7], m[11])
    return [r[0], r[1], r[2], -(r[0] * t[0] + r[1] * t[1] + r[2] * t[2]),
            r[3], r[4], r[5], -(r[3] * t[0] + r[4] * t[1] + r[5] * t[2]),
            r[6], r[7], r[8], -(r[6] * t[0] + r[7] * t[1] + r[8] * t[2]),
            0.0, 0.0, 0.0, 1.0]


def to_trs(m):
    """Translation and quaternion of a rotation + translation matrix."""
    tr = m[0] + m[5] + m[10]
    if tr > 0:
        k = 2 * math.sqrt(1 + tr)
        q = ((m[9] - m[6]) / k, (m[2] - m[8]) / k, (m[4] - m[1]) / k, k / 4)
    elif m[0] > m[5] and m[0] > m[10]:
        k = 2 * math.sqrt(1 + m[0] - m[5] - m[10])
        q = (k / 4, (m[1] + m[4]) / k, (m[2] + m[8]) / k, (m[9] - m[6]) / k)
    elif m[5] > m[10]:
        k = 2 * math.sqrt(1 + m[5] - m[0] - m[10])
        q = ((m[1] + m[4]) / k, k / 4, (m[6] + m[9]) / k, (m[2] - m[8]) / k)
    else:
        k = 2 * math.sqrt(1 + m[10] - m[0] - m[5])
        q = ((m[2] + m[8]) / k, (m[6] + m[9]) / k, k / 4, (m[4] - m[1]) / k)
    return (m[3], m[7], m[11]), q


def export_skinned(path, mem, objs, anims, fps, bind=None, name="character"):
    """glTF with the objects skinned to their skeleton and one glTF animation
    per entry of `anims` ({label: Animation}). The bind pose is the model's
    rest pose, or frame 0 of `bind` if given."""
    doc = ext_mesh.Gltf(path, mem)
    g = doc.g
    if bind is None:
        parents = [p for p, _ in objs[0].skeleton]
        local = [m for _, m in objs[0].skeleton]
        world = objs[0].rest_pose()
        trs_ = [to_trs(m) + ((1.0, 1.0, 1.0),) for m in local]
    else:
        parents = bind.parents
        world = bind.pose(0)
        trs_ = [(bind.sample(1, b, 0), bind.sample(0, b, 0), bind.sample(2, b, 0))
                for b in range(bind.bones)]
    nb = len(parents)
    first = len(g["nodes"])
    for b, (t, q, s) in enumerate(trs_):
        g["nodes"].append({"name": "bone%02d" % b, "translation": list(t),
                           "rotation": list(q), "scale": list(s)})
    for b in range(nb):
        kids = [first + c for c in range(nb) if parents[c] == b]
        if kids:
            g["nodes"][first + b]["children"] = kids
    roots = [first + b for b in range(nb) if parents[b] < 0]
    g["scenes"][0]["nodes"] += roots
    ibm = []
    for m in world:
        inv = rigid_inverse(m)
        ibm += [inv[4 * r + c] for c in range(4) for r in range(4)]      # column-major
    skin = {"joints": list(range(first, first + nb)),
            "inverseBindMatrices": doc.add(ibm, 16, kind="MAT4"), "skeleton": roots[0]}
    g["skins"] = [skin]
    mesh = doc.mesh(name, objs, pose=lambda b, v, w: apply(world[b], v, w))
    doc.node({"name": name, "mesh": mesh, "skin": 0})
    g["animations"] = []
    for label, a in anims.items():
        if a.bones != nb:
            continue
        samplers, channels = [], []
        for kind, path_ in enumerate(("rotation", "translation", "scale")):
            for b in range(nb):
                keys = a.tracks[kind][b]
                times = [f / fps for f, _ in keys]
                vals = []
                for _, v in keys:
                    vals += v
                samplers.append({"input": doc.add(times, 1, minmax=True),
                                 "output": doc.add(vals, len(keys[0][1])),
                                 "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1,
                                 "target": {"node": first + b, "path": path_}})
        g["animations"].append({"name": label, "samplers": samplers, "channels": channels})
    doc.save()


def parse_range(s, n):
    if not s:
        return list(range(n))
    out = []
    for part in s.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--record", required=True, help="record holding the animation set")
    ap.add_argument("--slot", required=True, help="hex slot of the animation set")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--mesh", help="record:slot[:entry] of the model, e.g. s28:39")
    ap.add_argument("--gltf")
    ap.add_argument("--anims", help="animations to export, e.g. 0-20,40 (default all)")
    ap.add_argument("--bind", type=int, help="animation whose frame 0 is the bind pose "
                    "(default: the model's rest pose)")
    ap.add_argument("--fps", type=float, default=50.0,
                    help="animation frames per second (one per game tick; 50 assumed)")
    ap.add_argument("--variant", type=lambda v: int(v, 0), default=7,
                    help="section 3 slot for the character page (6-10)")
    a = ap.parse_args()
    records = ext_index.load(a.idx)
    by_name = {r.name: r for r in records}
    with open(a.dat, "rb") as f:
        res = ext_tex.resources(f, by_name[a.record])
        anims = animations(res["slot%s" % a.slot.upper().zfill(2)])
        if a.list:
            for i, an in anims.items():
                moving = sum(len(k) > 3 for kind in an.tracks for k in kind)
                print("%3d: %2d bones, %4d frames, loop %04X, %3d moving tracks" % (
                    i, an.bones, an.frames, an.loop, moving))
        if a.gltf:
            rec, slot, *entry = a.mesh.split(":")
            buf = ext_tex.resources(f, by_name[rec])["slot%s" % slot.upper().zfill(2)]
            objs = ext_mesh.objects(buf)
            if entry:
                objs = [objs[int(entry[0])]]
            mem = ext_tex.contexts(f, by_name[rec], records,
                                   ext_tex.resident(f, records, a.variant))[0]
            pick = parse_range(a.anims, max(anims) + 1)
            export_skinned(a.gltf, mem, objs,
                           {"anim%03d" % i: anims[i] for i in pick if i in anims}, a.fps,
                           None if a.bind is None else anims[a.bind],
                           name="%s_%s" % (rec, slot))


if __name__ == "__main__":
    main()
