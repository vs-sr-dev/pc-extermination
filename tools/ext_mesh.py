#!/usr/bin/env python3
"""Decode Extermination's meshes and export them to glTF.

    python tools/ext_mesh.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT \\
        --record s04_r0 --gltf out/s04_r0.gltf [--slots 43,44,72]
    python tools/ext_mesh.py ... --record s04_r0 --stats

A mesh resource is either one object or a table of them:

    u32 count, u32 offset[count]         (offsets from the resource start)

Not every entry of a table is an object: entry 0 of the room geometry
(slot 0x44) is a 32 x 32 grid descriptor, not decoded yet.

An object is a 0x30-byte header and a VIF1 packet for the VU1 microcode:

    +00 u32 batches   +04 u32 qwc (VIF stream, qwords)
    +08 u32 bones (the table size for room geometry)
    +0C u32 offset of the rest skeleton = 0x40 + qwc * 16  +10 u32 0 (3: 11-qword vertices)
    +14 f32 min x, y, z   +20 f32 ? (a radius or distance)   +24 f32 max x, y, z
    +30 VIF: per batch NOP/MSCAL/MSCNT, NOPs, STCYCL 4,4, then one or two
             UNPACK V4-32 of 32 vertices, then a last MSCNT. The
             MSCAL/MSCNT that follows a batch runs it. Most objects use 4
             qwords per vertex (128 qwords a batch); characters use 11
             (352 qwords, sent as UNPACKs of 256 + 96): the same 4 qwords
             and 7 zero ones, workspace for the microprogram. Character
             positions are small, local to a bone.

A vertex, as unpacked into VU memory:

    qw0  u64 TEX0 of the texture (0: untextured), u64 0
    qw1  f32 s, t, q, 0
    qw2  f32 normal x, y, z, 0
    qw3  f32 x, y, z, w; w is +-1 with flags in the low mantissa bits:
         0x8000 no triangle ends here (strip start, like the GS ADC bit),
         the sign (with 0x4000) gives the triangle's winding; bits 3-12
         hold bone * 8. Positions and normals are local to that bone.

Vertices form triangle strips; every vertex without the 0x8000 flag closes a
triangle with the two before it. Batches pad with repeats of the last vertex.
"""
import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ps2kit import gs, gsmem, vif  # noqa: E402
import ext_index  # noqa: E402
import ext_tex  # noqa: E402

HEADER = 0x30
FLAG_NOKICK, FLAG_SIDE = 0x8000, 0x4000


class Object:
    def __init__(self, buf, off):
        (self.batches, self.qwc, self.kind, self.size, _) = struct.unpack_from("<5I", buf, off)
        vals = struct.unpack_from("<7f", buf, off + 0x14)
        self.bbox, self.radius = (vals[0:3], vals[4:7]), vals[3]
        self.skeleton = skeleton(buf, off, self.kind, self.size)
        self.vertices = []        # (tex0, (s,t,q), (nx,ny,nz), (x,y,z), wbits)
        self.batch_sizes = []
        end = off + HEADER + 16 * self.qwc
        pending = b""
        for c in vif.walk(buf, off + HEADER, end):
            if c.is_unpack:
                pending += c.data
            elif c.cmd in (0x14, 0x15, 0x17) and pending:     # MSCAL/MSCALF/MSCNT
                self._batch(pending)
                pending = b""
        if pending:
            self._batch(pending)

    def _batch(self, vecs):
        qw = len(vecs) // 16
        stride = qw // 32 if qw % 32 == 0 else 4          # 4 qwords, or 11 when skinned
        n = qw // stride
        self.batch_sizes.append(n)
        for k in range(n):
            v = 16 * stride * k
            tex0, = struct.unpack_from("<Q", vecs, v)
            stq = struct.unpack_from("<3f", vecs, v + 16)
            nrm = struct.unpack_from("<3f", vecs, v + 32)
            pos = struct.unpack_from("<3f", vecs, v + 48)
            wbits, = struct.unpack_from("<I", vecs, v + 60)
            self.vertices.append((tex0, stq, nrm, pos, wbits))

    def rest_pose(self):
        """World matrix of each bone in the rest pose (identity if none)."""
        world = []
        for parent, m in self.skeleton:
            world.append(m if parent < 0 else matmul(world[parent], m))
        return world

    def triangles(self):
        """Yield (i, j, k) vertex indices, batch by batch, as the strips say."""
        base = 0
        for n in self.batch_sizes:
            for i in range(base + 2, base + n):
                w = self.vertices[i][4]
                if w & FLAG_NOKICK:
                    continue
                if w >> 31:
                    yield i - 1, i - 2, i
                else:
                    yield i - 2, i - 1, i
            base += n


