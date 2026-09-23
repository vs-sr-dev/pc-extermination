"""Scan a PS2 disc tree and report what is recognised.

    python -m ps2kit.fingerprint E:/
    python -m ps2kit.fingerprint build/disc --deep

This is the first step of every new title: before reading any code, find out
which parts of the disc are standard (SDK movies, SPU audio, IOP modules,
overlays) and which are the game's own containers that need real work.

Per file it identifies by magic and by structure; for executables it also
reports the compiler, the SDK libraries linked in and the files the code names
by path. With --deep, large unknown files are sampled at every 2048-byte
sector for known magics, which is how container formats usually give
themselves away.
"""
import argparse
import collections
import math
import os
import re
import struct

from . import adpcm

SECTOR = 2048

# magic -> label; checked at offset 0 (and at sector starts with --deep)
MAGICS = [
    (b"\x7fELF", "ELF"),
    (b"MWo3", "CodeWarrior overlay (MWo3)"),
    (b"\x00\x00\x01\xba", "MPEG program stream"),
    (b"\x00\x00\x01\xb3", "MPEG video elementary stream"),
    (b"SShd", "SShd audio header"),
    (b"TIM2", "TIM2 image"),
    (b"VAGp", "VAG sound"),
    (b"IECSsreV", "Sony SD sound bank (HD)"),
    (b"PK\x03\x04", "zip"),
    (b"RIFF", "RIFF"),
    (b"RESET\0", "IOP replacement image (IOPRP romdir)"),
]


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b)
    return -sum(v / len(b) * math.log2(v / len(b)) for v in c.values())


def looks_like_spu_adpcm(b):
    """Every 16-byte frame: filter <= 4, shift <= 12, flag byte in 0..7."""
    frames = len(b) // 16
    if frames < 64:
        return False
    bad = 0
    for i in range(0, frames * 16, 16):
        if b[i] >> 4 > 4 or b[i] & 15 > 12 or b[i + 1] > 7:
            bad += 1
    return bad / frames < 0.001


def looks_like_dma_gs_packet(b):
    """DMAtag (cnt/ret/end with QWC) followed by VIF NOP + DIRECT/DIRECTHL."""
    if len(b) < 32:
        return False
    tag, = struct.unpack_from("<I", b, 0)
    tid = (tag >> 28) & 7
    qwc = tag & 0xFFFF
    cmds = [(w >> 24) & 0x7F for w in struct.unpack_from("<4I", b, 16)]
    return tid in (1, 6, 7) and qwc > 0 and any(c in (0x50, 0x51) for c in cmds)


def elf_report(data):
    out = []
    if struct.unpack_from("<H", data, 0x10)[0] == 0xFF80:
        # IOP module: .iopmod holds six words, a u16 version, then the name
        shoff, = struct.unpack_from("<I", data, 0x20)
        shnum, = struct.unpack_from("<H", data, 0x30)
        for i in range(shnum):
            s = struct.unpack_from("<10I", data, shoff + 40 * i)
            if s[1] == 0x70000080:                            # SHT_IOPMOD
                ver, = struct.unpack_from("<H", data, s[4] + 0x18)
                end = data.index(b"\0", s[4] + 0x1A)
                name = data[s[4] + 0x1A:end].decode("latin-1")
                out.append("IOP module '%s' version %d.%02d" % (name, ver >> 8, ver & 0xFF))
                return out
        out.append("IOP module (no .iopmod section)")
        return out
    comment = re.findall(rb"(MW MIPS C Compiler \([^)]*\)|GCC: \([^)]*\)[^\0]*|SN Systems[^\0]*|ProDG[^\0]*)", data)
    if comment:
        out.append("compiler: " + ", ".join(sorted({c.decode('latin-1') for c in comment})))
    libs = sorted({m.decode() for m in re.findall(rb"PsIIlib[a-z0-9 ]{2,9}\d{4}", data)})
    if libs:
        out.append("SDK libs: " + ", ".join(l.replace("PsII", "") for l in libs))
    phnum, = struct.unpack_from("<H", data, 0x2C)
    phoff, = struct.unpack_from("<I", data, 0x1C)
    loads = [struct.unpack_from("<8I", data, phoff + 32 * i) for i in range(phnum)]
    empty = collections.Counter(p[2] for p in loads if p[0] == 1 and p[4] == 0 and p[5])
    if empty:
        va, n = empty.most_common(1)[0]
        if n > 1:
            out.append("%d empty PT_LOADs at %08X -> overlay region" % (n, va))
    paths = sorted({m.decode("latin-1") for m in re.findall(rb"(?:cdrom0:)?\\[A-Z0-9_\\]+\.[A-Z0-9]{1,3}(?:;1)?", data)})
    if paths:
        out.append("paths named in code: %d" % len(paths))
        out.extend("    " + p for p in paths)
    return out


def classify(path, deep=False):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(0x10000)
    notes = []
    kind = None
    for magic, label in MAGICS:
        if label and head.startswith(magic):
            kind = label
            break
    if os.path.basename(path).upper() == "SYSTEM.CNF":
        kind = "boot config"
        notes += [l.strip() for l in head.decode("latin-1").splitlines() if l.strip()]
    elif kind == "ELF":
        with open(path, "rb") as f:
            notes += elf_report(f.read())
    elif kind == "MPEG program stream":
        with open(path, "rb") as f:
            body = f.read(0x200000)
        notes.append("has SShd audio (Sony PSS)" if b"SShd" in body else "video only, no SShd audio")
    elif kind is None and looks_like_dma_gs_packet(head):
        kind = "DMA/GIF packet (GS upload)"
    elif kind is None and looks_like_spu_adpcm(head):
        kind = "raw SPU ADPCM stream"
        flags = collections.Counter(head[1::16])
        notes.append("flag bytes %s" % dict(flags))
        if set(flags) <= {2}:
            notes.append("no end/loop-start flags: track bounds must live in code")
        with open(path, "rb") as f:
            f.seek(min(size // 2, 0x100000) & ~(SECTOR - 1))
            il, scores = adpcm.guess_layout(f.read(0x40000))
        notes.append("layout: %s (L/R pairing score %.2f)" % (
            "stereo, interleave %#x" % il if il else "mono",
            scores.get(il, max(scores.values(), default=0.0))))
    if kind is None:
        kind = "unknown (entropy %.2f)" % entropy(head)
        if deep and size > 16 * SECTOR:
            notes += deep_scan(path)
    return size, kind, notes


def deep_scan(path, limit=64 * 1024 * 1024):
    counts = collections.Counter()
    first = {}
    with open(path, "rb") as f:
        pos = 0
        while pos < limit:
            f.seek(pos)
            b = f.read(16)
            if len(b) < 16:
                break
            for magic, label in MAGICS:
                if b.startswith(magic):
                    key = label
                    counts[key] += 1
                    first.setdefault(key, pos)
            pos += SECTOR
    return ["%d sector(s) start with %s (first at %#x)" % (n, k, first[k])
            for k, n in counts.most_common()]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--deep", action="store_true")
    a = ap.parse_args()
    for dirpath, _, files in sorted(os.walk(a.root)):
        for name in sorted(files):
            p = os.path.join(dirpath, name)
            size, kind, notes = classify(p, a.deep)
            print("%-28s %12d  %s" % (os.path.relpath(p, a.root), size, kind))
            for n in notes:
                print("%-28s %12s    %s" % ("", "", n))


if __name__ == "__main__":
    main()
