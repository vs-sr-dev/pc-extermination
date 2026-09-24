# TODO — session 7

Between sessions 6 and 7 the Evergrace probe ran on the same runtime and
fixed seven more runtime bugs (listed in `runtime/README.md`); Extermination
still reaches its title with them. Session 6 took the recompiled game from
its first stall to the title screen at full speed (50 fields a second),
fixed four display bugs, a stack collision and a recompiler bug on the way,
and recompiled all 19 overlays.
"Nouvelle partie" stops in the opening movie. Build and run as in
[runtime/README.md](../runtime/README.md); drive the game with
`PS2X_PAD_SCRIPT` (at full speed the title is up by tick ~4300; Cross at
4600 starts a new game).

1. **Movies**, with Evergrace as the second case. The Evergrace probe
   (`pc-evergrace` session 2) took its movie much further and showed where
   the runtime's libmpeg stands:
   * FFmpeg decodes the pictures and the player uploads them to GS memory
     (the Crave logo is intact at page 140);
   * the player waits on its **own** machinery around libmpeg, which the
     HLE did not drive: two threads at priority 0 (rejected until now), the
     `sceMpegCbBackground` callback that feeds the movie's PCM to the IOP
     (now called from `sceMpegGetPicture`), and `sceMpegCbNodata`, which
     reads `D4_MADR` to see how far the IPU has consumed the game's
     bitstream ring and chains more DMA to channel 4. Without an IPU model
     that ring never drains and the player cannot finish; the final sprite
     pass from the uploaded picture into the field buffers also draws
     nothing yet.
   Extermination streams with `sceCdSt*` (not `sceRead`); its tree is built
   without the runtime's MPEG traces, so whether its pictures decode is not
   known yet. Plan: configure with `-DPS2X_ENABLE_AGRESSIVE_LOGS=ON`, check
   which callbacks Extermination registers (`sceMpegAddCallback` types,
   `0x00108DB0` for the stream ones) and whether it too drives the IPU
   itself. The generic fix is probably a small IPU-side model: let the
   FFmpeg decoder "consume" the game's ring (advance `D4_MADR`/`QWC`,
   complete channel 4) instead of reading PSS behind the game's back.
   A skip remains the fallback (Evergrace has one: `PS2X_SKIP_MOVIES`).
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
