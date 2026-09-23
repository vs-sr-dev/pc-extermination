"""VU0/VU1 microcode: disassemble instruction pairs, find MPG uploads.

    python -m ps2kit.vu SCES_502.40 --dma 0x2322F0               MPGs of a DMA chain
    python -m ps2kit.vu SCES_502.40 --elf 0x2313A4 0x231F9C     MPGs in a VIF stream
    python -m ps2kit.vu micro.bin [--base 0]                      raw microcode

A VU instruction is 64 bits: the lower word (integer, load/store, branch,
FDIV, EFU) at the lower address and the upper word (FMAC) above it. Both run
in the same cycle. When the upper word's I bit is set, the lower word is a
float loaded into the I register instead of an instruction.

Upper word: I E M D T flags (bits 31-27), dest xyzw (24-21), ft (20-16),
fs (15-11), fd (10-6), opcode (5-0); opcodes 0x3C-0x3F take their real
opcode from bits 10-6 and 1-0. Lower word: opcode in bits 31-25; 0x40 is a
register group like the upper one (bits 5-0, and 10-6 with 1-0 for 0x3C-3F).
Branch offsets are 11-bit signed counts of instructions from the next one.
"""
import argparse
import struct

XYZW = "xyzw"
BC = XYZW

UPPER = {}
for i, n in enumerate(("add", "sub", "madd", "msub", "max", "mini", "mul")):
    for b in range(4):
        UPPER[4 * i + b] = (n + BC[b], "fd_fs_ftbc")
UPPER.update({0x1C: ("mulq", "fd_fs_q"), 0x1D: ("maxi", "fd_fs_i"), 0x1E: ("muli", "fd_fs_i"),
              0x1F: ("minii", "fd_fs_i"), 0x20: ("addq", "fd_fs_q"), 0x21: ("maddq", "fd_fs_q"),
              0x22: ("addi", "fd_fs_i"), 0x23: ("maddi", "fd_fs_i"), 0x24: ("subq", "fd_fs_q"),
              0x25: ("msubq", "fd_fs_q"), 0x26: ("subi", "fd_fs_i"), 0x27: ("msubi", "fd_fs_i"),
              0x28: ("add", "fd_fs_ft"), 0x29: ("madd", "fd_fs_ft"), 0x2A: ("mul", "fd_fs_ft"),
              0x2B: ("max", "fd_fs_ft"), 0x2C: ("sub", "fd_fs_ft"), 0x2D: ("msub", "fd_fs_ft"),
              0x2E: ("opmsub", "fd_fs_ft"), 0x2F: ("mini", "fd_fs_ft")})
UPPER_X = {}
for i, n in enumerate(("adda", "suba", "madda", "msuba")):
    for b in range(4):
        UPPER_X[4 * i + b] = (n + BC[b], "acc_fs_ftbc")
for b in range(4):
    UPPER_X[0x18 + b] = ("mula" + BC[b], "acc_fs_ftbc")
UPPER_X.update({0x10: ("itof0", "ft_fs"), 0x11: ("itof4", "ft_fs"), 0x12: ("itof12", "ft_fs"),
                0x13: ("itof15", "ft_fs"), 0x14: ("ftoi0", "ft_fs"), 0x15: ("ftoi4", "ft_fs"),
                0x16: ("ftoi12", "ft_fs"), 0x17: ("ftoi15", "ft_fs"), 0x1C: ("mulaq", "acc_fs_q"),
                0x1D: ("abs", "ft_fs"), 0x1E: ("mulai", "acc_fs_i"), 0x1F: ("clipw", "fs_ftw"),
                0x20: ("addaq", "acc_fs_q"), 0x21: ("maddaq", "acc_fs_q"), 0x22: ("addai", "acc_fs_i"),
                0x23: ("maddai", "acc_fs_i"), 0x24: ("subaq", "acc_fs_q"), 0x25: ("msubaq", "acc_fs_q"),
                0x26: ("subai", "acc_fs_i"), 0x27: ("msubai", "acc_fs_i"), 0x28: ("adda", "acc_fs_ft"),
                0x29: ("madda", "acc_fs_ft"), 0x2A: ("mula", "acc_fs_ft"), 0x2C: ("suba", "acc_fs_ft"),
                0x2D: ("msuba", "acc_fs_ft"), 0x2E: ("opmula", "acc_fs_ft"), 0x2F: ("nop", "")})