def skeleton(buf, off, bones, size):
    """The rest skeleton after an object's VIF data, or [] (room geometry
    has none: its +08 word is a table size).

    At object + size, one 0x50-byte record per bone: u32 index, i32 parent
    (-1 for the root), 8 bytes 0, then the bone's local 4x4 matrix in the
    VU0 library's row-vector layout (translation in the last row). Returned
    as (parent, column-vector matrix as a row-major list of 16)."""
    base = off + size
    if not 0 < bones < 256 or base + 0x50 * bones > len(buf):
        return []
    out = []
    for k in range(bones):
        index, parent = struct.unpack_from("<Ii", buf, base + 0x50 * k)
        if index != k or not -1 <= parent < k:
            return []
        m = struct.unpack_from("<16f", buf, base + 0x50 * k + 0x10)
        out.append((parent, [m[4 * c + r] for r in range(4) for c in range(4)]))
    return out


def matmul(a, b):
    """4x4 matrices as row-major lists of 16 floats."""
    return [sum(a[4 * i + k] * b[4 * k + j] for k in range(4)) for i in range(4) for j in range(4)]


def apply(m, v, w):
    """m * (v, w), the first three components."""
    return tuple(m[4 * i] * v[0] + m[4 * i + 1] * v[1] + m[4 * i + 2] * v[2] + m[4 * i + 3] * w
                 for i in range(3))


def is_object(buf, off=0):
    if off + HEADER > len(buf):
        return False
    b, qwc, _, size = struct.unpack_from("<4I", buf, off)
    return 0 < b < 4096 and size == 0x40 + 16 * qwc and off + HEADER + 16 * qwc <= len(buf)


def objects(buf):
    """The objects of a mesh resource (one object or a table of them)."""
    if is_object(buf):
        return [Object(buf, 0)]
    n, = struct.unpack_from("<I", buf, 0)
    if not 0 < n < 0x10000 or 4 + 4 * n > len(buf):
        return []
    offs = struct.unpack_from("<%dI" % n, buf, 4)
    if not all(o < len(buf) for o in offs):
        return []
    found = [Object(buf, o) for o in offs if is_object(buf, o)]
    return found if len(found) * 2 > n else []


def winding_check(objs):
    """How many triangles face the way their vertex normals do."""
    agree = total = 0
    for o in objs:
        V = o.vertices
        for i, j, k in o.triangles():
            a, b, c = V[i][3], V[j][3], V[k][3]
            u = [b[x] - a[x] for x in range(3)]
            v = [c[x] - a[x] for x in range(3)]
            n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            vn = [V[i][2][x] + V[j][2][x] + V[k][2][x] for x in range(3)]
            d = sum(n[x] * vn[x] for x in range(3))
            if d:
                total += 1
                agree += d > 0
    return agree, total


def has_normals(o):
    """Room geometry carries vertex colours (0-1) where props carry normals."""
    lens = [sum(c * c for c in v[2]) for v in o.vertices if any(v[2])]
    return bool(lens) and sum(abs(x - 1) < 0.05 for x in lens) * 2 > len(lens)


