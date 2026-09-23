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

The title logo in section 2 is a single 256×384 transfer declared as
PSMCT32. Decoded naively as 32-bit it shows the EXTERMINATION logo, but
scrambled: the data is 8- or 4-bit texel data uploaded *through* a 32-bit
transfer, a common PS2 trick. Reading it back needs a model of GS local
memory with the per-format swizzles (PSMCT32 → PSMT8/PSMT4 reinterpretation).
That component is generic and goes into `ps2kit` (see the plan).

## Sound banks

**Observed**. The first pack of most room records. A small header (0x3C–0x6C
bytes, containing counts and offsets) followed by an `SShd` header whose
fields are all 0xFFFFFFFF past the first few, then SPU-ADPCM sample data.
Driven by the custom IOP driver `sndn2_driver`. Not decoded yet.

## Text

**Observed**. Slot `0x3F` of each area, and slots `0x40`/`0x41` of section 57.
Plain **Latin-1** (`à` = 0xE0, `ù` = 0xF9), strings NUL-terminated, `\n` for
line breaks, preceded by a header and a table of 16-byte records
(`{u32 offset?, u32 index, …}`). Example from area 00, Italian:

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

**Verified.** `STREAM\MUSIC.DAT` and `STREAM\VOICE.DAT` are headerless mono
SPU-ADPCM at 48 kHz. Every frame has flag byte 0x02, so the data carries no
track bounds. The bounds are two tables in the executable (PAL addresses):

| Table | VA | Entries |
|---|---|---|
| music | `0x0025E8B0` | 66 tracks, 206.9 min, 21 with the loop flag |
| voice | `0x0025ECE0` | 178 clips, 18.5 min |

16 bytes a track: `u32 start sector, u32 start byte, u32 size, u32 loop`.
Entry 0 is empty; both tables tile their file exactly. The stream code
(`0x001FB120`) turns a music size into time at `0.0746667 s` per sector:
3584 samples in that time is 48 000 samples/s, so mono 48 kHz or stereo
24 kHz. Stereo is ruled out by the decoded data, which stays continuous across
every candidate interleave boundary, and 48 kHz is confirmed by the voice
clips, whose 15.6 kHz line-scan whistle only lands there at that rate. (The
voice path divides the same product by 2; what that timing is for is open.)
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
