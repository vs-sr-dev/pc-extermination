# Attack plan

How to get from a PAL disc to a native PC build, and what session 1 found
that shapes the route.

## What session 1 established

* **The data side is friendly.** One index format tiles all game data;
  movies, music and voice are standard SDK formats and already extract. Text
  is plain cp1252. Nothing is compressed or encrypted so far.
* **The logic is code, not script.** Each area has its own CodeWarrior
  overlay of native MIPS (7–28 KB of code each). There is no bytecode
  interpreter to reimplement: gameplay lives in about 2 900 functions in the
  executable plus about 370 in the overlays.
* **The code is compiler output.** CodeWarrior C, one toolchain, SDK
  libraries from 2000 linked statically. Instruction mix: heavy MMI (the
  compiler uses `por` for every register move), about 1 800 VU0 macro-mode
  instructions for vector maths, 128-bit `lq`/`sq`. No evidence yet of
  hand-written assembly beyond the SDK.
* **The hard hardware is the usual PS2 trio**: GS rendering driven by
  prebuilt DMA/GIF packets, VU1 microcode for geometry (to be confirmed), and
  a custom IOP sound driver (`sndn2_driver`) talked to over SIF RPC.

## The route: static recompilation plus high-level replacement

Three options were weighed.

| Route | Verdict |
|---|---|
| **Reimplement the engine** from formats, as for RPG Maker 3 | Poor fit. RPG Maker 3's behaviour is data; Extermination's is ~3 300 functions of game-specific C. Rewriting them by hand from disassembly is years of work. |
| **Ship an emulator** | Not a port. |
| **Static recompilation** of the EE code to C/C++, with a runtime that replaces the hardware at the SDK boundary | **Chosen.** The code is small, single-toolchain and C-generated, which is the best case for recompilation. Game logic runs unmodified; effort goes into the platform layer, which is reusable. |

Static recompilation does not remove the hardware problem, it moves it. The
recompiled code still writes GIF packets, kicks DMA, talks to the IOP. The
runtime answers those at the highest level that works:

* **SDK calls, not registers.** Identify libcdvd, libpad, libmc, libgraph,
  libdma and libipu functions by signature and replace them wholesale:
  `sceCdRead` becomes a file read, `scePadRead` SDL input, `sceMc*` files
  in a save folder, IPU/MPEG playback a movie player.
* **Rendering** is the big one. First step is a GS packet interpreter that
  turns GIF primitives into modern draw calls (a "GS HLE"). Once the game's
  own draw functions are known, replace them directly with native calls, which
  also opens the door to higher resolutions and widescreen.
* **VU1**: models do go through VU1 microcode (22 programs). Either
  interpret them, or, better for a port, render the mesh format natively
  (decoded in sessions 3–4) and skip VU1.
* **Sound**: the sequencer is EE code and gets recompiled with the rest; what
  reaches the IOP are plain voice commands (pitch, volume, address, ADSR, key
  on/off) through `0x001157F0`. Replacing that one function with a native
  48-voice SPU mixer fed by `ps2kit.adpcm` covers all effects.

## Phases

### Phase 1 — assets, completely (sessions 2–4)

Understanding every format first makes phases 3–4 debuggable: when the port
draws a wrong model, we will know what it should have drawn.

1. ~~**GS local-memory model**~~ — done in session 2 (`ps2kit.gsmem`);
   CSM2, PSMCT16S and Z formats not needed so far.
2. ~~**Texture extraction**~~ — done in session 2: TEX0 is in every mesh
   vertex, `tools/ext_tex.py` resolves 23 278 of 23 687 textures; the UI
   pictures (inventory, full screens) wait for their draw code.
3. ~~Text dump for all five languages~~ — done in session 1; the tables
   before the strings decoded in session 2, except the meaning of one
   command argument.
4. ~~**Sound banks**~~ split into samples in session 4; programs, tones,
   effect sequences and the real sample rates in session 5.
5. ~~**Models**~~: meshes (session 3), skeletons, animation and actor
   placement (session 4): rooms and characters export to glTF; every room
   with its actors, every creature class resolved (session 5).
6. Section map filled in: what sections 0–3, 27–57 hold.

### Phase 2 — map the executable (started in session 2)

1. Ghidra with ghidra-emotionengine-reloaded (capstone mis-decodes EE-only
   opcodes, see below); import the main ELF and each overlay at 0x00826080.
   Main ELF imported and analysed in session 2 (2 686 functions); AREA00
   imported in session 3 and again at the right base (0x008260C0: the file
   loads with its header) in session 4; all 19 as ELFs with the executable,
   seeded, in session 5.
2. ~~Name the SDK~~: 508 functions from PS2Recomp's signature database in
   session 4 (`tools/ghidra/names_SCES_502.40.tsv`, 567 names in all).
3. ~~The main loop~~ (session 5: `0x001AAF38`, one tick a vblank at least),
   ~~the area loader~~ (session 2: `0x00200710`), ~~the sound sequencer~~
   (session 5: on the EE, `0x001152D8`); the stream code and the voice
   commands to `sndn2_driver` remain.
4. Dynamic analysis in PCSX2: breakpoints on the loaders, GS dumps of a
   room, to confirm what static reading suggests.

### Phase 3 — recompile and boot (sessions ~6+)

1. Evaluate **PS2Recomp** (ran-j), an experimental EE→C++ static recompiler
   with a TOML-driven analyzer and a runtime. Session 4: it builds with
   MinGW, and fed the function map exported from our Ghidra project it
   recompiles every function of the main executable; its own analyzer,
   alone, takes the data and the VU microcode for code (the ELF has one
   section for everything). Adopted for the main executable; overlays and
   VU1 are ours to solve.
2. ~~Recompile the main ELF and all 19 overlays~~ (session 6,
   `tools/recomp/`): each overlay is its own unit with `aNN_` names; the
   runtime keeps one function table per overlay and serves the one whose
   MWo3 header is in memory, so the loader needs no hook.
3. ~~Runtime stubs until the game reaches its title screen~~ with the GS
   HLE. Session 5: the runtime builds with the generated code (a clean copy
   of PS2Recomp at `D:\Tools\PS2Recomp-ext`, generated files in
   `ps2xRuntime/src/runner`) and boots through its IRX loading and file
   lookups. Session 6: the title screen, at 50 fields a second, after fixes
   to the runtime's sprites, double buffering, frame latching, vblank
   timing and callback stacks, and one to the recompiler
   ([runtime/README.md](../runtime/README.md)).
4. Past the title: the opening movie (MPEG through FFmpeg), then the first
   area and its overlay.

### Phase 4 — the platform layer

Rendering, input, saves, audio, movies — each replacing an SDK boundary, in
roughly that order of importance for "playable".

### Phase 5 — port quality

Resolution and widescreen, frame pacing, remappable controls, and the
subtitle question: English voice with any of the five text languages, and
clean movies with soft subtitles.

## The game-agnostic toolkit, alongside

Everything above that is not specific to Extermination goes into `ps2kit/`
as it is written. See [10-ps2kit.md](10-ps2kit.md).
