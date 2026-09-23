"""CodeWarrior PS2 overlay modules ("MWo3").

    python -m ps2kit.mwo3 OVERLAY/*.BIN
    python -m ps2kit.mwo3 AREA00.BIN --seeds [--host MAIN.ELF]   function entries
    python -m ps2kit.mwo3 AREA00.BIN --elf out.elf --host MAIN.ELF

Metrowerks CodeWarrior for PS2 links overlays as separate files with a 0x40
byte header, followed by the text and data images back to back:

    +00  "MWo3"
    +04  u32  overlay number (1-based, link order)
    +08  u32  load address (shared by every overlay of one region)
    +0C  u32  text size
    +10  u32  data size
    +14  u32  bss size
    +18  u32  bss start (load + text + data, aligned to 0x80)
    +1C  u32  bss start, repeated
    +20  char[32] original file name

The whole file, header included, is read to the load address: text starts
at load + 0x40. (Checked on Extermination: every jal inside an overlay lands
on a function prologue with this base, none with text at the load address.)

The main executable reserves one empty PT_LOAD program header per overlay at
the same load address, whose memsz is text + data + bss; an ELF with many
zero-filesz segments at one address is the tell-tale sign.

Disassemblers find little in a raw overlay: it has no entry point and no
symbols. seeds() lists function entries from the code itself (jal targets,
code pointers in the data, frame setups after a return), and to_elf() wraps
the overlay, with the host executable's segments if given, in an ELF that
Ghidra or any other tool can load at the right addresses.
"""
import argparse
import struct

HEADER = 0x40
JR_RA = 0x03E00008


class Overlay:
    def __init__(self, data):
        if data[:4] != b"MWo3":
            raise ValueError("not an MWo3 overlay")
        (self.number, self.load, self.text_size, self.data_size,
         self.bss_size, self.bss_start, self.bss_start2) = struct.unpack_from("<7I", data, 4)
        self.name = data[0x20:0x40].split(b"\0")[0].decode("latin-1")
        self.image = data[HEADER:HEADER + self.text_size + self.data_size]
        if HEADER + self.text_size + self.data_size != len(data):
            raise ValueError("size fields do not add up to the file size")

    @property
    def text(self):
        return self.image[:self.text_size]

    @property
    def text_va(self):
        return self.load + HEADER

    @property
    def data_va(self):
        return self.load + HEADER + self.text_size

    def va_to_off(self, va):
        """Offset into `image` (text then data) of an address."""
        return va - self.load - HEADER

    def read(self, va, n):
        o = self.va_to_off(va)
        if not 0 <= o <= len(self.image) - n:
            raise ValueError("address %08X is outside the overlay" % va)
        return self.image[o:o + n]

    def __repr__(self):
        return ("Overlay(#%d %s load=%08X text=%08X+%05X data=%08X+%05X bss=%08X+%06X)"
                % (self.number, self.name, self.load, self.text_va, self.text_size,
                   self.data_va, self.data_size, self.bss_start, self.bss_size))


def _is_frame(w):
    """addiu $sp, $sp, -n: a function setting up its stack frame."""
    return w >> 16 == 0x27BD and w & 0x8000


