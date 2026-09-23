# TODO — session 5

Session 4 closed the asset side of characters: meshes with their skeletons,
animation, spawn tables, sound samples. What is left of phase 1 is small;
phase 3 (recompilation) has started with PS2Recomp building and running.

1. **Listen** to `build/audio/listen/sfx_s04r0_{22050,32000,48000}.wav`
   (the same 12 samples at three rates) and pick the rate by ear; then decode
   the `SShd` maps and sequences so each effect gets its own rate.
2. **Every room with its actors**: run `ext_spawn.py` over all areas (each
   area's overlay from the file table at `0x0028CF40`), and resolve the
   actor classes still exported as empties (humans `0x00128C00`/
   `0x0012A5C0`, debris `0x001E4720`, `0x001551B0`).
3. **Overlays in Ghidra**: seed AREA00 with its `jal` targets and the entry
   points the executable calls (`0x001E8110`), then import the other 18
   the same way and name their functions.
4. **Animation clock**: find the main loop's vsync wait; is a tick 1/50 s?
5. **PS2Recomp, phase 3 proper**: build `ps2_runtime`, link the generated
   code, and see how far the main executable gets with stubs. Decide how
   overlays are compiled (one unit each, function tables swapped on load)
   and how VU1 is handled (interpret the 22 microprograms, or draw the mesh
   format natively).
6. **The other room microprogram** (`0x002382A0`) and the lighting in the
   skinning one (`0x00236020`), now that `ps2kit.vu` reads them.

Captures that would still help (PCSX2): a GS dump of the first room, and a
savestate in area 00 to compare the slot table at `0x0028D010` and the actor
list.
