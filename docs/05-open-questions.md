# Open questions

Resolved questions move to the bottom with the session that settled them.

## Data

1. **Resource formats.** Five families recognised by header (model, offset
   table, keyed, path, GS — see 02-container-formats.md). The model family's
   vertices are 64 bytes with TEX0, s/t/q and x/y/z/w; the second quadword
   of floats, the w flags, and how vertices form strips or triangles are
   not decoded. The slot number is a global resource ID; a slot → role
   table is the goal.
2. **Sound bank format** — the header before `SShd`, and how programs map to
   samples. Driven by `sndn2_driver`; the loader hands banks to the IOP
   through `0x001FBD00`.
3. **Text commands** — every area's text runs `{3, 1, 0, -1}` then
   `{3, 0, n, -1}` on the first line of a radio conversation. n (3–77) is not
   a voice clip or a music track. What is it? Find who interprets the
   command table.
4. **Sections 0–2, 28, 30, 50–57**: roles still guesses. 29 is a mesh
   resource drawn with area 00's pages: a cutscene, a demo, an attract
   sequence?
5. **The character page variants** (section 3, slots 6–10): what do the
   two globals that choose them (`0x00813287`, `0x008137E0`) mean? Slot 6
   is only a half page.
6. **Inventory and full-screen pictures** (sections 31–49, 55–56): no TEX0
   for them in the data. Their draw code will say how they are read (PSMT8
   and PSMT4 regions share pages).

## Code

7. Whether models go through VU1 microcode, and how many microprograms there
   are (look for VIF `MPG` in the data and in the executable). The room
   meshes carry GS registers per vertex, which suggests they are turned into
   GIF packets by the EE or VU1 rather than drawn from stored packets.
8. The `sndn2_driver` RPC protocol.
9. Name the SDK functions in the Ghidra project (libcdvd, libdma, libgraph,
   libpad…): the loader already shows `sceCdSearchFile` at `0x00111C28`,
   `sceCdRead` at `0x00112440`, and `sceDmaGetChan`/`sceDmaSend`/`sceDmaSync`
   at `0x00101BB8`/`0x00101F08`/`0x00102468`, by behaviour.

## Tools

10. Does PS2Recomp handle CodeWarrior output and MWo3 overlays? Evaluate
    before building anything of our own.

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
* **Text tables** (session 2): header, per-line command records and the
  command table decoded; only the meaning of n remains (question 3).
