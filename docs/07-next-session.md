# TODO — session 7

Session 6 took the recompiled game from its first stall to the title screen
at full speed (50 fields a second), fixed four display bugs, a stack
collision and a recompiler bug on the way, and recompiled all 19 overlays.
"Nouvelle partie" stops in the opening movie. Build and run as in
[runtime/README.md](../runtime/README.md); drive the game with
`PS2X_PAD_SCRIPT` (at full speed the title is up by tick ~4300; Cross at
4600 starts a new game).

1. **Movies**: why the player waits after 33 stream reads. The movie code is
   around `0x00203D70`–`0x00207A00`: `0x00108DB0` is
   `sceMpegAddStrCallback` (callbacks `0x002047A0` and `0x002048D0`, data
   `0x00292280`), `0x00206A80` the player's vsync handler. Follow what the
   main thread waits on and what the runtime's MPEG HLE (FFmpeg now built
   in) gives back; the pre-title play of the same movie does end. If that
   takes long, a skip (end of stream reported at once) unblocks the rest.
2. **Overlays in action**: past the movie, AREA00 loads. Watch for
   `[overlay] 1 resident`, then follow the first failures inside overlay
   code. The overlay units call the executable through the dispatcher; a
   `jal` from the executable into an overlay does not exist, but check.
3. **Sound**: replace `SndVoiceCmd` (`0x001157F0`, a 256-entry command queue
   at `0x00282340`, two banks of 0x1000 bytes, count at `0x00282300`) with a
   native mixer, or first see what the IOP emulator already plays.
4. **Rendering plan**: the software rasteriser costs about a third of the
   frame time already on menus; native drawing of the mesh format versus the
   runtime's VU1 interpreter, as in the session 5 plan.
5. **Runtime heap**: the runtime's `guestMalloc` hands out memory right
   after the executable, where the game's own `malloc` heap lives. Nothing
   has broken yet; give it a region of its own (the main stack's far end
   has room) before something does.
6. The 21 actors still without a model, the six unplayed samples, and the
   roles of sections 0–2, 29, 30, 50–57.

Captures that would still help (PCSX2): the opening movie playing (to compare
the MPEG calls), a savestate in area 00.
