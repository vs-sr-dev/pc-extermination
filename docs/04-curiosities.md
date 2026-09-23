# Curiosities

Things the disc reveals that have nothing to do with making it run.

### 1. A year-old teaser rides along, unreferenced

`EXTER1.DAT` (43 MB) sits in the disc root with a timestamp of 19 May 2000,
eleven months before every other file (April 2001). Nothing in the
executable names it. It is a silent MPEG-2 program stream, 640×480 at
**29.97 fps** — NTSC timing on a PAL disc — letterboxed, 93 seconds long.
The content is pre-release: CG shots of the squad, plus in-engine footage
with a high top-down camera following two soldiers through a door and a
red-lit corridor. Most likely an old promo clip used as filler when the DVD
was mastered.

### 2. Four areas were cut, and their numbers kept

Index sections map to areas as section = area + 4. Sections 9, 13, 14 and 16
are present but empty (size zero), and exactly those four areas — 05, 09, 10
and 12 — also have no `OVERLAY\AREAnn.BIN`. The numbering was frozen before
they were dropped. Overlay numbers inside the MWo3 headers are contiguous
(1–19), so the overlays were relinked after the cut, but the file and
section numbers were not. The executable still has 23 overlay slots: at boot
it looks up a file for each, and the four cut slots name the previous area's
file again (05→`AREA04`, 09 and 10→`AREA08`, 12→`AREA11`).

### 3. Two areas with almost no code

`AREA18.BIN` and `AREA22.BIN` hold 0xC0 bytes of code each, against 7–28 KB
for the others. Either they are pure transition or cutscene areas driven
entirely by data, or placeholders.

### 4. Subtitles burned into the video

Four movies exist in five versions whose soundtracks are bit-identical: only
the picture differs. In E39S2 the Italian copy differs from the English one
in 41 frames, all in one band near the bottom — a subtitle ("Ma cosa hai
fatto!?") rendered into the video; the English copy has none. The other five
movies have no dialogue and are byte-identical in all five folders.

### 5. The voice studio's monitor is on tape

The voice clips carry a faint, steady tone at about 15.6 kHz: the line
frequency of a 625-line CRT (15 625 Hz), most likely a monitor in the
recording booth. Handy, too — it sits at the right frequency only when the
clips are played at 48 kHz, which confirmed the rate.

### 6. Three lines of Japanese in the Spanish version

The Spanish text of section 23 keeps three lines that were never translated,
still in Shift-JIS: 火が消えた ("the fire's out"), 今のうちに通り抜けられるかも
しれない ("maybe I can get through while I have the chance") and くっ　これでは
戻れないぞ ("damn, I can't go back this way"). The other languages have them
translated. The Italian text has its own small slip: "ESonia?" for
"E Sonia?", twice.

### 7. "BR" is British

The English files use the suffix `BR` (British), not `EN` or `UK`.

### 8. Save names

The executable names the memory card directory
`BESCES-50240-DS00-00` with files `EX_DATA.00`–`EX_DATA.04`. `DS` is
plausibly Deep Space, the developer.

### 9. Every vertex carries its own texture register

The room meshes store, in front of each 64-byte vertex, the full 64-bit GS
TEX0 register of its texture: 50 000–85 000 copies per room for a few
hundred distinct values. Wasteful on disc, but it made texture pairing
trivial to recover, and it means the renderer never looks a material up.

### 10. The textures are upside down

Signs such as "CAUTION! Transformer Room" read upside down in GS memory, but
not mirrored left to right: the textures are stored bottom row first
(the convention of BMP files and OpenGL), and the UVs compensate.

### 11. The Spanish logo screen is the Italian one

Every picture with lettering (title, inventory screens, warnings) differs
between the five languages, except section 41, the Deep Space logo screen,
which is byte-identical in the Italian and Spanish data.