def seeds(ov, refs=()):
    """Sorted function entry candidates in the overlay's text:

    * targets of jal inside the overlay's own text;
    * the first frame setup after each `jr $ra` and its delay slot, past nop
      padding, and the first code after the text's leading padding;
    * words anywhere in the overlay (spawn tables, callbacks) and addresses
      in `refs` (what the host executable jumps to or stores) that land on an
      entry: a frame setup, or code right after a return or padding. Every
      overlay of a region shares the addresses, so a host reference may
      belong to another overlay; the test keeps those that fit this one."""
    lo, hi = ov.text_va, ov.text_va + ov.text_size
    words = struct.unpack_from("<%dI" % (len(ov.image) // 4), ov.image)
    text = words[:ov.text_size // 4]

    def entry_like(va):
        k = (va - lo) // 4
        if not (lo <= va < hi and va % 4 == 0) or text[k] == 0:
            return False
        return (_is_frame(text[k]) or k == 0 or text[k - 1] == 0 and
                (k < 2 or text[k - 2] in (0, JR_RA)))

    out = set()
    for i, w in enumerate(text):
        if w >> 26 == 3:                                     # jal
            t = ((w & 0x03FFFFFF) << 2) | (lo & 0xF0000000)
            if lo <= t < hi:
                out.add(t)
        if w == JR_RA:
            k = i + 2
            while k < len(text) and text[k] == 0:
                k += 1
            if k < len(text) and _is_frame(text[k]):
                out.add(lo + 4 * k)
    k = 0
    while k < len(text) and text[k] == 0:
        k += 1
    if k < len(text):
        out.add(lo + 4 * k)
    out.update(w for w in list(words) + list(refs) if entry_like(w))
    return sorted(out)


def host_refs(host, lo, hi):
    """Addresses in [lo, hi) that the host executable jumps to (jal) or
    stores as a word: its ways into an overlay region."""
    d, base = host.data, host.main.vaddr
    words = struct.unpack_from("<%dI" % (host.main.filesz // 4), d, host.main.offset)
    out = set()
    for i, w in enumerate(words):
        if w >> 26 == 3:
            w = ((w & 0x03FFFFFF) << 2) | ((base + 4 * i) & 0xF0000000)
        if lo <= w < hi:
            out.add(w)
    return out


def to_elf(ov, host=None):
    """An ELF32 (MIPS, little endian) image holding the overlay at its load
    address, header included, and bss; plus every loaded segment of `host`
    (a ps2kit.elf.Elf) that does not overlap it. Sections .text/.data/.bss
    name the overlay's parts."""
    segs = []                                    # (vaddr, data, memsz, flags)
    if host:
        for sg in host.segments:
            if sg.filesz and not (sg.vaddr < ov.bss_start + ov.bss_size and
                                  ov.load < sg.vaddr + sg.memsz):
                data = host.data[sg.offset:sg.offset + sg.filesz]
                segs.append((sg.vaddr, data, sg.memsz, sg.flags))
    body = b"\0" * HEADER + ov.image           # the header's bytes are not needed
    pad = ov.bss_start - (ov.load + len(body))
    segs.append((ov.load, body, len(body) + pad + ov.bss_size, 7))
    names = b"\0.text\0.data\0.bss\0.shstrtab\0"
    phoff, n = 0x34, len(segs)
    off = phoff + 32 * n
    ph, blobs = b"", b""
    offsets = []
    for va, data, memsz, flags in segs:
        off = (off + 15) & ~15
        blobs += b"\0" * (off - (phoff + 32 * n + len(blobs)))
        offsets.append(off)
        ph += struct.pack("<8I", 1, off, va, va, len(data), memsz, flags, 16)
        blobs += data
        off += len(data)
    ov_off = offsets[-1]
    strtab_off = phoff + 32 * n + len(blobs)
    shoff = (strtab_off + len(names) + 3) & ~3
    sh = struct.pack("<10I", *[0] * 10)
    sh += struct.pack("<10I", 1, 1, 6, ov.text_va, ov_off + HEADER, ov.text_size, 0, 0, 16, 0)
    sh += struct.pack("<10I", 7, 1, 3, ov.data_va, ov_off + HEADER + ov.text_size,
                      ov.data_size, 0, 0, 16, 0)
    sh += struct.pack("<10I", 13, 8, 3, ov.bss_start, 0, ov.bss_size, 0, 0, 16, 0)
    sh += struct.pack("<10I", 18, 3, 0, 0, strtab_off, len(names), 0, 0, 1, 0)
    text = ov.text
    entry = next((ov.text_va + k for k in range(0, len(text), 4) if any(text[k:k + 4])),
                 ov.text_va)                             # past the leading padding
    ehdr = (b"\x7fELF\x01\x01\x01" + b"\0" * 9 +
            struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, entry, phoff, shoff, 0x20924001,
                        0x34, 32, n, 40, 5, 4))
    out = ehdr + ph + blobs + names
    return out + b"\0" * (shoff - len(out)) + sh


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--seeds", action="store_true", help="print function entry candidates")
    ap.add_argument("--elf", metavar="OUT", help="write an ELF of one overlay")
    ap.add_argument("--host", help="the main executable, included in the ELF")
    a = ap.parse_args()
    for path in a.files:
        ov = Overlay(open(path, "rb").read())
        print(ov)
        if a.seeds:
            refs = ()
            if a.host:
                from ps2kit import elf
                refs = host_refs(elf.Elf(a.host), ov.text_va, ov.text_va + ov.text_size)
            for va in seeds(ov, refs):
                print("0x%08X" % va)
        if a.elf:
            host = None
            if a.host:
                from ps2kit import elf
                host = elf.Elf(a.host)
            open(a.elf, "wb").write(to_elf(ov, host))


if __name__ == "__main__":
    main()