LOWER = {0x00: ("lq", "ft_imm_is"), 0x01: ("sq", "fs_imm_it"), 0x04: ("ilw", "it_imm_is"),
         0x05: ("isw", "it_imm_is"), 0x08: ("iaddiu", "it_is_imm15"), 0x09: ("isubiu", "it_is_imm15"),
         0x10: ("fceq", "vi1_imm24"), 0x11: ("fcset", "imm24"), 0x12: ("fcand", "vi1_imm24"),
         0x13: ("fcor", "vi1_imm24"), 0x14: ("fseq", "it_imm12"), 0x15: ("fsset", "imm12"),
         0x16: ("fsand", "it_imm12"), 0x17: ("fsor", "it_imm12"), 0x18: ("fmeq", "it_is"),
         0x1A: ("fmand", "it_is"), 0x1B: ("fmor", "it_is"), 0x1C: ("fcget", "it"),
         0x20: ("b", "br"), 0x21: ("bal", "it_br"), 0x24: ("jr", "is"), 0x25: ("jalr", "it_is"),
         0x28: ("ibeq", "it_is_br"), 0x29: ("ibne", "it_is_br"), 0x2C: ("ibltz", "is_br"),
         0x2D: ("ibgtz", "is_br"), 0x2E: ("iblez", "is_br"), 0x2F: ("ibgez", "is_br")}
LOWER_R = {0x30: ("iadd", "id_is_it"), 0x31: ("isub", "id_is_it"), 0x32: ("iaddi", "it_is_imm5"),
           0x34: ("iand", "id_is_it"), 0x35: ("ior", "id_is_it")}
LOWER_X = {0x30: ("move", "ft_fs"), 0x31: ("mr32", "ft_fs"), 0x34: ("lqi", "ft_isinc"),
           0x35: ("sqi", "fs_itinc"), 0x36: ("lqd", "ft_isdec"), 0x37: ("sqd", "fs_itdec"),
           0x38: ("div", "q_fsf_ftf"), 0x39: ("sqrt", "q_ftf"), 0x3A: ("rsqrt", "q_fsf_ftf"),
           0x3B: ("waitq", ""), 0x3C: ("mtir", "it_fsf"), 0x3D: ("mfir", "ft_is"),
           0x3E: ("ilwr", "it_is_dest"), 0x3F: ("iswr", "it_is_dest"), 0x40: ("rnext", "ft_r"),
           0x41: ("rget", "ft_r"), 0x42: ("rinit", "r_fsf"), 0x43: ("rxor", "r_fsf"),
           0x64: ("mfp", "ft_p"), 0x68: ("xtop", "it"), 0x69: ("xitop", "it"), 0x6C: ("xgkick", "is"),
           0x70: ("esadd", "p_fs"), 0x71: ("ersadd", "p_fs"), 0x72: ("eleng", "p_fs"),
           0x73: ("erleng", "p_fs"), 0x74: ("eatanxy", "p_fs"), 0x75: ("eatanxz", "p_fs"),
           0x76: ("esum", "p_fs"), 0x78: ("esqrt", "p_fsf"), 0x79: ("ersqrt", "p_fsf"),
           0x7A: ("ercpr", "p_fsf"), 0x7B: ("waitp", ""), 0x7C: ("esin", "p_fsf"),
           0x7D: ("eatan", "p_fsf"), 0x7E: ("eexp", "p_fsf")}
LOWER_NOP = 0x8000033C


