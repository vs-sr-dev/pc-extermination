# pc-extermination

Toward a native PC port of **Extermination** (PlayStation 2, Deep Space /
Sony Computer Entertainment, 2001), the Antarctic survival horror that never
left the PS2 and was never re-released.

This repository documents the disc and its formats, and grows the tooling for
the port. Alongside it grows **ps2kit**, a game-agnostic toolkit for PS2
reverse engineering: everything the port needs that is not specific to
Extermination.

## BYOA — Bring Your Own Assets

This repository contains **documentation and tools only**. No game data, no
executables, no assets. You need your own original disc. The work is done on
the PAL release, SCES-50240.

## Layout

    docs/     disc, format and engine analysis, and the plan
    tools/    Extermination-specific tools
    ps2kit/   game-agnostic PS2 toolkit

## Tools

Everything needs only Python 3.8+, no dependencies. Run from the repository
root.

```sh
# what is on the disc
python -m ps2kit.fingerprint E:/ --deep

# data index: list, verify against the DATA file, extract
python tools/ext_index.py E:/DATA/INDEX_IT.IDX --list --section 4
python tools/ext_index.py E:/DATA/INDEX_IT.IDX --dat E:/DATA/DATA_IT.DAT --verify
python tools/ext_index.py E:/DATA/INDEX_IT.IDX --dat E:/DATA/DATA_IT.DAT \
    --extract out/ --section 4

# music and voice tracks -> WAV
python tools/ext_stream.py E:/SCES_502.40 --list
python tools/ext_stream.py E:/SCES_502.40 --kind music \
    --stream E:/STREAM/MUSIC.DAT --extract out/music/

# all text, per language (UTF-8 out)
python tools/ext_text.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT > text_it.txt

# GS texture pages: list transfers, read one back as PSMT8 with a CLUT
python -m ps2kit.gs out/s02/slot05.bin --list
python -m ps2kit.gs out/s02/slot05.bin --t8 0 --clut 16,352 --png logo.png

# textures, meshes and rooms -> PNG / glTF
python tools/ext_tex.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT --census
python tools/ext_mesh.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT \
    --record s04_r0 --slots 44 --gltf out/room.gltf

# characters with skeleton and every animation -> skinned glTF
python tools/ext_anim.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT \
    --record s28 --slot 3A --mesh s28:39 --variant 6 --gltf out/squad.gltf

# a room with its actors placed from the overlay's spawn tables
python tools/ext_spawn.py E:/SCES_502.40 E:/OVERLAY/AREA00.BIN \
    E:/DATA/INDEX_IT.IDX --area 0 --room 0 --dat E:/DATA/DATA_IT.DAT \
    --gltf out/room00.gltf

# sound banks -> SPU-ADPCM samples as WAV
python tools/ext_sound.py E:/DATA/INDEX_IT.IDX E:/DATA/DATA_IT.DAT --list

# movies -> MPEG-2 video + WAV
python -m ps2kit.pss E:/MOVIE_IT/E001.PSS --video e001.m2v --audio e001.wav

# executable: layout, xrefs, raw reads by virtual address
python -m ps2kit.elf E:/SCES_502.40 --info
python -m ps2kit.elf E:/SCES_502.40 --xref 0x00284D08
python -m ps2kit.elf E:/SCES_502.40 --callers 0x001C6CE0

# VU microcode, from the DMA chain that uploads it
python -m ps2kit.vu E:/SCES_502.40 --dma 0x00237D00

# overlays
python -m ps2kit.mwo3 E:/OVERLAY/AREA00.BIN
```

## Status

Sessions 1–4: disc, index, streamed audio, text, textures, meshes,
skeletons and animation, actor placement and sound banks are decoded;
rooms and characters export to glTF. The main executable is mapped in
Ghidra and recompiles with PS2Recomp. See [docs/00-sessions.md](docs/00-sessions.md)
for the log,
[docs/06-attack-plan.md](docs/06-attack-plan.md) for the route,
[docs/07-next-session.md](docs/07-next-session.md) for what is next and
[docs/04-curiosities.md](docs/04-curiosities.md) for the interesting bits.

## Documentation

    00-sessions.md            progress log
    01-disc-layout.md         what is on the DVD
    02-container-formats.md   every format, with verified layouts
    04-curiosities.md         what the disc reveals about its making
    05-open-questions.md      what is still unknown
    06-attack-plan.md         the porting route
    07-next-session.md        the plan for the next session
    10-ps2kit.md              the game-agnostic toolkit

## Licence

MIT — see [LICENSE](LICENSE). This covers the documentation and tools in this
repository only. It says nothing about Extermination itself, which remains
the property of its rights holders.
