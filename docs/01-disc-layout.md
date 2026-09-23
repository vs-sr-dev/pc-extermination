# Disc layout

Extermination, PAL, SCES-50240 (Deep Space / SCEE, 2001). One DVD-5,
3.2 GB used, 86 files. Every file is sector aligned; the game addresses the
big ones by LSN after one `sceCdSearchFile`.

```
SYSTEM.CNF          BOOT2 = cdrom0:\SCES_502.40;1  VER = 2.00  VMODE = PAL
SCES_502.40         1.5 MB   main executable (CodeWarrior, overlays)
OVERLAY\AREA*.BIN   19 x 2-50 KB   per-area code overlays (MWo3)
DATA\INDEX_xx.IDX   5 x 116 KB     index, one per language
DATA\DATA_xx.DAT    5 x 235 MB     all game data, one per language
STREAM\MUSIC.DAT    325 MB   66 music tracks, raw SPU ADPCM, stereo 48 kHz
STREAM\VOICE.DAT    29 MB    178 voice clips, raw SPU ADPCM, mono 48 kHz
MOVIE_xx\*.PSS      5 x 9 movies, MPEG-2 640x480 25 fps + PCM 48 kHz stereo
IRX\*.IRX, IOPRP20.IMG   IOP modules and the IOP replacement image
EXTER1.DAT          43 MB    MPEG-2 teaser, never referenced (see curiosities)
```

Language suffixes: `BR` (English — British), `FR`, `GE`, `IT`, `SP`.

## What is per-language and what is not

| Content | Per language? | Evidence |
|---|---|---|
| Game data | yes, but only text differs | The IT and BR indices differ in 238 bytes. Every structural difference is a size or offset shifted by the text resource (slot `0x3F` of an area, `0x40`/`0x41` of section 57). |
| Voice | **no** | One `VOICE.DAT`, so one spoken language for every version — English, judging by the English movies being the ones without subtitles. Other languages get subtitles. |
| Music | no | One `MUSIC.DAT`. |
| Movies | partly | 5 of 9 are byte-identical across languages. E001, E006S1, E39S2 and E900 differ in every language, but their audio is identical to the sample in all five: the difference is in the picture. For E39S2 it was checked frame by frame — only a subtitle band differs, burned in for IT, absent in English (`BR`). |

A port therefore needs one copy of voice, music and the five shared movies,
plus per-language text and the four subtitled movies (or one clean movie set
plus soft subtitles, if the subtitle text can be recovered — the English set
has none burned in).

## Executable and overlays

`SCES_502.40` is linked by **Metrowerks CodeWarrior for PS2** (`.comment`:
`MW MIPS C Compiler (2.3.1.01)`). One PT_LOAD maps file offset 0x300 to
`0x00100000`; the code ends near `0x00231370`, data and bss run to `0x00826080`.

From `0x00826080` the ELF has 19 more PT_LOAD headers with no file content,
one per overlay, each with memsz = text + data + bss of that overlay. The
overlays themselves are `OVERLAY\AREAnn.BIN`, format in
[02-container-formats.md](02-container-formats.md#mwo3-overlays). All load at
the same address; one is resident at a time.

SDK libraries linked in (from their embedded version tags): libgraph, libdma,
libipu, libkernl, libcdvd, libmc, libpad, all "2000" builds. IOP modules:

| File | Module | Version |
|---|---|---|
| SIO2MAN.IRX | sio2man | 2.04 |
| PADMAN.IRX | padman | 3.02 |
| MCMAN.IRX | mcman_tool | 2.14 |
| MCSERV.IRX | mcserv | 2.10 |
| LIBSD.IRX | Sound_Device_Library | 1.04 |
| SNDN2DRV.IRX | sndn2_driver | 1.00 — the game's own sound driver |
| IOPRP20.IMG | IOP replacement romdir (SIFCMD, FILEIO, CDVDMAN, …) | |

## Sections of the data index

`INDEX_xx.IDX` holds 58 sections of 0x800 bytes; format in
[02-container-formats.md](02-container-formats.md#data-index). Together the
87 records tile `DATA_xx.DAT` exactly, in all five languages
(`tools/ext_index.py --verify`).

| Section | Contents (provisional) |
|---|---|
| 0 | system: 4 resources, 1.2 MB |
| 1 | GS pack + 1 resource |
| 2 | one GS packet: the title logo, among others |
| 3 | 45 shared resources (player, weapons, common effects — to confirm) |
| 4–26 | **areas 00–22**: section = area + 4. A main record (area-wide resources, text in slot `0x3F`) plus one sub-record per room, typically holding a sound bank, a GS texture pack and 4–30 resources |
| 9, 13, 14, 16 | **empty** — areas 05, 09, 10 and 12, which also have no overlay |
| 27 | GS packets with explicit upload descriptors (UI?) |
| 28 | six large resources of the model family |
| 29 | one 3.8 MB resource |
| 30 | GS pack + 1 resource |
| 31–49 | **19 GS-only sections — one per area** (maps or loading screens?) |
| 50–54 | resources `0x86`/`0x87` |
| 55–56 | GS-only |
| 57 | global text: menus, save, item messages |
