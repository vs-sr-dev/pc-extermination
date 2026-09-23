# Container formats

Status tags: **verified** = checked against every instance on the disc;
**observed** = consistent with what was looked at, not yet exhaustive;
**guess** = a working hypothesis.

## Data index

**Verified** on all five languages: 87 records, contiguous, covering each
`DATA_xx.DAT` to the last byte. Tool: `tools/ext_index.py`.

`INDEX_xx.IDX` is 58 sections of 0x800 bytes. Each has a main record at
+0x000 and `subrecords` more at +0x100 + 0x70·k. A record:

| Off | Type | Field |
|---|---|---|
| 00 | u32 | id — section number, or sub-record number |
| 04 | u32 | offset into `DATA_xx.DAT`, bytes, sector aligned |
| 08 | u32 | size, bytes |
| 0C | u16 | sound banks — number of sound-bank (off, size) pairs (0 or 1 on disc) |
| 0E | u16 | GS packs — number of GS-pack pairs (0 or 1 on disc) |
| 10 | u32 | uploads — number of extra (off, size) pairs (only section 27 uses it) |
| 14 | u32 | packs_size — bytes taken by the packs at the start of the record |
| 18 | u32 | subrecords (main record only) |
| 1C | u32 | count of resources |
| 20 | pairs | sound bank pairs, GS pack pairs, then `uploads` pairs |
| … | u32[count] | resources: `(slot << 24) \| offset`, offset relative to `offset + packs_size` |

Resource sizes are implicit: the distance to the next resource by offset, or
to the end of the record. Formats have to be told apart by content.

Session 1 read 0x0C as a u32 of flag bits (0x00010001); the loader code reads
it as two u16 counts, which agrees with every record on the disc. Records
with both a sound bank and a GS pack: 33. GS only: 24. Sound only: 2 (the
two rooms of section 23).

### How the game loads it (from the code)

**Verified** in the executable (Ghidra, `tools/ghidra/ExportLoaders.java`).
At boot, `0x001FF880` looks up `INDEX_xx.IDX` and `DATA_xx.DAT` for the
current language with `sceCdSearchFile` and keeps their positions at
`0x0028D000`/`0x0028D008`; the same function fills a table of 23 overlays
at `0x0028CF40`, in which the cut areas repeat the previous file (05→04,
09 and 10→08, 12→11).

The area loader `0x00200710` is a state machine driven once per frame. For
area *n* (byte at `0x00813280`) it:

1. reads `AREAnn.BIN` whole to the overlay address and flushes the cache;
2. reads index **section n + 4** (`(n + 4) * 0x800`), which confirms
   section = area + 4;
3. reads the main record's packs and hands them over: sound banks to the
   IOP, GS packs **sent as they are on DMA channel 1 (VIF1)**
   (`0x00201270`);
4. reads the main record's resources, kicks its `uploads` packets the same
   way, and fills the **slot table**;
5. if the section has rooms, does 3–4 again for the room record at
   `0x0028C840 + room * 0x70` (room byte at `0x00813281`);
6. kicks one character texture page, a resource of section 3 in slots 6–10,
   chosen from two globals (`0x002012D0`).

The **slot table** at `0x0028D010` is 256 pointers:
`table[slot] = load address + offset`. The slot is therefore a global
resource ID: an area's main record and its room fill the same table, and
the code reaches every resource as `table[slot]`. The same `(slot << 24) |
offset` walk appears in `0x001FFC10` (the boot loader, which also kicks
section uploads) and in the generic loader `0x00200260`, which places other
sections in fixed memory zones by number (29, 39–43, 50–56 and 1–3 each have
their own case).

## GS upload packets

**Observed**. Standard PS2 path-2 packets, ready to be kicked by DMA:

```
DMAtag  ret/cnt, QWC            e.g. 0x60006007
VIF     NOP, DIRECT qwc         0x10000000 0x50006006
GIFtag  A+D, 4 regs             BITBLTBUF TRXPOS TRXREG TRXDIR
GIFtag  IMAGE, qwc              raw pixels
```

