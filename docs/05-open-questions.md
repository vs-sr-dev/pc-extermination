# Open questions

## Data

1. **Resource formats.** Five families recognised by header (model, offset
   table, keyed, path, GS — see 02-container-formats.md), none decoded. The
   slot number probably says the role; a slot → role table is the goal.
2. **How textures are read back.** GS packs upload through PSMCT32; the real
   PSM, CLUT and TEX0 settings must be somewhere else, most likely in the
   model packets.
3. **Sound bank format** — the header before `SShd`, and how programs map to
   samples. Driven by `sndn2_driver`.
4. **Text table** — the 16-byte records before the strings in slot `0x3F`.
5. **Sections 0–3 and 27–57**: roles are guesses. Sections 31–49 (one GS
   pack per area) could be maps or loading screens.
6. **Is section = area + 4 right?** It fits the four cut areas exactly; to
   be confirmed in the area loader.

## Code

7. Where the area loader lives, and how it chooses sections and sub-records.
8. Whether models go through VU1 microcode, and how many microprograms there
   are (look for VIF `MPG` in the data and in the executable).
9. The `sndn2_driver` RPC protocol.
10. What the voice timing computed at `0x001FB280` is for: it halves the
    duration that the same formula gives for music.

## Tools

11. Does PS2Recomp handle CodeWarrior output and MWo3 overlays? Evaluate
    before building anything of our own.
