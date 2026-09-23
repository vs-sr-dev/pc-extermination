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
  `sceCdSearchFile` of `MUSIC.DAT`. 66 music tracks (206.9 min) and 178 voice
  clips (18.5 min), mono 48 kHz. `tools/ext_stream.py` extracts them to WAV.
* **Movies**: PSS with PCM audio, demuxed exactly by `ps2kit.pss`. Four
  movies are per-language with identical audio; the Italian E39S2 differs from
  the English one only by a burned-in subtitle.
* **Localisation understood**: one voice track for all (English), text in
  plain Latin-1 per language, a genuine Italian translation.
* **Overlays**: the MWo3 format is fully described; each area's gameplay is
  native code, not script.
* **Route chosen**: static recompilation plus SDK-level replacement
  (`06-attack-plan.md`).
* **ps2kit started** (`10-ps2kit.md`): `elf`, `adpcm`, `pss`, `mwo3`,
  `fingerprint` — the first pieces of the game-agnostic toolkit.
* Eight curiosities (`04-curiosities.md`), among them an unreferenced
  pre-release teaser from May 2000 and four cut areas.

One correction on the way: the index flag bits were first read as
"pack A / pack B" by position; tallying the pack contents over all records
showed bit 0 is the sound bank and bit 16 the GS pack, with the pairs always
in that order.