**Census** (IT, all records): 65 packets, 115 image transfers, and every
one is PSMCT32, 256 pixels wide (DBW 4), mostly 256×480. The game never
uploads in the texture's own format: it ships whole 256-wide "texture pages"
as 32-bit data, and the renderer reads them back as indexed textures.

**Verified for PSMT8** on the title page (section 2, 256×384 at block
0x2A00): read back as PSMT8 it becomes a clean 512×768 index image — the
EXTERMINATION logo, the X-ray hand in its rings, `© 2001 Deep Space Inc. /
Sony Computer Entertainment Inc.`, menu glyphs — with the CLUTs stored in the
same page: 16×16 PSMCT32 rectangles at y = 352, x = 0, 16, 32, 48 (four
colour variants of the logo) and 64, in CSM1 order, alpha 0–128. For a
page-aligned upload the 32-bit and 8-bit layouts share pages and blocks, so a
closed-form remap suffices (`ps2kit.gs.unswizzle8`).

**Room pages are PSMT4.** Read through a full model of GS local memory
(`ps2kit.gsmem`) the room pages become 128×128 4-bit texture pages.

### How textures are read back: TEX0 in every vertex

**Verified** on every room. The room meshes (slots `0x43`, `0x44`, `0x72`
and others) are lists of vertices whose first quadword is the **TEX0_1
register of that vertex's texture**, upper half zero (full layout under
[Meshes](#meshes-vu1-packets)).

A room carries 50 000–85 000 such vertices, and 400–880 distinct TEX0
values. All of them are **PSMT4** (a few PSMT8) with TBW 8, sizes from 32×16
to 256×128, a 16-colour **PSMCT32 CLUT in CSM1**, CSA 0, TCC 1, TFX 0
(modulate) or 2 (highlight). Each texture has its own CBP: the CLUTs are
scattered through the same pages as the texels.

`tools/ext_tex.py --census` replays each record's GS pack into GS memory,
collects the TEX0 values and checks that texels and CLUT fall in uploaded
blocks. It builds GS memory the way the loader does: the resident set, then
the area's main-record pack, then the room's pack; an area's own resources
count as resolved if they resolve over any of its rooms. **Of 23 687
distinct textures on the disc, 23 278 resolve.** The rest are 3 false
positives and section 29's 406, which are area 00's: they resolve 100% over
any room of area 00.

**Textures are stored bottom-up**: lettering reads upside down in GS memory
(the UVs compensate). `ext_tex.py` flips its PNGs upright unless `--raw`.

### GS memory map

| Blocks | Content | From |
|---|---|---|
| 0x1B80–0x1BFF | character page, one of five variants: the squad's faces and uniforms ("SECURITY"/"F.S" patches) in the combinations a scene needs, v7 mutated tissue; slot 6 is a 256×32 half page, 7–10 are 256×64 | section 3, slots 6–10, chosen by the area loader |
| 0x1D00–0x247F | resident set: player, weapons, muzzle flashes, pickups, keycards, HUD | section 27, upload 0 (slot 0x33) |
| 0x2480–0x24FF | resident, **localised** (256×32) | section 27, upload 1 (slot 0x34) |
| 0x1D00… | inventory screen of the area, **localised** (sections 31–38, 42–49), over the resident set | GS-only sections |
| 0x2A00… | room texture pages (256×448 to 256×928 as PSMCT32) | room record GS pack |
| 0x2A00… | title (s01), logo screens (s39–41), s55/s56 | GS-only sections |

The inventory screens (checked on s34: "OGGETTI SPECIALI", item icons for
a CD, keycards, a knife, a crowbar) read mostly as PSMT8 with some PSMT4
text. No TEX0 for them exists in the data: their draw code must carry it.

**Room packs are identical in all five languages**; the title, the second
resident upload, section 30, sections 31–49 and s55 differ per language.
Section 41 (the Deep Space logo screen) is identical in Italian and Spanish.

## Sound banks

**Verified** on all 35 banks: every sub-bank header parses, all 2 996
effect sequences read to their end, and 2 112 of the 2 113 sample offsets
the tones give land on a sample start. The first pack of most room records.
Tool: `tools/ext_sound.py`.

| Off | Field |
|---|---|
| 00 | u32 total = hd size + bd size |
| 04 | u32 offset of the first sub-bank header = 0x20 + 16·n |
| 0C | u32 n, sub-banks (1–4) |
| 10 | u32 hd size (this header included), u32 bd size |
| 18 | u32 offset of the bd (= hd size) |
| 20 | n × `{u32 bd size, u32 offset of the sub-bank header, u32 kind (2 or 4), u32 0}` |
| … | n sub-bank headers, each running to the next |
| bd | n blocks of SPU-ADPCM samples, in the same order |

Session 4 read the bd from `+04 + hd size`, 0x50 bytes too late: the upload
code (`0x001FBD70`) reads it from `bank + [+0x18]`. It copies each block to
IOP memory and SPU memory at a base chosen by the kind (table at
`0x00265400`): kind 2 is the room's own, kind 4 the blocks shared across
rooms. Every sample ends with Sony's end frame `00 07 77 77 …`.

### The sequencer is on the EE

`sndn2_driver` (`ps2kit.irx` reads its imports: libsd, sifcmd, thbase…)
only plays voices. The sequencer is EE code, run once a frame by
`0x001152D8` over 48 tracks and 48 voices, which sends voice commands
(`0x001157F0`: pitch, volume, address, ADSR, key on/off) to the IOP. A
sub-bank is registered with its SPU address by `0x00119528`; offsets below
are from the start of the sub-bank header:

| Off | Field |
|---|---|
| 00 | u32 ?, u32 bd size, u32 0 |
| 0C | `"SShd"` |
| 10 | u32 offset of the music programs (-1 on every bank) |
| 14 | u32 offset of the velocity table: u16, then 128 bytes (identity) |
| 18 | u32 offset of an LFO wave (64 bytes of a sine), -1 if none |
| 1C | u32 offset of the effect table |
| 20 | u32 offset of the effect channels: 16 bytes, 48 × 16-byte channel states, then u16 last program and a u16 offset per program |
| 24 | u32 offset of the program list, which the program offsets count from |

A **program** is 8 bytes — mode (0xFF: one tone per key), volume, pan, 0,
bend range, 0x7F, first key, last key — then one 16-byte **tone** per key:

| Off | Field |
|---|---|
| 0 | u8 lowest, highest voice |
| 2 | u8 centre note, s8 fine tune in 1/16 semitone |
| 4 | u16 sample offset in the sub-bank's bd / 8 |
| 6 | u16 ADSR1, u16 ADSR2 |
| A | u8 ?, volume, pan, bend range, 0x7F, flags (1, 2 reverb, 0x10, 0x20, 0x40, 0x80) |

The **effect table** is `u16 last group`, then a u16 offset (from the table)
per group of `u16 last index` and a u16 offset per sequence. The game
starts an effect with `0x00119EA0(bank, group, index)` (called from the
effect API at `0x001FC584`). A sequence is MIDI-like, with a variable-length
delta after each event:

| Event | Meaning |
|---|---|
| `a0 key velocity program` | key on (velocity 0: key off) |
| `b0 07 time value program key` | volume ramp |
| `b0 0a time value program key` | pan |
| `b0 41 time value program key` | pitch glide |
| `b0 60 a b c` | loop |
| `ff 2f 00` | end |

`0x00119650` plays the other kind of sequence, `"SSsq"` files with 0x90 notes
and key ranges; none were found in the data yet.

### Sample rates

The key picks the tone (key − first key) and, against its centre note, the
pitch: `0x00117918` reads a table of 16 steps a semitone at `0x002428F0`
(0x1000 at the centre, two typos in it), and the key-on `0x00115850` scales
the result by 44 100 / 48 000 for the 48 kHz SPU2. So a tone plays its
sample at

    44100 · 2^((key − centre)/12 + fine/192) Hz

Most tones come out at 16 049, 32 097 or 8 024 Hz: 16 000, 32 000 and
8 000 Hz rounded to the 1/16 semitone. Others replay a sample lower or
higher for variety (one room 00 sample is keyed at 7 519 and 16 881 Hz);
some silent tones (volume 0) play at 5 kHz. Played this way the room 00
effects sound right (**confirmed by ear**, session 5); session 4's 22 050 Hz
was simply the closest of the rates tried. `ext_sound.py --wav` writes each
sample at the rate of the tone keyed most often; `--tones` lists them all.

2 125 samples, 2 113 keyed by a tone. The other 12 are the same 6 samples in
two sub-banks with no programs (`s07_r1` b3, `s21` b2): open.

## Text

**Verified** as far as the strings go: 19 text resources in every
language (17 areas + two system tables in section 57), about 1 470 non-empty
strings each (725 in English). Tool: `tools/ext_text.py`.

Slot `0x3F` of each area, slots `0x40`/`0x41` of section 57. An area's text
resource (**verified** on all 17 areas):

    u32 cmd_offset  u32 lines  u32 cmd_size  u32 0x10       header
    lines × { u32 cmd_off, u32 cmd_index, u32 cmd_bytes, u32 cmd_bytes }
    cmd_size bytes of 16-byte commands, at cmd_offset
    the string table (lines entries)

The per-line records point into the command table the same way the string
table points into its pool (offset, index, length); most lines run no
command. A command is `{u32 type, u32 value, u32 character position, u32
extra}`, applied by the text renderer (`0x001FE9E0`) when it reaches that
position in the string: **style runs**.

| Type | Effect |
|---|---|
| 2 | colour = palette[value] (palette at `0x002704F0`) |
| 3 | sets byte +5 of the text state to value × 8 — on (1) / off (0); most likely the italic slant |
| 4 | colour = palette[value], and byte +5 = extra × 8 |

The disc only uses type 3. 134 pairs in Italian: `{3, 1, 0}` then
`{3, 0, n}` with n the line's length (131 of 134) style **a whole radio
line**; the others style **single words** ("Finché *cerchi* di
dimenticare", "*acqua*", the code "*YS-4921*" in French). Session 2's
voice-clip hypothesis was wrong: n = 32 on two lines is two lines of 32
characters. The section 57 tables have a different header.

The string table is found by its shape:

    u32 ?  u32 count  u32 pool_size  u32 1
    count × { u32 offset, u32 offset, u32 length, u32 length + 1 }
    pool: NUL-terminated strings, `
` for line breaks

Encoding is **Windows-1252** (French `œ` is 0x9C), with **Shift-JIS pairs
led by 0x81** for a few symbols — `…` 0x8163, `／` 0x815E, `＜ ＞`
0x8183/0x8184, full-width space and `！` — so the font engine is Japanese.
Bytes 0x80, 0x8D, 0x8E, 0x8F and 0x90 are the game's own glyphs (pad
buttons, card-key symbols). Empty strings separate groups of lines, and the
English file leaves all dialogue empty. Example from area 00, Italian:

    Dennis. / Qui, Roger. / Credo ci sia qualcuno
vivo quaggiù.

## Meshes (VU1 packets)

**Verified** on the whole disc: 26 999 objects, 917 000 triangles, every
object's batch count matching its header. Tool: `tools/ext_mesh.py`
(statistics, glTF export with textures); VIF walker `ps2kit.vif`.

A mesh resource is one object, or `u32 count, u32 offset[count]` and the
objects. The meshes are VIF1 packets for **VU1 microcode**, stored ready to
send:

| Off | Field |
|---|---|
| 00 | u32 batches |
| 04 | u32 qwc of the VIF stream |
| 08 | u32 **bones** (1–47; for room geometry, the table size instead) |
| 0C | u32 offset of the **rest skeleton** = 0x40 + qwc·16, just after the VIF data |
| 10 | u32 0 (3: 11-qword vertices) |
| 14 | f32 min x, y, z |
| 20 | f32 ? (radius or distance) |
| 24 | f32 max x, y, z |
| 30 | VIF: per batch `NOP`/`MSCAL 0`/`MSCNT`, NOPs, `STCYCL 4,4`, `UNPACK V4-32` (FLG, double-buffered), and a final `MSCNT` |
| [0C] | per bone, 0x50 bytes: u32 index, i32 parent (-1: root), 8 bytes 0, the bone's local 4×4 matrix (VU0 layout, translation in the last row) |

A batch is 32 vertices. A vertex is 4 quadwords (props, rooms, bodies) or 11
(the heads of section 3: the same 4, then 7 zero quadwords of workspace for
the microprogram):

| qw | Content |
|---|---|
| 0 | u64 TEX0 of its texture (0: untextured), u64 0 |
| 1 | f32 s, t, q, 0 |
| 2 | f32 normal (props, characters) **or** vertex colour 0–1 (room geometry, pre-lit) |
| 3 | f32 x, y, z, w; w = ±1 with flags and a bone address in the low mantissa bits |

The low 16 bits of w (**verified in the microcode**, session 4):

* **bits 3–9: bone × 8**. The skinning microprogram loads them with `ilw`
  and uses them as the VU1 address of the bone's matrices (8 qwords a bone).
  Positions and normals are **local to that bone**; one bone per vertex.
  VU1 data memory wraps at 1024 qwords, so the flag bits do not disturb the
  address.
* **0x8000**: the vertex closes no triangle. The room microprogram adds a
  constant to the output w, setting the GS ADC bit.
* **the sign of w** (with 0x4000) gives each triangle's winding: 99.8% of
  prop triangles and 99.4% of character triangles face their normals with
  this rule. The room microprogram does not test it (no winding cull).
* **0x2000** (room geometry): not tested by the room microprogram.

**Lighting and clipping in the microcode** (session 5). The skinning
program (`0x00236020`) gets 8 qwords a bone: a 4×4 position matrix, then 3
rows of a **light matrix** (the directions of three directional lights,
turned into bone space), and per draw a colour matrix (VU1 1013–1016: three
light colours and the ambient). A vertex's colour is ambient + Σ max(0,
N·Lᵢ)·Cᵢ, clamped to 255 by adding 2²³ and taking the mantissa (no `ftoi`):
libvu0's normal-light and light-colour matrices. Both it and the room
program reject a triangle whose three vertices lie outside one clip plane;
the room program's companion `0x002382A0` also clips the ones that cross a
plane (Sutherland–Hodgman against x, y and w, in four MPG blocks) and kicks
the polygon it makes. A port drawing natively needs the lighting formula and
none of the clipping.

