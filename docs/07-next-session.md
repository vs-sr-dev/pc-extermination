# TODO — session 6

Session 5 finished phase 1 for sound and actors (real sample rates, every
room with its actors), put all 19 overlays in Ghidra, settled the clock
(1/50 s a tick) and read the VU lighting. PS2Recomp's runtime builds with our
generated code (see the session log for how far it runs).

1. **Runtime, phase 3 proper**: follow the runner's first failures; give the
   overlays a home. Every overlay is a separate unit at the same address:
   recompile each from its `ps2kit.mwo3 --elf` wrapper (text range only) and
   register its functions when the area loader reads the file (the loader is
   `0x00200710`; a hook on its "file read" step can swap the table).
2. **Sound in the port**: replace `SndVoiceCmd` (`0x001157F0`) with a native
   48-voice SPU mixer (ADPCM, pitch, ADSR, volume, pan) and let the
   recompiled sequencer drive it. Needs the command numbers: read
   `0x001157F0`'s queue and the driver side.
3. **Rendering plan**: the draw paths that upload each of the 22 VU1
   programs, and the per-actor light and colour matrices; then decide native
   drawing of the mesh format (lighting formula known) versus the runtime's
   VU interpreter.
4. **The 21 actors still without a model** (overlay classes of areas 01, 03,
   13, 21) and the six samples in the two program-less sub-banks.
5. **Sections 0–2, 29, 30, 50–57**: roles still guesses.

Captures that would still help (PCSX2): a savestate in area 00 to compare
the slot table at `0x0028D010`, the actor list, and the larva's texture in
the room (grey in our export, dark red alone).