class Gltf:
    """A glTF 2.0 document under construction: buffers, textures from GS
    memory, meshes; save() writes the .gltf, its .bin and the PNGs."""

    def __init__(self, path, mem):
        self.path, self.mem = path, mem
        self.out_dir = os.path.dirname(os.path.abspath(path))
        self.stem = os.path.splitext(os.path.basename(path))[0]
        os.makedirs(os.path.join(self.out_dir, self.stem + "_tex"), exist_ok=True)
        self.blob = bytearray()
        self.g = {"asset": {"version": "2.0", "generator": "pc-extermination"},
                  "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                  "materials": [], "textures": [], "images": [], "samplers": [
                      {"magFilter": 9729, "minFilter": 9729, "wrapS": 10497, "wrapT": 10497}],
                  "accessors": [], "bufferViews": [], "buffers": []}
        self.materials = {}

    def material(self, tex0):
        g = self.g
        key = tex0 & ((1 << 34) - 1) | tex0 & (0x7FFFFFF << 37) if tex0 else 0
        if key in self.materials:
            return self.materials[key]
        m = {"name": "untextured", "doubleSided": False,
             "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0}}
        if key:
            t = gsmem.Tex0(tex0)
            name = ext_tex.name(t)
            rgba = self.mem.texture(t, tcc=1)
            rel = "%s_tex/%s.png" % (self.stem, name)
            gs.write_png(os.path.join(self.out_dir, rel), t.w, t.h, rgba)
            g["images"].append({"uri": rel})
            g["textures"].append({"sampler": 0, "source": len(g["images"]) - 1})
            m["name"] = name
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(g["textures"]) - 1}
            if any(rgba[i] < 255 for i in range(3, len(rgba), 4)):
                m["alphaMode"] = "MASK"
                m["alphaCutoff"] = 0.5
        g["materials"].append(m)
        self.materials[key] = len(g["materials"]) - 1
        return self.materials[key]

    def add(self, values, comps, target=None, minmax=False, ctype=5126, kind=None):
        """Append a float (or ctype) accessor of `comps` components."""
        g, blob = self.g, self.blob
        fmt = {5126: "f", 5121: "B", 5123: "H"}[ctype]
        data = struct.pack("<%d%s" % (len(values), fmt), *values)
        while len(blob) % 4:
            blob.append(0)
        view = {"buffer": 0, "byteOffset": len(blob), "byteLength": len(data)}
        if target:
            view["target"] = target
        blob.extend(data)
        g["bufferViews"].append(view)
        acc = {"bufferView": len(g["bufferViews"]) - 1, "componentType": ctype,
               "count": len(values) // comps,
               "type": kind or {1: "SCALAR", 2: "VEC2", 3: "VEC3", 4: "VEC4"}[comps]}
        if minmax:
            acc["min"] = [min(values[i::comps]) for i in range(comps)]
            acc["max"] = [max(values[i::comps]) for i in range(comps)]
        g["accessors"].append(acc)
        return len(g["accessors"]) - 1

    def mesh(self, name, objs, pose=None):
        """Add a glTF mesh of the objects; None if it has no triangles.

        pose(bone, (x, y, z), w) -> (x, y, z) moves bone-local positions (and
        normals, with w = 0) into place and turns on JOINTS_0/WEIGHTS_0.
        Without it, objects with more than one bone are put in their rest
        pose."""
        groups = {}               # (material, has normals) -> pos, nrm, uv, col, joints
        for o in objs:
            normals = has_normals(o)
            V = o.vertices
            rest = o.rest_pose() if not pose and len(o.skeleton) > 1 else None
            for tri in o.triangles():
                mat = self.material(V[tri[2]][0])
                p, n, uv, col, jt = groups.setdefault((mat, normals), ([], [], [], [], []))
                for i in tri:
                    tex0, stq, q2, pos, wbits = V[i]
                    if pose:
                        bone = bone_of(wbits)
                        pos, q2 = pose(bone, pos, 1.0), pose(bone, q2, 0.0)
                        jt.append(bone)
                    elif rest:
                        m = rest[bone_of(wbits)]
                        pos, q2 = apply(m, pos, 1.0), apply(m, q2, 0.0) if normals else q2
                    p += pos
                    q = stq[2] or 1.0
                    uv += [stq[0] / q, stq[1] / q]
                    if normals:
                        n += q2
                    else:
                        col += [min(q2[0], 1.0), min(q2[1], 1.0), min(q2[2], 1.0), 1.0]
        prims = []
        for (mat, normals), (p, n, uv, col, jt) in groups.items():
            attrs = {"POSITION": self.add(p, 3, 34962, True),
                     "TEXCOORD_0": self.add(uv, 2, 34962)}
            if normals:
                attrs["NORMAL"] = self.add(n, 3, 34962)
            else:
                attrs["COLOR_0"] = self.add(col, 4, 34962)
            if jt:
                attrs["JOINTS_0"] = self.add([x for j in jt for x in (j, 0, 0, 0)], 4,
                                             34962, ctype=5121)
                attrs["WEIGHTS_0"] = self.add([x for _ in jt for x in (1.0, 0, 0, 0)], 4, 34962)
            prims.append({"attributes": attrs, "material": mat, "mode": 4})
        if not prims:
            return None
        self.g["meshes"].append({"name": name, "primitives": prims})
        return len(self.g["meshes"]) - 1

    def node(self, node, root=True):
        self.g["nodes"].append(node)
        k = len(self.g["nodes"]) - 1
        if root:
            self.g["scenes"][0]["nodes"].append(k)
        return k

    def save(self):
        g = self.g
        bin_name = self.stem + ".bin"
        with open(os.path.join(self.out_dir, bin_name), "wb") as fb:
            fb.write(self.blob)
        g["buffers"].append({"uri": bin_name, "byteLength": len(self.blob)})
        for k in ("textures", "images"):
            if not g[k]:
                del g[k]
        with open(self.path, "w") as fj:
            json.dump(g, fj)


