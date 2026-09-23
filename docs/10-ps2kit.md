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
| 1. Recognise | What is on this disc? Which parts are standard? | `fingerprint`: magics, SPU ADPCM heuristic, GS packets, toolchain from `.comment`, SDK library versions, IRX names and versions, overlay regions, file paths named by the code | a knowledge base: each finding linked to the extractor or runtime module that handles it |
| 2. Extract | Turn standard formats into standard files | `adpcm`, `pss`, `mwo3` | GS memory model + textures, TIM2, VAG/VAB, SShd banks, IOPRP romdir; memory cards via `ps2mc.py` from pc-rpgmaker3 |
| 3. Map code | What does the code do, where? | `elf`: segments, reads, lui/addiu xrefs, instruction mix | SDK signature matching per library version, overlay-aware loader, Ghidra project generator |
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

## Known gaps

* **capstone cannot disassemble the EE properly**: in MIPS64 mode it decodes
  `lq`/`sq` and the MMI group as unrelated MSA/DSP instructions (the move
  `por` shows up as raw bytes). ps2kit needs its own R5900 decoder, or should
  defer to Ghidra with ghidra-emotionengine-reloaded for anything beyond
  xref searching.
