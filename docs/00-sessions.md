# Session log

## Session 1 — disc analysis and the route

Goal: understand how the disc is built, what is standard and what is not,
and choose a porting strategy.

Results:

* **Disc mapped** (`01-disc-layout.md`): CodeWarrior executable with 19
  area overlays, a per-language index + data pair, streamed music and voice,
  PSS movies, IOP modules including the game's own `sndn2_driver`.
* **Data index solved and verified**: 58 sections, 87 records that tile each
  `DATA_xx.DAT` to the last byte in all five languages. Records carry an
  optional sound bank and GS texture pack, then slot-tagged resources.
  `tools/ext_index.py` lists, verifies and extracts.
* **Streamed audio solved**: no headers and no end flags in the data; the
  track tables are in the executable, found by following the
  `sceCdSearchFile` of `MUSIC.DAT`. 66 music tracks (103.4 min, stereo
  48 kHz, interleave 0x400) and 178 voice clips (18.5 min, mono 48 kHz).
  `tools/ext_stream.py` extracts them to WAV.
* **Movies**: PSS with PCM audio, demuxed exactly by `ps2kit.pss`. Four
  movies are per-language with identical audio; the Italian E39S2 differs from
  the English one only by a burned-in subtitle.
* **Localisation understood**: one voice track for all (English), text in
  cp1252 per language, a genuine Italian translation.
* **Overlays**: the MWo3 format is fully described; each area's gameplay is
  native code, not script.
* **Route chosen**: static recompilation plus SDK-level replacement
  (`06-attack-plan.md`).
* **ps2kit started** (`10-ps2kit.md`): `elf`, `adpcm`, `pss`, `mwo3`,
  `fingerprint`, `gs` — the first pieces of the game-agnostic toolkit.
* **First pictures**: every GS upload on the disc is a 256-wide PSMCT32
  page (115 transfers). Read back as PSMT8 the title page gives the logo and
  copyright line, with four CLUTs beside it (`ps2kit.gs`). Room pages look
  like PSMT4: next session.
* **Text solved** for all five languages (`tools/ext_text.py`): cp1252
  with Shift-JIS symbol pairs, the font's own glyph bytes, English dialogue
  left empty.
* Eight curiosities (`04-curiosities.md`), among them an unreferenced
  pre-release teaser from May 2000 and four cut areas.

Two corrections on the way. The music was first decoded as mono: right
pitch, but a "woodpecker" stutter that the user heard at once. The stream
code had been misread too (the halving belongs to the music path, not the
voice path), and a better test — L/R pairing in time rather than plain L/R
correlation — found the 0x400 interleave on every track. That test is now
`ps2kit.adpcm.guess_layout`, run by the fingerprint on any raw ADPCM file.

And the index flag bits were first read as "pack A / pack B" by position;
tallying the pack contents over all records showed bit 0 is the sound bank
and bit 16 the GS pack, with the pairs always in that order.

## Session 2 — GS memory, every texture, and the loader

Goal: phase 1 of the plan, room textures; first steps in Ghidra.

Results:

* **GS local memory modelled** (`ps2kit.gsmem`): page, block and column
  layout of PSMCT32/24/16 and PSMT8/4/8H/4HL/4HH from plain arithmetic, write
  any transfer, read any rectangle back, CSM1 CLUTs, TEX0 decoding. Its PSMT8
  read reproduces session 1's verified `unswizzle8` byte for byte; read as
  PSMT4, the room pages came out as clean texture pages at the first try.
* **TEX0 found in the meshes**: every 64-byte vertex of the room meshes
  starts with the TEX0 register of its texture. PSMT4, TBW 8, 16-colour
  PSMCT32 CLUTs, one CBP per texture.
* **Every texture resolved** (`tools/ext_tex.py`): with GS memory built as
  the game builds it — the resident set from section 27's uploads and a
  character page from section 3, then the area's pack, then the room's —
  23 278 of 23 687 distinct textures resolve; the rest are 3 false positives
  and section 29, which resolves over area 00. PNG export, flipped upright
  (the game stores textures bottom-up: the user spotted the upside-down
  signs).
