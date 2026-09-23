# Open questions

## Data

1. **Resource formats.** Five families recognised by header (model, offset
   table, keyed, path, GS — see 02-container-formats.md), none decoded. The
   slot number probably says the role; a slot → role table is the goal.
2. **How textures are read back.** Every GS upload is a 256-wide PSMCT32
   page. The title page reads as PSMT8; room pages look like PSMT4. The TEX0
   settings (base, PSM, CLUT) must be in the model or material resources.
3. **Sound bank format** — the header before `SShd`, and how programs map to
   samples. Driven by `sndn2_driver`.
4. **Text tables** — the strings are solved; the per-line records and the
   `{3, 0, n, -1}` commands before them are not. Test: are the n voice clip
   numbers, matching line order and clip length?
5. **Sections 0–3 and 27–57**: roles are guesses. Sections 31–49 (one GS
   pack per area) could be maps or loading screens.
6. **Is section = area + 4 right?** It fits the four cut areas exactly; to
   be confirmed in the area loader.

## Code

7. Where the area loader lives, and how it chooses sections and sub-records.
8. Whether models go through VU1 microcode, and how many microprograms there
   are (look for VIF `MPG` in the data and in the executable).
9. The `sndn2_driver` RPC protocol.

## Tools

10. Does PS2Recomp handle CodeWarrior output and MWo3 overlays? Evaluate
    before building anything of our own.
