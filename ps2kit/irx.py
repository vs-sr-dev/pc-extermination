"""IOP modules (IRX): relocation, import and export tables.

    python -m ps2kit.irx MODULE.IRX            module info, imports, exports
    python -m ps2kit.irx MODULE.IRX --image out.bin   relocated image at 0

An IRX is a relocatable MIPS I ELF of type 0xFF80 with a `.iopmod` section
(module name, version, entry point, gp). Code reaches other modules through
stub tables that the loader patches at run time:

    u32 0x41E00000, u32 0, u16 version, u16 0, char name[8]
    per function: `jr $ra` then `addiu $zero, $zero, ordinal`
    u32 0, u32 0

An export table looks the same with a different magic (0x41C00000) and a
list of function addresses instead of stubs. relocate() applies the REL
relocations at a chosen base (R_MIPS_32, 26, HI16/LO16 pairs), so a
disassembler sees real jump targets and data addresses.

The ordinal names below come from the public SDK headers for the libraries
most games import; unknown ordinals are shown by number.
"""
import argparse
import struct

TYPE_IRX = 0xFF80
IMPORT_MAGIC, EXPORT_MAGIC = 0x41E00000, 0x41C00000

# ordinal -> name for common IOP libraries (ps2sdk import headers)
ORDINALS = {
    "libsd": {
        2: "sceSdQuit", 4: "sceSdInit", 5: "sceSdSetParam", 6: "sceSdGetParam",
        7: "sceSdSetSwitch", 8: "sceSdGetSwitch", 9: "sceSdSetAddr",
        10: "sceSdGetAddr", 11: "sceSdSetCoreAttr", 12: "sceSdGetCoreAttr",
        13: "sceSdNote2Pitch", 14: "sceSdPitch2Note", 15: "sceSdProcBatch",
        16: "sceSdProcBatchEx", 17: "sceSdVoiceTrans", 18: "sceSdBlockTrans",
        19: "sceSdVoiceTransStatus", 20: "sceSdBlockTransStatus",
        21: "sceSdSetTransCallback", 22: "sceSdSetIRQCallback",
        23: "sceSdSetEffectAttr", 24: "sceSdGetEffectAttr",
        25: "sceSdClearEffectWorkArea", 26: "sceSdSetTransIntrHandler",
        27: "sceSdSetSpu2IntrHandler",
    },
    "sysclib": {
        4: "setjmp", 5: "longjmp", 6: "toupper", 7: "tolower", 8: "look_ctype_table",
        9: "get_ctype_table", 10: "memchr", 11: "memcmp", 12: "memcpy",
        13: "memmove", 14: "memset", 15: "bcmp", 16: "bcopy", 17: "bzero",
        18: "prnt", 19: "sprintf", 20: "strcat", 21: "strchr", 22: "strcmp",
        23: "strcpy", 24: "strcspn", 25: "index", 26: "rindex", 27: "strlen",
        28: "strncat", 29: "strncmp", 30: "strncpy", 31: "strpbrk",
        32: "strrchr", 33: "strspn", 34: "strstr", 35: "strtok", 36: "strtol",
        37: "atob", 38: "strtoul", 40: "wmemcopy", 41: "wmemset", 42: "vsprintf",
    },
    "thbase": {
        4: "CreateThread", 5: "DeleteThread", 6: "StartThread",
        7: "StartThreadArgs", 8: "ExitThread", 9: "ExitDeleteThread",
        10: "TerminateThread", 11: "iTerminateThread", 14: "ChangeThreadPriority",
        15: "iChangeThreadPriority", 16: "RotateThreadReadyQueue",
        17: "iRotateThreadReadyQueue", 18: "ReleaseWaitThread",
        19: "iReleaseWaitThread", 20: "GetThreadId", 22: "ReferThreadStatus",
        23: "iReferThreadStatus", 24: "SleepThread", 25: "WakeupThread",
        26: "iWakeupThread", 27: "CancelWakeupThread", 28: "iCancelWakeupThread",
        29: "SuspendThread", 30: "iSuspendThread", 31: "ResumeThread",
        32: "iResumeThread", 33: "DelayThread", 34: "GetSystemTime",
        35: "SetAlarm", 36: "iSetAlarm", 37: "CancelAlarm", 38: "iCancelAlarm",
        39: "USec2SysClock", 40: "SysClock2USec", 41: "GetSystemStatusFlag",
    },
    "intrman": {
        4: "RegisterIntrHandler", 5: "ReleaseIntrHandler", 6: "EnableIntr",
        7: "DisableIntr", 8: "CpuDisableIntr", 9: "CpuEnableIntr",
        17: "CpuSuspendIntr", 18: "CpuResumeIntr", 23: "QueryIntrContext",
    },
    "sifcmd": {
        4: "sceSifInitCmd", 5: "sceSifExitCmd", 6: "sceSifGetSreg",
        7: "sceSifSetSreg", 8: "sceSifSetCmdBuffer", 10: "sceSifAddCmdHandler",
        11: "sceSifRemoveCmdHandler", 12: "sceSifSendCmd", 13: "isceSifSendCmd",
        14: "sceSifInitRpc", 15: "sceSifBindRpc", 16: "sceSifCallRpc",
        17: "sceSifRegisterRpc", 18: "sceSifCheckStatRpc",
        19: "sceSifSetRpcQueue", 20: "sceSifGetNextRequest",
        21: "sceSifExecRequest", 22: "sceSifRpcLoop", 23: "sceSifGetOtherData",
        24: "sceSifRemoveRpc", 25: "sceSifRemoveRpcQueue",
    },
    "sifman": {
        5: "sceSifInit", 6: "sceSifSetDChain", 7: "sceSifSetDma",
        8: "sceSifDmaStat", 29: "sceSifCheckInit",
    },
    "timrman": {
        4: "AllocHardTimer", 5: "ReferHardTimer", 6: "FreeHardTimer",
        7: "SetTimerMode", 8: "GetTimerStatus", 9: "SetTimerCounter",
        10: "GetTimerCounter", 11: "SetTimerCompare", 12: "GetTimerCompare",
        13: "SetHoldMode", 14: "GetHoldMode", 15: "GetHoldReg",
        16: "GetHardTimerIntrCode", 20: "SetTimerHandler",
    },
    "loadcore": {
        6: "RegisterLibraryEntries", 7: "ReleaseLibraryEntries",
    },
}


