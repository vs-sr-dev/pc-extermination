# TODO — session 4

Rooms, props and textures extract (`ext_tex.py`, `ext_mesh.py`). What is
missing for a full asset picture is characters, animation and sound; on the
code side, the actors and the microcode.

1. **Characters**: find the skeleton and the animation. Suspects: the
   "keyed" family (`u32 n, 0x01xx0000, 0x00040078, floats near ±1`), the
   section 28 meshes, slot 0x71 in rooms (57 offsets). Find how batches bind
   to bones: the character draw code (users of `TableEntry` on the
   character slots) will say. Goal: one squad member assembled in Blender.
2. **Spawn tables**: decode the record fields from the code that walks them
   (start from the behaviour functions `0x00128C00`, `0x0012A5C0`,
   `0x0015B040` and the overlay entry points); then place room 00's props in
   the glTF export.
3. **Sound banks** (the pack before `SShd`): decode to WAV sets, listen.
4. **VU disassembler** in `ps2kit` for the ~20 microprograms: settles the
   w flags (0x2000, 0x4000) and the lighting, and will be needed to judge
   PS2Recomp's VU story.
5. **More names** in `tools/ghidra/names_SCES_502.40.tsv`; import the other
   overlays.
6. Start phase 3: build **PS2Recomp** and run its analyzer on SCES_502.40.

Captures that would still help (PCSX2): a GS dump of the first room, and a
savestate in area 00 to compare the slot table at `0x0028D010`.
