# TODO — session 2

Phase 1 of the plan: first pictures. The title logo is the test case,
because it is one self-contained transfer and we already know what it should
look like.

1. **GS local-memory model** (`ps2kit/gsmem.py`): page/block/column layout
   and swizzles for PSMCT32, PSMCT16, PSMT8, PSMT4, and the CLUT layout
   (CSM1). Write path: apply a BITBLTBUF/TRXPOS/TRXREG transfer. Read path:
   read a rectangle back in any PSM. Validate by round-tripping, then on the
   section 2 logo.
2. **GS packet walker** (`ps2kit/gspacket.py`): DMA tag → VIF codes → GIF
   tags → register writes and image data. Enough to replay every GS pack of
   the disc into a GS memory image.
3. **Dump GS memory images** of the title section and of one room, and look
   at them as PSMT8/PSMT4 with guessed CLUTs. Then hunt the TEX0 values in
   the room's resources to pair textures with palettes.
4. **Text**: solve the slot `0x3F` table, write `tools/ext_text.py`, dump all
   five languages.
5. **Ghidra**: install ghidra-emotionengine-reloaded, import `SCES_502.40`
   and `AREA00.BIN`, and find the area loader from the index-reading code
   (xref the `\DATA\INDEX_xx.IDX` path strings at `0x00274880`).

Captures that would help (PCSX2): a GS dump of the title screen and of the
first room, to compare our GS memory image against the real one.
