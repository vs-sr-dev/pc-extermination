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