Batches pad with repeats of the last vertex. **The world is y up**, like the
characters: every actor of room 00 stands on the lowest surface below it,
with the rest of the room above (session 3 read it as y down and exported
the rooms upside down).

**Where they are:**

| Slot | Content |
|---|---|
| 0x44 (rooms) | room geometry: entry 0 is a **grid** (header of 8 words: 32 × 32 cells, cell sizes, origin; then 4 object indices per cell, ≤ 0 empty), the rest ~1 100 objects in world coordinates with vertex colours. The draw code (`0x001D5B60`) walks the grid and culls each object's box on VU0 (`vclip`) |
| 0x43 (rooms) | ~40 props (doors, crates, tracks, ladders, corpses…), up to 13 bones |
| 0x35 (section 27) | 126 **resident models**: pickups, cases, weapons |
| 0x72 and others (rooms) | the area's creatures, skinned (30 bones in area 00) |
| section 28, 0x39–0x3E | the squad's **bodies** (21 bones, head included): 0x39 (page v6) and 0x3E (v10) in the black "SECURITY" suit, 0x3D (v8) and 0x3C (v9) in the navy "F.S" parka, 0x3B (v7) the mutated one |
| section 3, 0x16–0x19 | four high-detail **heads** (1 131 triangles, 11-qword vertices) |
| section 3, others | small props, weapons |

