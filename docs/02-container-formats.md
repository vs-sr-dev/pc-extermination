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
| 0C | u32 | flags — bit 0: sound bank present, bit 16: GS pack present |
| 10 | u32 | uploads — number of extra (off, size) pairs (only section 27 uses it) |
| 14 | u32 | packs_size — bytes taken by the packs at the start of the record |
| 18 | u32 | subrecords (main record only) |
| 1C | u32 | count of resources |
| 20 | pairs | sound bank (off, size) if bit 0; GS pack (off, size) if bit 16; then `uploads` pairs |
| … | u32[count] | resources: `(slot << 24) \| offset`, offset relative to `offset + packs_size` |

Resource sizes are implicit: the distance to the next resource by offset, or
to the end of the record. The **slot** is a resource identifier local to the
section (the same slot number recurs across areas for the same role — `0x3F`
is always the area's text). Formats have to be told apart by content.

The pairs are always in the order sound bank, GS pack; the bits say which
are present. Records with both: 33. GS only: 24. Sound only: 2 (the two rooms
of section 23).

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

**Room pages are not PSMT8**: the same remap on `s04_r0` shows the texture
grid but scrambled contents, the look of PSMT4. PSMT4 needs a proper model of
GS local memory (block and column tables per format), the next `ps2kit`
component.

## Sound banks

**Observed**. The first pack of most room records. A small header (0x3C–0x6C
bytes, containing counts and offsets) followed by an `SShd` header whose
fields are all 0xFFFFFFFF past the first few, then SPU-ADPCM sample data.
Driven by the custom IOP driver `sndn2_driver`. Not decoded yet.

## Text

**Verified** as far as the strings go: 19 text resources in every
language (17 areas + two system tables in section 57), about 1 470 non-empty
strings each (725 in English). Tool: `tools/ext_text.py`.

Slot `0x3F` of each area, slots `0x40`/`0x41` of section 57. Inside, before
the strings, sit tables not decoded yet: a header, a table of 16-byte
per-line records, and short command records `{3, 1, 0, -1}` / `{3, 0, n, -1}`
(n = 11, 32, 65… in area 00 — possibly voice clip numbers). Then the string
table, found by its shape:

    u32 ?  u32 count  u32 pool_size  u32 1
    count × { u32 offset, u32 offset, u32 length, u32 length + 1 }
    pool: NUL-terminated strings, `\n` for line breaks

Encoding is **Windows-1252** (French `œ` is 0x9C), with **Shift-JIS pairs
led by 0x81** for a few symbols — `…` 0x8163, `／` 0x815E, `＜ ＞`
0x8183/0x8184, full-width space and `！` — so the font engine is Japanese.
Bytes 0x80, 0x8D, 0x8E, 0x8F and 0x90 are the game's own glyphs (pad
buttons, card-key symbols). Empty strings separate groups of lines, and the
English file leaves all dialogue empty. Example from area 00, Italian:

    Dennis. / Qui, Roger. / Credo ci sia qualcuno\nvivo quaggiù.

## Resource families seen in areas

Not decoded; listed so later sessions can name them. The first 16 bytes are
enough to sort nearly every resource into one of these:

| Family | Header pattern | Guess |
|---|---|---|
| model | `u32 n, u32 qwc, u32 k, u32 bytes (= qwc·16 + 0x40), 0, floats…` | VU1 mesh packets |
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
