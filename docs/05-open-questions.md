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
   per actor class. The models are resolved for all but 21 of 804 actors
   (session 5); those 21 belong to overlay classes not read yet (area 01's
   `0x00826850`, `0x008298C0`, `0x0082B3D0`, area 03's `0x00826390`, area
   13's `0x0082C560`, area 21's `0x0082AED0`). What do the flesh patch, egg pod and
   spiked growth of s03 slots 0x1A, 0x20 and 0x24 do in play, and the two globals that switch creature variants
   (`0x00813388`) and larva textures (`0x00813308`)?
1e. **The larva in a room** renders grey where the model alone renders dark
   red: its texture depends on what the room's pack leaves in GS memory, or
   on the 0x0D/0x0E choice. Compare in PCSX2.
1c. **Room geometry flag 0x2000** in w: not tested by the room microprogram
   (`0x00237D00`). Perhaps read by the CPU (collision?) or by the other room
   program (`0x002382A0`).
2. **Sound**: banks, programs, tones and effect sequences are decoded and the
   rates confirmed by ear. Open: the six samples in the two sub-banks with no
   programs (`s07_r1` b3, `s21` b2); where the `"SSsq"` sequences played by
   `0x00119650` live (music is streamed: jingles?); the effect IDs the game
   passes to `0x001FC584`; the voice command protocol to the IOP
   (`0x001157F0`, command numbers 1, 3, 5, 6, 0x0A–0x0D, 0x28, 0x33).
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

7. The VU1 microprograms: which of the 22 each draw path uploads; does the
   room draw code (`0x001D5B60`) choose the clipping program `0x002382A0`
   for grid cells that cross the frustum? Where are the three lights and
   their colours set per actor?
8. The `sndn2_driver` RPC protocol (it imports libsd and plays what the EE
   sequencer sends).

## Tools

10. **PS2Recomp and the overlays**: it recompiles the main executable, not
    MWo3 overlays. Recompile each overlay as its own unit (an ELF wrapper at
    0x00826080) and let the runtime swap function tables on load: does its
    runtime allow that?
11. **PS2Recomp and VU1**: it covers VU0 macro mode only. Interpret the 22
    microprograms, or render the mesh format natively and never run them?

## Resolved

* **Sample rates** (session 5): the EE sequencer plays each tone at 44 100 ·
  2^((key − centre)/12 + fine/192) Hz; most samples are 8, 16 or 32 kHz.
  Confirmed by ear. The session 4 bank reader started the samples 0x50 bytes
  late (the bd offset is the header's +0x18).
* **Animation clock** (session 5): one tick a main-loop pass, 1/50 s, with no
  frame skip.
* **Overlays in Ghidra** (session 5): all 19 imported as synthetic ELFs with
  the executable (`ps2kit.mwo3 --elf`), seeded with `ps2kit.mwo3.seeds()`,
  analysed in about 20 s each.
* **VU1 lighting and clipping** (session 5): the skinning program lights
  vertices with three directional lights and an ambient term (libvu0's light
  and colour matrices, per bone); `0x002382A0` is a triangle clipper.
* **The "humans"** of `0x00128C00`/`0x0012A5C0` (session 5): larvae, the
  basic enemy; the "debris" of `0x001E4720` is a sprite emitter.

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