* **GS memory map**: resident 0x1B80–0x24FF, rooms from 0x2A00; room packs
  identical across languages, UI pictures localised. Sections 31–49 are
  inventory screens and full-screen pictures (content warning, "FINE",
  logo), 55 the ending.
* **Text tables decoded**: header, per-line command records, command table.
  The `{3, 0, n, -1}` commands open radio conversations, but n is **not** a
  voice clip (n = 32 opens two different conversations; durations do not
  match) nor a music track. Left open.
* **Ghidra set up**: ghidra-emotionengine-reloaded v2.1.37 installed into
  Ghidra 12.1.2; main executable imported and analysed (2 686 functions);
  `tools/ghidra/ExportLoaders.java` + `export.sh` decompile the users of a
  string, an address range, or given functions, headless.
* **The loader read from the code**: file tables at boot (`0x001FF880`), the
  area loader state machine (`0x00200710`) that reads index section
  `area + 4` (**confirmed**), kicks GS packs unchanged on VIF1, and fills a
  global **slot table** of 256 resource pointers at `0x0028D010`. The cut
  areas' overlay slots point at the previous area's file.

One correction: session 1 read the record field at 0x0C as flag bits
(bit 0 sound, bit 16 GS). The loader reads it as two u16 counts, which fits
every record; `ext_index.py` now does the same.

Ghidra's analysis created no references to the file tables at 0x0028CF40
and 0x0028D000, although the code addresses them with plain `lui` pairs;
`ps2kit.elf.xref` found them. The two tools go together.

## Session 3 — meshes, rooms in Blender, text styles

Held in the same sitting as session 2. Goal: the model format and the code
that draws it.

Results:

* **Meshes decoded** (`tools/ext_mesh.py`, `ps2kit.vif`): every mesh is a
  stored VIF1 packet for **VU1 microcode** — `STCYCL 4,4`, `UNPACK V4-32` of
  32 vertices, `MSCAL 0`/`MSCNT`. A vertex is TEX0, s/t/q, normal or
  pre-lit colour, x/y/z/w with strip flags in w's mantissa (4 quadwords;
  11 for characters, 7 of them workspace). 26 999 objects and 917 000
  triangles parse on the whole disc; the winding rule matches the normals
  on 99.4–99.8% of triangles.
* **Room 00 in Blender**: glTF export with the GS-memory textures, alpha
  masks and vertex colours; the room reads right from inside (walls,
  railings, stairs, lights). The room geometry has a 32 × 32 culling grid
  in its first entry, walked by the draw code with VU0 `vclip`.
* **Props and characters**: props are actors placed by **spawn tables at the
  head of each overlay's data** (position, rotation, behaviour function);
  flickering lights have their own hard-coded lists. Section 3 holds the
  squad's four **heads**, and its five texture pages (slots 6–10) are the
  faces in the combinations a scene needs. Bodies need the skeleton: next.
* About twenty VU1 microprograms located in the executable.
* **Text commands solved**: style runs `{type, value, character position,
  extra}` applied by the text renderer. Type 3 (italic, probably) covers
  whole radio lines and single emphasised words. Session 2's n is the
  run's end position; the "voice clip" idea was wrong. German loses two
  emphases to a bug.
* **Ghidra**: `AREA00.BIN` imported; 42 functions named from
  `tools/ghidra/names_SCES_502.40.tsv` by `ApplyNames.java` (libcdvd,
  libdma, libvu0, libc, the loaders, the room and text drawers).

The first try at characters gave piles of fragments: the stride was 4
quadwords where characters use 11. With 11 the heads came out whole; with
the wrong face page, psychedelic.

## Session 4 — skeletons, animation, spawns, sounds, VU and PS2Recomp

Goal: the six points of the session 3 plan.

Results:

* **Skeletons and animation decoded** (`tools/ext_anim.py`). Every mesh
  carries its rest skeleton after the VIF data (header +08 bones, +0C
  offset); w's low bits hold bone × 8 and positions are local to the bone.
  Animation sets are the "offset table" family: 12-byte keys of packed
  20- and 26-bit floats, rotation/translation/scale tracks, loop, hold or
  chain. The squad's 459 animations and 11 enemy models export to skinned
  glTF and play in Blender. Section 28 holds the squad's five bodies (four
  members and the mutated one), each paired with one character page.