def _dest(w):
    return "".join(c for i, c in enumerate(XYZW) if w >> (24 - i) & 1)


def _fields(w):
    return (w >> 16 & 31, w >> 11 & 31, w >> 6 & 31)          # t, s, d


def upper(w):
    """Mnemonic and operands of an upper word (flags not included)."""
    op = w & 0x3F
    if op >= 0x3C:
        name, form = UPPER_X.get((w >> 6 & 31) << 2 | op & 3, ("?u%08X" % w, ""))
    else:
        name, form = UPPER.get(op, ("?u%08X" % w, ""))
    t, s, d = _fields(w)
    dst = _dest(w)
    if form == "":
        return name
    name += "." + dst if dst and form not in ("fs_ftw",) else ""
    ops = {"fd_fs_ftbc": "vf%d, vf%d, vf%d%s" % (d, s, t, BC[op & 3]),
           "acc_fs_ftbc": "acc, vf%d, vf%d%s" % (s, t, BC[op & 3]),
           "fd_fs_q": "vf%d, vf%d, q" % (d, s), "fd_fs_i": "vf%d, vf%d, i" % (d, s),
           "fd_fs_ft": "vf%d, vf%d, vf%d" % (d, s, t), "acc_fs_q": "acc, vf%d, q" % s,
           "acc_fs_i": "acc, vf%d, i" % s, "acc_fs_ft": "acc, vf%d, vf%d" % (s, t),
           "ft_fs": "vf%d, vf%d" % (t, s), "fs_ftw": "vf%d, vf%dw" % (s, t)}[form]
    return "%-10s %s" % (name, ops)


def lower(w, pc=0):
    """Mnemonic and operands of a lower word at instruction address pc (in bytes)."""
    if w == LOWER_NOP:
        return "nop"
    op = w >> 25
    t, s, d = _fields(w)
    dst = _dest(w)
    if op == 0x40:
        sub = w & 0x3F
        if sub >= 0x3C:
            name, form = LOWER_X.get((w >> 6 & 31) << 2 | sub & 3, ("?l%08X" % w, ""))
        else:
            name, form = LOWER_R.get(sub, ("?l%08X" % w, ""))
    else:
        name, form = LOWER.get(op, ("?l%08X" % w, ""))
    imm11 = w & 0x7FF
    imm11 -= 0x800 if imm11 & 0x400 else 0
    target = pc + 8 + imm11 * 8
    fsf, ftf = XYZW[w >> 21 & 3], XYZW[w >> 23 & 3]
    imm5 = d - 32 if d & 16 else d
    ops = {"": "", "ft_imm_is": "vf%d, %d(vi%d)" % (t, imm11, s),
           "fs_imm_it": "vf%d, %d(vi%d)" % (s, imm11, t),
           "it_imm_is": "vi%d, %d(vi%d)" % (t, imm11, s),
           "it_is_imm15": "vi%d, vi%d, 0x%X" % (t, s, (w >> 10 & 0x7800) | w & 0x7FF),
           "vi1_imm24": "vi1, 0x%06X" % (w & 0xFFFFFF), "imm24": "0x%06X" % (w & 0xFFFFFF),
           "it_imm12": "vi%d, 0x%03X" % (t, (w >> 10 & 0x800) | w & 0x7FF),
           "imm12": "0x%03X" % ((w >> 10 & 0x800) | w & 0x7FF),
           "it_is": "vi%d, vi%d" % (t, s), "it": "vi%d" % t, "is": "vi%d" % s,
           "br": "0x%04X" % target, "it_br": "vi%d, 0x%04X" % (t, target),
           "it_is_br": "vi%d, vi%d, 0x%04X" % (t, s, target), "is_br": "vi%d, 0x%04X" % (s, target),
           "id_is_it": "vi%d, vi%d, vi%d" % (d, s, t), "it_is_imm5": "vi%d, vi%d, %d" % (t, s, imm5),
           "ft_fs": "vf%d, vf%d" % (t, s), "ft_isinc": "vf%d, (vi%d++)" % (t, s),
           "fs_itinc": "vf%d, (vi%d++)" % (s, t), "ft_isdec": "vf%d, (--vi%d)" % (t, s),
           "fs_itdec": "vf%d, (--vi%d)" % (s, t), "q_fsf_ftf": "q, vf%d%s, vf%d%s" % (s, fsf, t, ftf),
           "q_ftf": "q, vf%d%s" % (t, ftf), "it_fsf": "vi%d, vf%d%s" % (t, s, fsf),
           "ft_is": "vf%d, vi%d" % (t, s), "it_is_dest": "vi%d, (vi%d)" % (t, s),
           "ft_r": "vf%d, r" % t, "r_fsf": "r, vf%d%s" % (s, fsf), "ft_p": "vf%d, p" % t,
           "p_fs": "p, vf%d" % s, "p_fsf": "p, vf%d%s" % (s, fsf)}[form]
    if dst and form in ("ft_imm_is", "fs_imm_it", "ft_fs", "ft_isinc", "fs_itinc", "ft_isdec",
                        "fs_itdec", "ft_is", "ft_r", "ft_p", "it_is_dest", "it_imm_is"):
        name += "." + dst
    return "%-10s %s" % (name, ops) if ops else name


