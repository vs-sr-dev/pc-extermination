# ps2kit — the game-agnostic toolkit

## The idea

No tool will port a PS2 game in one click: each game has its own engine,
formats and tricks. But a large part of every port is the *same* work,
because every PS2 game sits on the same hardware, the same SDK and a handful
of toolchains. ps2kit collects that shared part, so that each new game starts
with a report of what is already known and a set of ready solutions for it.

It is grown inside this project: every piece is written because Extermination
needed it, then kept free of Extermination-specific knowledge.

## Layers

| Layer | Question it answers | Now | Next |
|---|---|---|---|
| 1. Recognise | What is on this disc? Which parts are standard? | `fingerprint`: magics, SPU ADPCM heuristic with mono/stereo interleave detection, GS packets, toolchain from `.comment`, SDK library versions, IRX names and versions, overlay regions, file paths named by the code | a knowledge base: each finding linked to the extractor or runtime module that handles it |
| 2. Extract | Turn standard formats into standard files | `adpcm`, `pss`, `mwo3`, `gs` (packet walker), `vif` (VIF code walker, UNPACK expansion), `gsmem` (GS local memory: write any transfer, read back PSMCT32/24/16, PSMT8/4/8H/4HL/4HH, CSM1 CLUTs, TEX0 decoding and texture rendering) | PSMCT16S and Z formats, CSM2, TIM2, VAG/VAB, SShd banks, IOPRP romdir; memory cards via `ps2mc.py` from pc-rpgmaker3 |
| 3. Map code | What does the code do, where? | `elf`: segments, reads, lui/addiu xrefs, instruction mix; Ghidra with ghidra-emotionengine-reloaded, driven headless by `tools/ghidra/ExportLoaders.java` (users of strings, of address ranges, or given functions, decompiled to files) and `ApplyNames.java` (a names file applied to the project) | SDK signature matching per library version, overlay-aware import, naming the SDK in the Ghidra project |
| 4. Translate | Turn EE code into C/C++ | — | recompiler configs generated from layer 3 (for PS2Recomp or our own) |
| 5. Runtime | Replace the hardware | — | SDK-level HLE: cdvd, pad, mc, IPU/movies, SIF RPC dispatch; GS HLE renderer; SPU mixer |

The "ready-made solutions" of the original idea live at the seam between
layers 1 and 5: when the fingerprint finds, say, libcdvd 2000 and PSS movies
and CodeWarrior overlays, it should be able to say *these runtime modules
cover them* and *these parts are yours to solve* (custom formats, custom IOP
drivers, VU1 microcode).

## Principles

* Pure Python, no dependencies, for layers 1–3 — same rule as the RPG Maker 3
  tools. Layer 5 will be C/C++.
* Every format claim is tested against real discs before it goes in.
* Game knowledge stays out: a function that needs a game's table address takes
  it as a parameter.

## The GS memory model

`ps2kit.gsmem` models the 4 MB of GS local memory with plain arithmetic: the
page and block geometry of each format, the two block orders (8×4 and 4×8
blocks in a page), and one column pattern that every format packs its
pixels into (see the module docstring). It writes a host-to-local transfer
as the GS would and reads any rectangle back in any format, so the usual PS2
trick of uploading 4- and 8-bit textures through 32-bit transfers needs no
special case.

Checked on real data: its PSMT8 read of the Extermination title page equals
`gs.unswizzle8`, verified in session 1; its PSMT4 reads give clean texture
pages for every room, and 23 278 TEX0 values found in the game's meshes
render with correct colours. `Tex0` decodes the register and `plausible()`
filters candidates when hunting TEX0 in unknown data; `texture()` renders
one.

It is pure Python: replaying a 1 MB pack and reading it back takes under a
second, fine for extraction. The runtime will need the same tables in C.

## Known gaps

* **capstone cannot disassemble the EE properly**: in MIPS64 mode it decodes
  `lq`/`sq` and the MMI group as unrelated MSA/DSP instructions (the move
  `por` shows up as raw bytes). ps2kit defers to Ghidra with
  ghidra-emotionengine-reloaded (installed in session 2, release v2.1.37 for
  Ghidra 12.1.2) for anything beyond xref searching.
* Ghidra's analysis created no references to some globals the code reaches
  with `lui` pairs (the file tables at 0x0028CF40 and 0x0028D000; cause not
  investigated); `ps2kit.elf.xref` finds them, so the two are used together.
