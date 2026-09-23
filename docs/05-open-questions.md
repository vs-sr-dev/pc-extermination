# Open questions

Resolved questions move to the bottom with the session that settled them.

## Data

1. **Resource formats.** Meshes, skeletons, animation sets and spawn tables
   are decoded (see 02-container-formats.md); the keyed, path, collision
   (0x42) and trigger (0x46) families are not. A slot → role table is the
   goal.
1a. **The heads of section 3** (slots 0x16–0x19, 11-qword vertices): the
   section 28 bodies have heads of their own, so where are these drawn?
   Close-ups and cutscenes are the guess; the 7 workspace qwords suggest a
   different microprogram.
1b. **Spawn records**: the meaning of +0x03, +0x2E, +0x0E, +0x54 and +0x56
   per actor class, and the classes whose model is not in slot 0x35 or 0x43
   (the humans of `0x00128C00`, the debris of `0x001E4720`).
1c. **Room geometry flag 0x2000** in w: not tested by the room microprogram
   (`0x00237D00`). Perhaps read by the CPU (collision?) or by the other room
   program (`0x002382A0`).
1d. **Animation clock**: one frame per tick, but is a tick 1/50 s or 1/25 s?
   The main loop's vsync wait will say.
2. **Sound banks**: the layout and the samples are out; the `SShd` maps and
   sequences are not, and without them the sample rates. Then the
   `sndn2_driver` RPC protocol (`0x001FBD00`).
3. **Text style 3**: italic, or another effect? Byte +5 of the text state
   at `0x00265854` — see what the glyph drawer does with it.
4. **Sections 0–2, 29, 30, 50–57**: roles still guesses. 29 is a mesh
   resource drawn with area 00's pages: a cutscene, a demo, an attract
   sequence?
5. **The character page globals** (`0x00813287`, `0x008137E0`): which
   squad members a scene shows (each body has its page); slot 6 is only a
   half page.
6. **Inventory and full-screen pictures** (sections 31–49, 55–56): no TEX0
   for them in the data. Their draw code will say how they are read (PSMT8
   and PSMT4 regions share pages).

## Code

7. The VU1 microprograms: all 22 disassemble (`ps2kit.vu`); the lighting in
   the skinning program (`0x00236020`) and the other room program
   (`0x002382A0`) are still to read.
8. The `sndn2_driver` RPC protocol.
9. **Overlays in Ghidra**: AREA00 re-imported at the right base
   (`0x008260C0`), but a raw import finds only 28 functions; seed it with
   the `jal` targets and the entry points the executable calls
   (`0x001E8110`), then import the other 18.

## Tools

10. **PS2Recomp and the overlays**: it recompiles the main executable, not
    MWo3 overlays. Recompile each overlay as its own unit (an ELF wrapper at
    0x00826080) and let the runtime swap function tables on load: does its
    runtime allow that?
11. **PS2Recomp and VU1**: it covers VU0 macro mode only. Interpret the 22
    microprograms, or render the mesh format natively and never run them?

## Resolved

* **How textures are read back** (session 2): every mesh vertex carries its
  TEX0. With the resident set, the area pack and the room pack in GS memory,
  23 278 of 23 687 textures on the disc resolve; the rest are 3 false
  positives and section 29, which resolves over area 00's rooms.
* **Is section = area + 4 right?** (session 2): yes, the area loader reads
  index section `area + 4`.
* **Where the area loader lives** (session 2): `0x00200710`, a per-frame
  state machine; boot loader `0x001FFC10`, generic section loader
  `0x00200260`, file tables built by `0x001FF880`. See
  02-container-formats.md.
* **Do models go through VU1?** (session 3): yes. Every mesh is a stored
  VIF1 packet of vertex batches run by `MSCAL`/`MSCNT`.
* **Text tables** (sessions 2–3): header, per-line records, and the
  commands: style runs `{type, value, position, extra}`; n is a character
  position, the end of the styled run.
* **Characters** (session 4): skeletons live in the meshes, animation sets
  are the "offset table" family, bones bind vertex by vertex through w; the
  squad's bodies are section 28.
* **Spawn tables** (session 4): the chain from `0x0024E3A0`, the record
  layout, and the model lookup (slots 0x35 and 0x43).
* **Naming the SDK** (session 4): PS2Recomp's signature database names 508
  SDK functions, agreeing with the 19 found by hand.
* **Does PS2Recomp handle CodeWarrior output?** (session 4): yes, for the
  main executable, given the function map from Ghidra.
* **Which way is up?** (session 4): y is up in the world and in character
  space.