class Irx:
    def __init__(self, data):
        d = self.data = bytes(data)
        if d[:4] != b"\x7fELF":
            raise ValueError("not an ELF file")
        etype, = struct.unpack_from("<H", d, 16)
        if etype != TYPE_IRX:
            raise ValueError("not an IRX (ELF type %04X)" % etype)
        shoff, = struct.unpack_from("<I", d, 0x20)
        shnum, shstrndx = struct.unpack_from("<HH", d, 0x30)
        sh = [struct.unpack_from("<10I", d, shoff + 40 * i) for i in range(shnum)]
        base = sh[shstrndx][4]
        self.sections = []                  # (name, type, addr, offset, size, info)
        for s in sh:
            name = d[base + s[0]:d.index(b"\0", base + s[0])].decode("latin-1")
            self.sections.append((name, s[1], s[3], s[4], s[5], s[7]))
        mod = self.section(".iopmod")
        _, entry, gp, tsz, dsz, bsz, ver = struct.unpack_from("<IIIIIIH", d, mod[3])
        self.name = d[mod[3] + 26:d.index(b"\0", mod[3] + 26)].decode("latin-1")
        self.version = ver
        self.entry, self.gp = entry, gp
        self.text_size, self.data_size, self.bss_size = tsz, dsz, bsz

    def section(self, name):
        return next((s for s in self.sections if s[0] == name), None)

    def image(self, base=0):
        """The loaded image (text, rodata, data; bss zeroed), relocated at base."""
        size = max(s[2] + s[4] for s in self.sections if s[1] in (1, 8) and s[2] + s[4])
        img = bytearray(size)
        for name, typ, addr, off, sz, _ in self.sections:
            if typ == 1 and name != ".iopmod":
                img[addr:addr + sz] = self.data[off:off + sz]
        relocate(img, self._relocs(), base)
        return bytes(img)

    def _relocs(self):
        out = []
        for name, typ, addr, off, sz, info in self.sections:
            if typ == 9:                                    # SHT_REL
                for i in range(0, sz, 8):
                    r_off, r_info = struct.unpack_from("<II", self.data, off + i)
                    out.append((r_off, r_info & 0xFF))
        return out

    def imports(self, image=None):
        """[(library, version, [(stub address, ordinal)])], from the image."""
        return _tables(image or self.image(), IMPORT_MAGIC, stubs=True)

    def exports(self, image=None):
        """[(library, version, [(ordinal, function address)])]."""
        return _tables(image or self.image(), EXPORT_MAGIC, stubs=False)

    def stub_names(self, image=None):
        """{stub address: "library.name"} for every import stub."""
        out = {}
        for lib, _, entries in self.imports(image):
            names = ORDINALS.get(lib, {})
            for addr, n in entries:
                out[addr] = "%s.%s" % (lib, names.get(n, "#%d" % n))
        return out