* **Spawn tables decoded and placed** (`tools/ext_spawn.py`): the chain from
  `0x0024E3A0` through room tables to 44-byte records, read by
  `0x001B6E30`; model indices resolve to the resident set (slot 0x35) or the
  room's props (0x43). Room 00 exported with its actors.
* **Two corrections to earlier sessions.** The world is **y up**, not down:
  every actor stands on the lowest surface under it, so the room exports of
  session 3 were upside down (the exporter no longer flips). And overlays
  are loaded **with their header**: text starts at 0x008260C0, AREA00's data
  at 0x00829B00; `ps2kit.mwo3` fixed, AREA00 re-imported in Ghidra.
* **Sound banks** split into their samples (`tools/ext_sound.py`, 35 banks);
  the sample rate is not stored, so a listening test at three rates is in
  `build/audio/listen/`.
* **VU disassembler** in ps2kit (`ps2kit.vu`): 22 microprograms found through
  their DMA chains, no unknown opcodes. The room program settles the w
  flags (0x8000 = ADC; winding and 0x2000 not tested); the skinning program
  uses w's low 16 bits as the VU1 address of the bone matrices.
* **PS2Recomp built** (MinGW, analyzer and recompiler) and run. Its SCE
  signature database names 508 SDK functions and agrees with all 19 named by
  hand; the names file now has 567 entries, applied to the Ghidra project.
  With the function map exported from our Ghidra project every real
  function recompiles; the only errors are two synthetic entries in data.
  Overlays and VU1 microcode are outside its scope.

The first try at a character used an animation's frame 0 as the bind pose
and the quaternions as stored: the soldier lay on the ground in a twisted
pose. Conjugating them (the game builds row-vector matrices) stood him up in
every animation.

## Session 5 — sound rates, every room, overlays, the clock, VU, runtime

Goal: the six points of the session 4 plan.

Results:

* **Sound decoded to the note** (`tools/ext_sound.py`). The IOP driver
  imports no pitch conversion (`ps2kit.irx`, new), so the sequencer had to
  be on the EE: it is (`0x001152D8`), reading the `SShd` header directly —
  programs, 16-byte tones, an effect table and MIDI-like effect sequences.
  A tone plays at 44 100 · 2^((key − centre)/12 + fine/192) Hz: mostly 8, 16
  and 32 kHz. The user confirmed the room 00 effects by ear.
* **Every room with its actors** (`ext_spawn.py --all`): the model setter of
  each class traced from the call graph; 37 rooms, 804 actors, 684 with a
  mesh, 99 meshless by nature. The "humans" are **larvae**, the basic enemy
  (confirmed by the user, feeding on a corpse in room 00); the "debris" is a
  sprite emitter.
* **All 19 overlays in Ghidra**: `ps2kit.mwo3` now seeds functions and wraps
  an overlay with its host executable in an ELF; each imports and analyses
  in about 20 s. Their actor classes are mostly one door/prop pair repeated.
* **The clock**: one main-loop pass a tick, 1/50 s, no frame skip; fields
  are rendered with a half-line offset.
* **VU1**: three directional lights plus ambient in the skinning program;
  `0x002382A0` is a full triangle clipper.
