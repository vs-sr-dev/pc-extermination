# Runtime

The port runs the game's code recompiled by
[PS2Recomp](https://github.com/ran-j/PS2Recomp) inside PS2Recomp's runtime
(`ps2xRuntime`). This directory holds what we change in that runtime, as a
patch against upstream commit `75d729c` ("Feature/iop emulator (#244)"), and
how to build and run it. The generated code itself is not committed: it is
made from the disc (BYOA).

## What the patch changes

| Area | Change |
|---|---|
| Overlays | `ps2RegisterOverlayFunctionTable()`: one dense function table per overlay unit, served for the overlay whose MWo3 header (magic and number) is in memory. |
| GS | Sprites keep texture coordinates with their vertices when drawn right to left or bottom to top (text was upside down). |
| GS | `sceGsSetDefDBuffDc`: the second draw buffer follows the first instead of sitting on the Z buffer; `sceGszbufaddr` reads `(psm, w, h)` from a0–a2 as libgraph does. |
| Display | Frames are latched at vblank start on the game thread, not by the host thread at any moment (no more black or half-drawn frames); shown at 4:3. |
| Timing | Vblanks follow the host clock (50 Hz for PAL, set by `sceGsResetGraph`/`SetGsCrt`) instead of waiting for a field's worth of EE cycles. |
| Callbacks | Callback stacks are carved from the far end of the main thread's stack (`SetupThread` with an explicit stack), not from the top of RAM where that stack lives. |
| MPEG | Under MinGW, FFmpeg comes from pkg-config (MSYS2) instead of the MSVC prebuilt. |
| Build | `PS2X_ENABLE_LTO` switch: without LTO a runtime change relinks in seconds instead of twenty minutes. |
| Debugging | Environment switches, below. |

The recompiler needs one fix too (`ps2xrecomp.patch`, `git apply` in the PS2Recomp clone):
entry labels outside any function (code Ghidra kept only as a label, such as
the sound thread's loop at `0x001FBA50`) now register their resume points, so
a thread preempted inside them can resume.

## Building

MSYS2 MinGW64 with cmake, ninja, gcc and `mingw-w64-x86_64-ffmpeg`.

```sh
cp -r PS2Recomp PS2Recomp-ext                # or git archive
cd PS2Recomp-ext && patch -p0 --binary < .../runtime/ps2xruntime.patch
# generated code of the executable (build/recomp/output) into src/runner,
# its headers into include/; then the overlays:
python tools/recomp/ovl_recomp.py --recomp .../ps2_recomp.exe \
    --runtime .../PS2Recomp-ext/ps2xRuntime
cmake -S . -B out-dev -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_FLAGS=-march=native -DCMAKE_C_FLAGS=-march=native \
    -DPS2X_ENABLE_LTO=OFF -DPS2X_ENABLE_FFMPEG=ON \
    -DPS2X_BUILD_ANALYZER=OFF -DPS2X_BUILD_RECOMP=OFF -DPS2X_BUILD_STUDIO=OFF
ninja -C out-dev ps2EntryRunner
```

Run from the copied disc, with `C:\msys64\mingw64\bin` on `PATH`:

```sh
cd build/disc && ps2EntryRunner.exe SCES_502.40
```

Keys: arrows, X = cross, C = circle, Z = square, V = triangle, Enter = start.
Escape closes the window.

## Debugging switches

| Variable | Effect |
|---|---|
| `PS2X_PAD_SCRIPT="450:right,460:none,500:cross"` | From each vsync tick on, hold the listed buttons (`+` joins several); replaces host input. |
| `PS2X_TRACE_PRESENT=1` | One line per latched frame: display registers, host time, a pixel checksum. |
| `PS2X_DUMP_VRAM=<tick>` | Raw GS memory and display registers of eight latches from that tick (`vram_*.bin`). |
| `PS2X_TRACE_PAD=1` | Pad reads and button changes. |
| `PS2X_TRACE_PC=1` | Main thread PC, RA and SP every two seconds. |
| `PS2X_NO_DRAW=1` | Skip rasterisation (profiling). |
| `PS2X_CYCLE_PACED_VSYNC=1` | The old vblank pacing, by EE cycles. |
