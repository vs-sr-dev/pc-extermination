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
and others, the "model" family) are lists of 64-byte vertices whose first
quadword is the **TEX0_1 register of that vertex's texture**, upper half zero:

| Off | Content |
|---|---|
| 00 | u64 TEX0, u64 0 |
| 10 | f32 s, t, q, 0 — s and t in 0–1, inset by half a texel |
| 20 | f32 ×4, not decoded (often 1, 0, 0, 0) |
| 30 | f32 x, y, z, w — w is ±1 with flag bits in the low mantissa |

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
| 0x1B80–0x1BFF | character page, one of five variants (face, uniform with "SECURITY"/"F.S" patches, mutated tissue); slot 6 is a 256×32 half page, 7–10 are 256×64 | section 3, slots 6–10, chosen by the area loader |
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

**Observed**. The first pack of most room records. A small header (0x3C–0x6C
bytes, containing counts and offsets) followed by an `SShd` header whose
fields are all 0xFFFFFFFF past the first few, then SPU-ADPCM sample data.
Driven by the custom IOP driver `sndn2_driver`. Not decoded yet.

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
command. Every command in every area is `{3, 1, 0, -1}` followed by
`{3, 0, n, -1}`, 134 pairs in all, and they sit on the first line of a radio
conversation ("Dennis." / "Qui, Roger."). n runs from 3 to 77 and repeats
within and across areas (n = 32 opens two different conversations in area
00). **n is not a voice clip** (178 clips; durations do not match the lines)
nor a music track (66). Candidates: a portrait/expression, a jingle or sound
effect, a camera. To be settled in the code. The section 57 tables have a
different header.

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

## Resource families seen in areas

Not decoded; listed so later sessions can name them. The first 16 bytes are
enough to sort nearly every resource into one of these:

| Family | Header pattern | Guess |
|---|---|---|
| model | `u32 n, u32 qwc, u32 k, u32 bytes (= qwc·16 + 0x40), 0, floats…` | meshes; 64-byte vertices each carrying TEX0 (see GS section) |
| offset table | `u32 n, u32 0x10/0x20…, u32 offsets…, 0xFFFFFFFF` | animation or event sets |
| keyed | `u32 n, 0x01xx0000, 0x00040078, floats near ±1` | skeletons / keyframes (quaternions?) |
| path | `u32 n, 0x0001xx00, 0xFFFE001C, floats` | cameras or paths |
| GS | DMA tag `…6007`/`…7807` + VIF DIRECT | textures |

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

Text and data follow at 0x40. Tool: `python -m ps2kit.mwo3`.
