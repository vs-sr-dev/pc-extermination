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
| 2. Extract | Turn standard formats into standard files | `adpcm`, `pss`, `mwo3` (overlays; the file loads header included; function seeds; an ELF wrapper with the host executable), `irx` (IOP modules: REL relocation, import/export tables with SDK ordinal names), `gs` (packet walker), `vif` (VIF code walker, UNPACK expansion), `vu` (VU0/VU1 microcode disassembler, MPG uploads from VIF streams and DMA chains), `gsmem` (GS local memory: write any transfer, read back PSMCT32/24/16, PSMT8/4/8H/4HL/4HH, CSM1 CLUTs, TEX0 decoding and texture rendering) | PSMCT16S and Z formats, CSM2, TIM2, VAG/VAB, SShd banks, IOPRP romdir; memory cards via `ps2mc.py` from pc-rpgmaker3 |
| 3. Map code | What does the code do, where? | `elf`: segments, reads, lui/addiu xrefs, `jal` callers, instruction mix; Ghidra with ghidra-emotionengine-reloaded, driven headless by `tools/ghidra/ExportLoaders.java` (users of strings, of address ranges, or given functions, decompiled to files) and `ApplyNames.java` (a names file applied to the project) | SDK names now come from PS2Recomp's signature database; overlays go in as ELFs from `mwo3.to_elf`, seeded by `mwo3.seeds` through `ApplyNames.java` (a name of `-` only creates the function) |
| 4. Translate | Turn EE code into C/C++ | PS2Recomp (external), fed with the function map exported from Ghidra | overlays as separate units; a VU1 story |
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

## The VU disassembler

`ps2kit.vu` decodes both halves of a VU instruction (upper FMAC, lower
integer/load-store/branch/FDIV/EFU, and `loi` when the I bit is set) from
the encoding tables, with no dependencies. It finds microcode where games
keep it: MPG codes in a VIF stream, or in a chain of DMA `cnt` tags ending
in `ret`, which is how Extermination stores its 22 programs. Checked on all
of them (about 7 000 instructions): no unknown opcode, and the room and
skinning programs read as the vertex format predicts (TEX0 / STQ / RGBA /
XYZF2 GIF output, ADC from w's 0x8000, bone matrices addressed by w).

## Known gaps

* **capstone cannot disassemble the EE properly**: in MIPS64 mode it decodes
  `lq`/`sq` and the MMI group as unrelated MSA/DSP instructions (the move
  `por` shows up as raw bytes). ps2kit defers to Ghidra with
  ghidra-emotionengine-reloaded (installed in session 2, release v2.1.37 for
  Ghidra 12.1.2) for anything beyond xref searching.
* An overlay alone gives a disassembler nothing to start from. `mwo3.seeds()`
  collects jal targets, frame setups after returns, and code pointers in
  the overlay and the host (kept only where they land on an entry, since
  every overlay of a region shares the addresses); `mwo3.to_elf()` puts the
  overlay and the host executable in one ELF. Ghidra's analysis still
  follows host calls meant for other overlays and makes a few spurious
  functions, in data for the smallest overlays: trust the seeds.
* Ghidra's analysis created no references to some globals the code reaches
  with `lui` pairs (the file tables at 0x0028CF40 and 0x0028D000; cause not
  investigated); `ps2kit.elf.xref` finds them, so the two are used together.

## IOP modules

`ps2kit.irx` loads an IRX (a relocatable MIPS I ELF of type 0xFF80), applies
its REL relocations at any base and lists the stub tables that the IOP
loader patches (`0x41E00000` magic, library name, `jr $ra` / `addiu $0, $0,
ordinal` pairs), naming the ordinals of libsd, sysclib, thbase, intrman,
sifcmd, sifman and timrman from the public SDK headers. The import list alone
says a lot about a custom driver: Extermination's `sndn2_driver` imports no
`sceSdNote2Pitch`, which is what pointed to a sequencer on the EE.