def relocate(img, relocs, base):
    """Apply MIPS REL relocations to img (relative to 0) for a load at base."""
    hi = []
    for off, typ in relocs:
        w, = struct.unpack_from("<I", img, off)
        if typ == 2:                                        # R_MIPS_32
            w = (w + base) & 0xFFFFFFFF
        elif typ == 4:                                      # R_MIPS_26
            t = ((w & 0x03FFFFFF) << 2) + base
            w = (w & 0xFC000000) | ((t >> 2) & 0x03FFFFFF)
        elif typ == 5:                                      # R_MIPS_HI16
            hi.append(off)
            continue
        elif typ == 6:                                      # R_MIPS_LO16
            lo = struct.unpack_from("<h", img, off)[0]
            for h in hi:
                hw, = struct.unpack_from("<I", img, h)
                v = ((hw & 0xFFFF) << 16) + lo + base
                hw = (hw & 0xFFFF0000) | (((v + 0x8000) >> 16) & 0xFFFF)
                struct.pack_into("<I", img, h, hw)
            hi = []
            w = (w & 0xFFFF0000) | ((lo + base) & 0xFFFF)
        else:
            continue
        struct.pack_into("<I", img, off, w)


def _tables(img, magic, stubs):
    out = []
    for p in range(0, len(img) - 20, 4):
        if struct.unpack_from("<II", img, p) != (magic, 0):
            continue
        ver, = struct.unpack_from("<H", img, p + 8)
        name = img[p + 12:p + 20].split(b"\0")[0].decode("latin-1")
        if not name.isprintable() or not name:
            continue
        entries, q = [], p + 20
        if stubs:
            while q + 8 <= len(img):
                a, b = struct.unpack_from("<II", img, q)
                if a != 0x03E00008 or b >> 16 != 0x2400:
                    break
                entries.append((q, b & 0xFFFF))
                q += 8
        else:
            n = 0
            while q + 4 <= len(img):
                a, = struct.unpack_from("<I", img, q)
                if a == 0:
                    break
                entries.append((n, a))
                n += 1
                q += 4
        out.append((name, ver, entries))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("irx")
    ap.add_argument("--base", type=lambda s: int(s, 0), default=0)
    ap.add_argument("--image", metavar="OUT")
    a = ap.parse_args()
    m = Irx(open(a.irx, "rb").read())
    img = m.image(a.base)
    print("%s v%d.%02d  entry %08X  gp %08X  text %X data %X bss %X" % (
        m.name, m.version >> 8, m.version & 0xFF, m.entry + a.base, m.gp + a.base,
        m.text_size, m.data_size, m.bss_size))
    for lib, ver, entries in m.imports(img):
        names = ORDINALS.get(lib, {})
        print("import %-10s v%X" % (lib, ver))
        for addr, n in entries:
            print("  %08X  %3d  %s" % (addr, n, names.get(n, "?")))
    for lib, ver, entries in m.exports(img):
        print("export %-10s v%X: %s" % (lib, ver, " ".join("%d=%08X" % e for e in entries)))
    if a.image:
        open(a.image, "wb").write(img)


if __name__ == "__main__":
    main()
