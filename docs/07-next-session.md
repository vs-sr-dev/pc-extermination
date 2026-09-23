# TODO — session 3

Phase 1 continues with the **models**, and phase 2 with the code that draws
them. Textures are done (session 2): `tools/ext_tex.py` gives every room
texture as PNG, keyed by TEX0.

1. **Mesh format** (slots `0x43`, `0x44`, `0x72`… of the rooms). Known: the
   resource header `u32 n, u32 qwc, u32 k, u32 bytes = qwc·16 + 0x40`, then
   64-byte vertices `TEX0 | s t q 0 | 4 floats | x y z w`. To find: the
   header fields, the second float quadword (normal? colour?), the flag bits
   in w's mantissa (strip restart / ADC?), how vertices group into
   primitives. Goal: export one room to glTF with its textures and check it
   in Blender (the Blender MCP is available).
2. **Who draws it**: in Ghidra, the users of the slot table entries for the
   mesh slots (`0x0028D010 + slot * 4`, e.g. `0x0028D11C` for 0x43) —
   use `ps2kit.elf.xref` too, Ghidra may have no references for them. Does the renderer build GIF
   packets on the EE, or send the vertices to VU1? Look for VIF `MPG`.
3. **Overlays in Ghidra**: import `AREA00.BIN` (MWo3 body at 0x00826080)
   into the same project, as a separate program or an overlay block.
4. **Text command n**: find the reader of the text slot (`0x3F` →
   `0x0028D10C`) and the interpreter of the `{3, x, n, -1}` commands.
5. **Name the SDK** in the Ghidra project: start from the functions already
   identified by behaviour (sceCdSearchFile `0x00111C28`, sceCdRead
   `0x00112440`, sceDma* `0x00101BB8`/`0x00101F08`/`0x00102468`) and write
   the names back with a script.
6. **Sound banks** if time allows: the header before `SShd`.

Captures that would still help (PCSX2): a GS dump of the first room, to
compare against `ext_tex.py`, and a savestate in area 00 to check the slot
table at `0x0028D010` against the index.