def disasm(code, base=0):
    """Yield (address, lower word, upper word, text) for each instruction."""
    for i in range(0, len(code) - 7, 8):
        lo, up = struct.unpack_from("<II", code, i)
        flags = "".join(f for b, f in zip(range(31, 26, -1), "IEMDT") if up >> b & 1)
        u = upper(up)
        l = "loi        %r" % struct.unpack("<f", struct.pack("<I", lo))[0] if up >> 31 else \
            lower(lo, base + i)
        text = "%-34s %s" % (u, l)
        if flags:
            text += "    [%s]" % flags
        yield base + i, lo, up, text


def mpg_uploads(buf, start, end):
    """(VU address in bytes, code) of every MPG in a VIF stream."""
    from . import vif
    return [((c.imm) * 8, c.data) for c in vif.walk(buf, start, end) if c.cmd == 0x4A]


def dma_uploads(read, addr, limit=256):
    """(VU address in bytes, code) of the MPGs in a DMA chain of cnt tags,
    starting at addr; read(va, n) gives memory. Stops at the first tag
    other than cnt (the game's packets end with ret)."""
    from . import vif
    out = []
    for _ in range(limit):
        tag, = struct.unpack("<Q", read(addr, 8))
        qwc, tid = tag & 0xFFFF, tag >> 28 & 7
        buf = read(addr + 8, 8 + qwc * 16)
        out += [(c.imm * 8, c.data) for c in vif.walk(buf, 0, len(buf)) if c.cmd == 0x4A]
        if tid != 1:
            break
        addr += 16 + qwc * 16
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--elf", nargs=2, metavar=("START", "END"),
                    help="walk the VIF stream between two addresses of an ELF")
    ap.add_argument("--dma", metavar="VA", help="follow the DMA chain at an ELF address")
    ap.add_argument("--base", type=lambda v: int(v, 0), default=0)
    a = ap.parse_args()
    if a.elf or a.dma:
        from . import elf
        e = elf.Elf(a.file)
        if a.dma:
            uploads = dma_uploads(e.read, int(a.dma, 0))
        else:
            lo, hi = (int(x, 0) for x in a.elf)
            uploads = mpg_uploads(e.read(lo, hi - lo), 0, hi - lo)
        for addr, code in uploads:
            print("; MPG to VU address 0x%04X, %d instructions" % (addr, len(code) // 8))
            for pc, _, _, text in disasm(code, addr):
                print("%04X  %s" % (pc, text))
    else:
        code = open(a.file, "rb").read()
        for pc, _, _, text in disasm(code, a.base):
            print("%04X  %s" % (pc, text))


if __name__ == "__main__":
    main()
