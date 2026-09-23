"""CodeWarrior PS2 overlay modules ("MWo3").

    python -m ps2kit.mwo3 OVERLAY/*.BIN

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
"""
import argparse
import struct

HEADER = 0x40


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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    for path in ap.parse_args().files:
        print(Overlay(open(path, "rb").read()))


if __name__ == "__main__":
    main()