Some corpses carry a placeholder TEX0 (a purple glyph at 0x1FB0) that the
code replaces at run time.

**Each squad body renders right over one character page**, the variant in
brackets above, so the two globals that choose the page (`0x00813287`,
`0x008137E0`) choose which squad members a scene shows.

## Skeletons and animation

**Verified** on the squad (459 animations), the area creature and every
enemy set exported (11 models); read in the code (`0x001C6BD0`–`0x001CA130`,
named in `tools/ghidra/names_SCES_502.40.tsv`). Tool: `tools/ext_anim.py`
(skinned glTF, one glTF animation per game animation).

Every mesh carries its **rest skeleton** (above). An **animation set** is a
resource `u32 n, u32 offset[n]` (the "offset table" family of session 3);
each animation:

| Off | Field |
|---|---|
| 00 | u16 bones, u16 frames |
| 04 | u16 at the end: 0xFFFF loop, 0xFFFE hold, else the animation to chain to (54→53, 94→95, …) |
| 06 | u16 frames of the blend into the chained animation |
| 08 | u32 ×3: offsets of the rotation, translation and scale key blocks |
| 14 | u32 events (0: none): u16 count, then `{u16 frame, u16 flags}` (flags 5, 8, 9 in the enemy sets) |
| 20 | i32 parent[bones], parents first |