def bone_of(wbits):
    """The bone a vertex belongs to: w's low mantissa bits hold bone * 8."""
    return (wbits & 0x1FFF) >> 3


def export_gltf(path, meshes, mem, split=False):
    """Write a glTF 2.0 file (+ .bin + PNGs) with one node per mesh slot.

    Primitives are grouped by TEX0; textures are rendered from GS memory in
    GS row order, so the vertex s,t map straight onto glTF UVs. The game's
    world is y up like glTF's, so coordinates go through unchanged."""
    doc = Gltf(path, mem)
    for label, objs in meshes.items():
        parent = {"name": label, "children": []}
        doc.node(parent)
        if split:
            for k, o in enumerate(objs):
                m = doc.mesh("%s_%03d" % (label, k), [o])
                if m is not None:
                    parent["children"].append(doc.node(
                        {"name": "%s_%03d" % (label, k), "mesh": m}, root=False))
        else:
            m = doc.mesh(label, objs)
            if m is not None:
                parent["mesh"] = m
        if not parent["children"]:
            del parent["children"]
    doc.save()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("idx")
    ap.add_argument("dat")
    ap.add_argument("--record", required=True)
    ap.add_argument("--slots", help="comma-separated hex slots (default: all meshes)")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--gltf")
    ap.add_argument("--split", action="store_true", help="one glTF node per object")
    ap.add_argument("--variant", type=lambda v: int(v, 0), default=7,
                    help="section 3 slot for the character page (6-10)")
    a = ap.parse_args()
    records = ext_index.load(a.idx)
    r = next(x for x in records if x.name == a.record)
    with open(a.dat, "rb") as f:
        res = ext_tex.resources(f, r)
        meshes = {}
        for label, data in sorted(res.items()):
            if a.slots and label[4:].upper() not in {s.upper().zfill(2) for s in a.slots.split(",")}:
                continue
            objs = objects(data)
            if objs:
                meshes[label] = objs
        if a.stats:
            for label, objs in meshes.items():
                nv = sum(len(o.vertices) for o in objs)
                nt = sum(1 for o in objs for _ in o.triangles())
                kinds = sorted({o.kind for o in objs})
                ag, tot = winding_check(objs)
                print("%s: %d objects, %d vertices, %d triangles, kinds %s, winding agrees %d/%d" % (
                    label, len(objs), nv, nt, kinds, ag, tot))
        if a.gltf:
            base = ext_tex.resident(f, records, a.variant)
            mem = ext_tex.contexts(f, r, records, base)[0]
            export_gltf(a.gltf, meshes, mem, split=a.split)


if __name__ == "__main__":
    main()
