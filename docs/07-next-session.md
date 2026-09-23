# TODO — session 2

Phase 1 of the plan: room textures. The title page already reads back as
PSMT8; the room pages need PSMT4, and that needs a real GS memory model.

Done in session 1 already: the packet walker (`ps2kit.gs.walk`), PSMT8 +
CLUT on the title page, the text dump.

1. **GS local-memory model** (`ps2kit/gsmem.py`): page/block/column tables
   for PSMCT32, PSMCT16, PSMT8 and PSMT4. Write path: apply a transfer at
   its DBP/DBW. Read path: read any rectangle back in any PSM. Validate by
   reproducing `unswizzle8` on the title page, then read `s04_r0` as PSMT4.
2. **Replay a whole room** into one GS memory image (the GS pack and every
   GS resource) and browse it as PSMT4/PSMT8.
3. **Hunt TEX0**: search the room's resources for 64-bit values whose TBP0
   matches the upload blocks (0x2A00, 0x3180…) to pair textures and CLUTs.
4. **Text tables**: test the voice-clip hypothesis for `{3, 0, n, -1}`.
5. **Ghidra**: install ghidra-emotionengine-reloaded, import `SCES_502.40`
   and `AREA00.BIN`, and find the area loader from the index-reading code
   (xref the `\DATA\INDEX_xx.IDX` path strings at `0x00274880`).

Captures that would help (PCSX2): a GS dump of the title screen and of the
first room, to compare our GS memory image against the real one.