A key block is `u32 offset[bones]`, then one track per bone. A key is 12
bytes: 80 bits of packed floats (IEEE layout, bias 127) and a u16 frame;
frame 0xFFFF ends the track:

| Track | Packing | Unpacked by |
|---|---|---|
| rotation | 4 × 20 bits: sign, 8 exponent, 11 mantissa → quaternion x, y, z, w | `0x001C8CC0` (`<< 12`) |
| translation | 3 × 26 bits: sign, 8 exponent, 17 mantissa; 2 bits spare | `0x001C8DC0` (`<< 6`) |
| scale | the same; the top spare bit of a key clears the bones' velocities | `0x001C8DC0` |

Keys are sparse (every track has frame 0 and the last two frames) and are
interpolated linearly, rotations by `0x001CA890`. A bone's local transform
is T · R · S on its parent. The game's matrices are row-vector (the VU0
library's layout), so **in column-vector terms the stored quaternion is the
conjugate**. Character space is y up with the feet on the root; the squad's
hips sit 10.9 units up.

The clock: `0x001C6CE0` advances an actor by a step, 1.0 a tick normally
(2.6 and 1.6 in some states of the squad's behaviour), counting frames down;
at the end it loops, holds, or chains with a blend. **A tick is one pass of
the main loop, 1/50 s** (session 5): the loop at `0x001AAF38`–`0x001AB140`
clears the vblank counter `0x00813A18` (incremented by the vblank callback
`0x001AB150`), updates and draws, waits for at least one vblank, sets the
half-line offset of the current field and puts the display environment. No
frame skip and no scaling by elapsed time: when a frame overruns a field,
the game slows down.

The actor holds its set at +0x40 and the index at +0x2C; the squad's first
animation comes from a per-member table at `0x00249580`. Pairing sets and
models by bone count inside a record works for every set tried:

| Set | Bones | Models |
|---|---|---|
| s28 0x3A (459) | 21 | the squad, s28 0x39–0x3E |
| rooms 0x71 (57) | 30 | the area creature 0x72 (also 0x74, 0x6E, 0x70) |
| 0x7C (20) | 24 | 0x79, 0x7B: bats |
| 0x84 (54) | 29 | 0x82, 0x83: tall mutants, one holding a rifle |
| 0x78 (41) | 22 | 0x75, 0x77: crawlers |
| 0x7F (38) | 33 | 0x7D, 0x7E: dogs |
| s21 0x9B (30) | 44 | 0x9C: the armed boss |

The mixed sets in slots 0x96–0x9C hold one-off scenes.

### Placement

Room geometry needs none. Props, pickups and characters are **actors**,
created from **spawn tables** when a room starts. **Verified** in the code
(`0x001B6E30`, `0x001B70E0`) and on room 00. Tool: `tools/ext_spawn.py`.

    0x0024E3A0  u32 per area: address of a room table
    room table  u32 per room (the count is the index's): address of a list
    list        u32 addresses of spawn tables, 0-terminated
    spawn table 44-byte records up to a first u16 of 0xFFFF

The addresses point into the area's overlay or into the executable. Area 00's
rooms 0 and 1 share one table of 61 records at the start of the overlay's
data (`0x00829B00`); room 2 has two. A record:

| Off | Field |
|---|---|
| 00 | u16 condition: 0 always; 1 unless flag p is set (a pickup taken); 2–6 tests on the tables at `0x008132D8`/`0x00813358` |
| 02 | u16 p: low byte → actor +0x9A, the actor's flag; high byte, the condition's index |
| 04 | u16 class, allocated by `0x001B0260` |
| 06 | u16: low byte → actor +0x03, high byte → +0x2E |
| 08 | u16 **model index** → actor +0x0D |
| 0A | u16 → actor +0x0E |
| 0C | u16, u16 → actor +0x54, +0x56 |
| 10 | f32 x, y, z |
| 1C | f32 rotation x, y, z (radians) |
| 28 | u32 behaviour function, run every frame |

The actor's matrix is T · Rz · Ry · Rx · S (`0x001C9CA0`). Behaviours choose
the model on their first frame, and every path ends in `0x001CADD0`, which
sets the mesh at actor +0x44:

| Setter | Mesh |
|---|---|
| `0x001B1590` | `table[0x35][model]`, resident |
| `0x001B1670` | `table[0x43][model]`, the room's props |
| `0x001B1880(actor, slot, anim slot)` | `table[slot]`; the creatures' class inits pick the slot from the model byte |
| `0x001D1470(actor, mesh)` | slots 0x1A and 0x20 of section 3 |

The classes, from the behaviour addresses in the spawn records (**verified**
by reading each class init; `CLASSES` in `ext_spawn.py`):

| Behaviour | Class | Mesh (animations) |
|---|---|---|
| `0x0015AFB0` | pickup | 0x43 if (+0x03 & 0xF) = 1, else 0x35 |
| `0x0021A0D0` | container | 0x43 if +0x03 = 0 and +0x2E = 0x28, else 0x35 (white cases: 0x72) |
| `0x0021A3F0`, `0x001C50A0` | prop | 0x43 |
| `0x001551B0` | breakable | 0x43; resident 0x22 or 0x29 once broken |
| `0x001C0EB0` | resident | 0x35 |
| `0x00128C00`, `0x0012A5C0` | **larva**, the basic enemy (15 bones) | s03 0x0D, or 0x0E when `0x00813308` = −1 (0x0F) |
| `0x0012E390` | area creature | 0x72, 0x74 with bit 7; 0x6E, 0x70 with bit 0 (0x71) |
| `0x001383B0` | bat | 0x79, 0x7B (0x7C) |
| `0x0013D2C0` | crawler | 0x75, 0x77 (0x78) |
| `0x00141D10` | dog | 0x7D, 0x7E (0x7F) |
| `0x00147380` | tall mutant | 0x82, 0x83 (0x84) |
| `0x001C1800` | a dark spiked growth, animated (guess from its look) | s03 0x24 (0x25) |
| `0x001BF490`; `0x001BFE80`, `0x001C0AB0` | a flat patch of flesh; an egg pod (guesses) | s03 0x1A; s03 0x20 |
| `0x001E4720` | sprite emitter with a sound (0x411 + model): no mesh | |
| `0x0015AB10` | volume sized from `0x00248E10`: no mesh | |

For the creatures, bit 7 of the model byte picks the second model, and the
global `0x00813388` = −1 forces it. The overlays define classes of their
own, at addresses that repeat from one overlay to the next: most are a door
and a prop pair built on `ActorInitRoomProp`, present in almost every
overlay; area 01's `0x008284D0` takes the model byte as the slot ('G' 0x47,
'K' 0x4B), area 04's `0x00826C80` slot 0x4E (0x52).

A slot resolves as the loader fills the table: the room record, the area's
main record, then the resident sections 27, 28, 3 and 0–2. `ext_spawn.py
--all` exports all 37 rooms: 804 actors, 684 with a mesh, 99 without one by
design (emitters, volumes), 21 of classes not read yet. In room 00 six larvae
feed on a corpse, a document folder beside it (**confirmed** in Blender).

A separate list of flickering lights per room is hard-coded in the
executable (`0x001F6630`, 40-byte entries: model index, translation,
rotation), drawn by `0x001F6BA0`.

## Other resource families seen in areas

| Family | Header pattern | Guess |
|---|---|---|
| offset table | `u32 n, u32 0x10/0x20…, u32 offsets…, 0xFFFFFFFF` | **animation sets** (session 4), see above |
| keyed | `u32 n, 0x01xx0000, 0x00040078, floats near ±1` | not animation (the animation parser rejects them); open |
| path | `u32 n, 0x0001xx00, 0xFFFE001C, floats` | cameras or paths (slot 0x73 of room 00 is passed to the cases' effect) |
| slot 0x42 | `u32 0x28`, then (count, offset) pairs, rectangles at floor height | collision map (read with slot 0x46 by `0x00199C60`) |
| slot 0x46 | `u32 n`, offsets with a type in the top bits (0x8, 0xA, 0xC), 52-byte records with planes and boxes | trigger volumes, portals, door planes |

## Streamed audio

**Verified.** `STREAM\MUSIC.DAT` and `STREAM\VOICE.DAT` are headerless
SPU-ADPCM at 48 kHz: music **stereo, interleave 0x400** (every sector is
0x400 bytes of L then 0x400 of R), voice **mono**. Every frame has flag byte
0x02, so the data carries no track bounds. The bounds are two tables in the
executable (PAL addresses):

| Table | VA | Entries |
|---|---|---|
| music | `0x0025E8B0` | 66 tracks, 103.4 min, 21 with the loop flag |
| voice | `0x0025ECE0` | 178 clips, 18.5 min |

16 bytes a track: `u32 start sector, u32 start byte, u32 size, u32 loop`.
Entry 0 is empty; both tables tile their file exactly. The stream code
(`0x001FB120`) turns a size into time at `0.0746667 s` per sector for voice
(`0x001FB1D0`) and half that for music (`0x001FB27C`, divided by 2.0). A
sector holds 3584 ADPCM samples, so voice runs 48 000 mono samples/s and
music 1792 per channel in half the time: stereo at 48 kHz.

The data agrees. The two 0x400 halves of a music sector differ in level and
ADPCM statistics, and decoded as L/R they pair up in time: L correlates with
the R block beside it far more than with the R block before it (score 0.34–0.70
on every track sampled, ~0 for voice; `ps2kit.adpcm.guess_layout`). Decoded
as mono, music plays at the right pitch but half speed, stuttering at the
13.4 Hz block rate. Voice has no such structure, and its 15.6 kHz line-scan
whistle lands there only at 48 kHz.

Session 1 first read the music as mono: the listening test caught it.
Tool: `tools/ext_stream.py`.

## PSS movies

**Verified** on E39S2 (video byte-identical to ffmpeg's demux, audio
identical to the sample across languages). MPEG-2 program stream, video
640×480 25 fps; audio in private_stream_1, each packet's payload prefixed
with `FF A0 00 00`, the track starting with:

    SShd  size=0x18  type=1 (PCM16LE)  rate=48000  channels=2  interleave=0x200
    SSbd  size, then 0x200 bytes of L, 0x200 of R, …

Tool: `python -m ps2kit.pss`.

## MWo3 overlays

**Verified** on all 19: header size + text + data equals the file size.

| Off | Field |
|---|---|
| 00 | `"MWo3"` |
| 04 | overlay number (1–19, link order) |
| 08 | load address (`0x00826080` for all) |
| 0C | text size |
| 10 | data size |
| 14 | bss size |
| 18 | bss start = load + text + data, aligned to 0x80 (repeated at 1C) |
| 20 | original file name, e.g. `Area00.bin` |

Text and data follow at 0x40. **The whole file, header included, is read
to the load address**, so text starts at load + 0x40 (`0x008260C0`) and data
right after it (`0x00829B00` for AREA00): every `jal` inside the overlays
lands on a function prologue with this base, none with text at the load
address. Session 3 placed AREA00's data 0x40 too low. Tool:
`python -m ps2kit.mwo3`.

The executable enters an overlay through a per-area switch of `jal`s
(`0x001E8328`–`0x001E8598`) and through pointer tables (`0x00259E9C`,
0x30-byte entries; `0x00278418`); the spawn tables hold the overlay's actor
behaviours. The 19 overlays hold 1 (areas 18 and 22: a single init) to 46
functions by `python -m ps2kit.mwo3 --seeds --host`; all are imported in
Ghidra as ELFs with the executable (session 5).