* **The recompiled game boots.** PS2Recomp's runtime (with its IOP
  emulator) builds with our 23 000 generated files under MinGW (`-march=native`
  for its SSE4 paths, ffmpeg off, LTO link about 20 minutes). Run on
  `SCES_502.40`, it loads the six IRX modules, finds the index, the data
  and all 19 overlays with `sceCdSearchFile` (English by default; the cut
  areas repeat their neighbour's file as the table says), kicks 64
  small VIF1 packets, then goes quiet: the first stall to chase.

One correction to session 4: the bank reader took the sample data from the
end of the header, 0x50 bytes after where the upload code reads it (the
header's +0x18). The samples were cut 5 frames late, and the tones' sample
offsets could not match; with the right base 2 112 of 2 113 do. And a
stray hunch retired: 22 050 Hz was only the least wrong of three guesses.

## Session 6 — the recompiled game reaches its title screen

Goal: phase 3 proper, from the runtime's first stall to the title screen,
and a home for the overlays.

Results:

* **The "stall" was the language menu**, drawn wrong. Four runtime bugs,
  each found by dumping GS memory at a chosen vsync and reading it back with
  `ps2kit.gsmem`:
  * *Text upside down*: the game draws its sprites bottom to top, and the
    runtime's sprite rasteriser swapped the corners without their texture
    coordinates.
  * *Every other field black*: the game renders interlaced fields into two
    512 × 256 buffers at pages 0x00 and 0x40. The runtime's
    `sceGsSetDefDBuffDc` put the second draw buffer on the Z buffer (0x80),
    and its `sceGszbufaddr` read `w, h` one register late. The original
    libgraph code on the disc settled what they should do.
  * *Occasional black or half-drawn frames*: the host thread latched a frame
    whenever the vsync counter moved, racing the game's buffer flip and
    clear. Frames are now latched at vblank start on the game thread.
  * The 512 × 256 field is shown 4:3, as a television does.
* **The game ran at half speed** (22–25 fields a second) because a vblank
  waited for a field's worth of EE cycles as well as for host time. Vblanks
  now follow the host clock, at 50 Hz for PAL (the runtime assumed 60): the
  game runs at exactly 50.0 fields a second.
* **A stack collision**: the runtime carved callback stacks from the top of
  RAM, where Extermination's crt0 puts the main thread's stack (1 MB at
  0x1F00000). The first MPEG callback overwrote a saved return address and
  the game jumped into `.bss`. Callback stacks now use the far end of the
  main stack.
* **A recompiler bug**: resume points (the addresses a preempted thread
  restarts at) were not registered for code that exists only as an entry
  label, such as the sound thread's loop at `0x001FBA50`. Fixed in
  `ps2xRecomp`; 22 generated files changed.
* **Title screen reached**, in every language: language menu, violence
  warning, SCEE and Deep Space logos, the title with "Nouvelle partie /
  Charger partie / Option". The memory cards are probed on the way.
* **Overlays recompiled** (`tools/recomp/`): each of the 19 is its own unit,
  exported from its Ghidra program, names prefixed `aNN_`, 5 289 functions
  in all, no errors. The runtime keeps one table per overlay and serves the
  one whose MWo3 header is in memory, so no loader hook is needed. Not yet
  exercised: see below.
* **Tooling for the runtime** (`runtime/`): our changes as patches against
  PS2Recomp, a build without LTO (a runtime change relinks in 20 s instead
  of 20 min), scripted pad input and trace switches.

Where it stops: "Nouvelle partie" plays the opening movie (E900), and the
player waits for decoded pictures that never come; the stream stops after
33 reads, with FFmpeg (now built in) or without it. The first area, and so
the first overlay, is behind that movie.

## Between sessions 6 and 7 — the Evergrace probe

A one-session test of the toolchain on a second game (Evergrace,
FromSoftware 2000, `pc-evergrace` session 2): same Ghidra route, same
PS2Recomp, same runtime patch. It reached Evergrace's title screen, the
new-game menu and the character choice at 50 fields a second, and paid
back into this repository:

* seven runtime fixes that any game may need (`runtime/README.md`, the
  Kernel, DMA, GS and MPEG rows): Extermination still reaches its title
  with all of them;
* `tools/ghidra/SplitFarChunks.java`: small tail-jumped functions that
  Ghidra folds into their caller made PS2Recomp emit one 37 MB function;
* `tools/recomp/sync_generated.py` (copy only changed generated files, so
  ninja does not rebuild 20 000 of them) and `tools/recomp/vram_shot.py`
  (GS memory dumps to screenshots and a contact sheet);
* runtime switches `PS2X_TRACE_IO`, `PS2X_WATCH` and a list form of
  `PS2X_DUMP_VRAM`;
* a much clearer picture of the movie problem, carried into the session 7
  plan.
