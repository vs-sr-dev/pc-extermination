"""EE executable loading, address mapping and cross-references.

    python -m ps2kit.elf SCES_502.40 --info
    python -m ps2kit.elf SCES_502.40 --xref 0x270490
    python -m ps2kit.elf SCES_502.40 --read 0x25E8B0 64

PS2 retail executables are stripped, so the most useful question is usually
"who uses this address?". The EE has no PC-relative data loads: a 32-bit
address is built with `lui` followed by `addiu`/`ori` or folded into a
load/store offset. xref() tracks the last `lui` per register and reports every
completed pair that lands on the target.
"""
import argparse
import struct

# opcodes whose 16-bit immediate completes a lui (I-type, rs = base register)
_ADDIU, _ORI = 0x09, 0x0D
_MEM = {0x20, 0x21, 0x23, 0x24, 0x25, 0x27, 0x28, 0x29, 0x2B, 0x31, 0x35,
        0x37, 0x39, 0x3D, 0x3F, 0x1E, 0x1F}          # lb..sd, lwc1/swc1, lq/sq
_LUI = 0x0F


class Segment:
    def __init__(self, vaddr, offset, filesz, memsz, flags):
        self.vaddr, self.offset = vaddr, offset
        self.filesz, self.memsz, self.flags = filesz, memsz, flags

    def __repr__(self):
        return "Segment(va=%08X off=%06X filesz=%06X memsz=%06X)" % (
            self.vaddr, self.offset, self.filesz, self.memsz)


class Elf:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        if d[:4] != b"\x7fELF":
            raise ValueError("not an ELF file")
        self.entry, phoff, shoff = struct.unpack_from("<III", d, 0x18)
        phnum, = struct.unpack_from("<H", d, 0x2C)
        shnum, shstrndx = struct.unpack_from("<HH", d, 0x30)
        self.segments = []
        for i in range(phnum):
            p = struct.unpack_from("<8I", d, phoff + 32 * i)
            if p[0] == 1:                               # PT_LOAD
                self.segments.append(Segment(p[2], p[1], p[4], p[5], p[6]))
        self.sections = {}
        if shnum and shoff:
            sh = [struct.unpack_from("<10I", d, shoff + 40 * i) for i in range(shnum)]
            base = sh[shstrndx][4]
            for s in sh:
                name = d[base + s[0]:d.index(b"\0", base + s[0])].decode("latin-1")
                if name:
                    self.sections[name] = (s[3], s[4], s[5])
        # The loaded image is the first segment with file content.
        self.main = next(s for s in self.segments if s.filesz)

    def comment(self):
        """Compiler identification from .comment, if the linker kept it."""
        if ".comment" not in self.sections:
            return None
        _, off, size = self.sections[".comment"]
        return [p.decode("latin-1") for p in self.data[off:off + size].split(b"\0") if p]

    def va_to_off(self, va):
        for s in self.segments:
            if s.filesz and s.vaddr <= va < s.vaddr + s.filesz:
                return va - s.vaddr + s.offset
        raise ValueError("address %08X is not backed by the file" % va)

    def read(self, va, n):
        o = self.va_to_off(va)
        return self.data[o:o + n]

    def u32(self, va):
        return struct.unpack_from("<I", self.data, self.va_to_off(va))[0]

    def words(self, lo=None, hi=None):
        """Yield (va, word) over the main segment, or over [lo, hi)."""
        s = self.main
        lo = s.vaddr if lo is None else lo
        hi = s.vaddr + s.filesz if hi is None else hi
        o = self.va_to_off(lo)
        n = (hi - lo) // 4
        for i, w in enumerate(struct.unpack_from("<%dI" % n, self.data, o)):
            yield lo + 4 * i, w

    def xref(self, targets, window=64, span=4):
        """Find instructions that complete a lui pair onto any target.

        `span` widens each target into [t, t+span), so a field inside a
        structure still matches. Returns [(site_va, full_address, lui_va)].
        """
        targets = list(targets)
        hits = []
        lui = {}
        for va, w in self.words():
            op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 0xFFFF
            if op == _LUI:
                lui[rt] = (imm << 16, va)
                continue
            if (op in _MEM or op in (_ADDIU, _ORI)) and rs in lui:
                hi, lva = lui[rs]
                if va - lva > window:
                    continue
                simm = imm - 0x10000 if (imm & 0x8000 and op != _ORI) else imm
                full = (hi + simm) & 0xFFFFFFFF
                for t in targets:
                    if t <= full < t + span:
                        hits.append((va, full, lva))
        return hits

    def find_bytes(self, needle):
        """Every virtual address at which `needle` occurs in the main segment."""
        s, out, i = self.main, [], self.data.find(needle)
        while i != -1:
            if s.offset <= i < s.offset + s.filesz:
                out.append(i - s.offset + s.vaddr)
            i = self.data.find(needle, i + 1)
        return out

    def stats(self):
        """Instruction-mix counters that say a lot about the toolchain."""
        c = {"jr_ra": 0, "jal_targets": set(), "cop2": 0, "mmi": 0, "lq_sq": 0}
        for _, w in self.words():
            op = w >> 26
            if w == 0x03E00008:
                c["jr_ra"] += 1
            elif op == 0x03:
                c["jal_targets"].add(w & 0x3FFFFFF)
            elif op == 0x12:
                c["cop2"] += 1
            elif op == 0x1C:
                c["mmi"] += 1
            elif op in (0x1E, 0x1F):
                c["lq_sq"] += 1
        c["jal_targets"] = len(c["jal_targets"])
        return c


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("elf")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--xref", nargs="+", metavar="VA")
    ap.add_argument("--read", nargs=2, metavar=("VA", "N"))
    a = ap.parse_args()
    e = Elf(a.elf)
    if a.info:
        print("entry   %08X" % e.entry)
        print("comment %s" % e.comment())
        for s in e.segments:
            print("  ", s)
        for k, v in e.stats().items():
            print("  %-12s %d" % (k, v))
    if a.xref:
        for va, full, lva in e.xref(int(x, 0) for x in a.xref):
            print("%08X  -> %08X  (lui at %08X)" % (va, full, lva))
    if a.read:
        va, n = int(a.read[0], 0), int(a.read[1], 0)
        b = e.read(va, n)
        for i in range(0, len(b), 16):
            print("%08X  %s" % (va + i, b[i:i + 16].hex(" ")))


if __name__ == "__main__":
    main()
