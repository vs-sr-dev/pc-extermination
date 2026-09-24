# Runtime

The port runs the game's code recompiled by
[PS2Recomp](https://github.com/ran-j/PS2Recomp) inside PS2Recomp's runtime
(`ps2xRuntime`). This directory holds what we change in that runtime, as a
patch against upstream commit `75d729c` ("Feature/iop emulator (#244)"), and
how to build and run it. The generated code itself is not committed: it is
made from the disc (BYOA). The same patch runs Evergrace (the second game,
`pc-evergrace`), which found the second half of the list below.

## What the patch changes

| Area | Change |
|---|---|
| Overlays | `ps2RegisterOverlayFunctionTable()`: one dense function table per overlay unit, served for the overlay whose MWo3 header (magic and number) is in memory. |
| GS | Sprites keep texture coordinates with their vertices when drawn right to left or bottom to top (text was upside down). |
| GS | `sceGsSetDefDBuffDc`: the second draw buffer follows the first instead of sitting on the Z buffer; `sceGszbufaddr` reads `(psm, w, h)` from a0–a2 as libgraph does. |
| Display | Frames are latched at vblank start on the game thread, not by the host thread at any moment (no more black or half-drawn frames); shown at 4:3. |
| Timing | Vblanks follow the host clock (50 Hz for PAL, set by `sceGsResetGraph`/`SetGsCrt`) instead of waiting for a field's worth of EE cycles. |
| Callbacks | Callback stacks are carved from the far end of the main thread's stack, not from the top of RAM where that stack lives. |
| Kernel | `SetupThread` with stack −1 (the SDK's GNU crt0) puts the stack at the end of RAM and starts the thread at its top; it returned the bottom, so the stack grew into the heap. |
| Kernel | Priority 0 is accepted by `CreateThread` and `ChangeThreadPriority` (it is the highest EE priority, where the main thread already runs). |
| DMA | A chain started with `QWC > 0` sends `QWC` quadwords from `MADR` before reading the first tag at `TADR`. |
| DMA | `MADR`, `TADR` and tag addresses with bit 31 set point into the scratchpad (offset in the low 14 bits). |
| GS | `sceGsExecLoadImage` / `ExecStoreImage` take `dbp` in GS blocks, as libgraph does; they multiplied it by 8. |
| GS | `sceGsSetDefDispEnv` fills PMODE (0x66) and SMODE2 like libgraph; left at zero, a later `sceGsPutDispEnv` switched the display off. |
| MPEG | `sceMpegGetPicture` calls the `sceMpegCbBackground` callbacks, as libmpeg does while the IPU decodes. |
| MPEG | Under MinGW, FFmpeg comes from pkg-config (MSYS2) instead of the MSVC prebuilt. |
| Build | `PS2X_ENABLE_LTO` switch: without LTO a runtime change relinks in seconds instead of twenty minutes. |
| Debugging | Environment switches, below. |

The recompiler needs one fix too (`ps2xrecomp.patch`, `git apply` in the PS2Recomp clone):
entry labels outside any function (code Ghidra kept only as a label, such as
the sound thread's loop at `0x001FBA50`) now register their resume points, so
a thread preempted inside them can resume.

## Building

MSYS2 MinGW64 with cmake, ninja, gcc and `mingw-w64-x86_64-ffmpeg`.

The patch is made with `--strip-trailing-cr` and the upstream files are CRLF,
so turn the files it touches to LF first:

```sh
mkdir PS2Recomp-ext && (cd PS2Recomp && git archive HEAD) | tar -x -C PS2Recomp-ext
cd PS2Recomp-ext
for f in $(grep '^+++ ' .../runtime/ps2xruntime.patch | awk '{print $2}'); do
    sed -i 's/\r$//' "$f"; done
patch -p0 < .../runtime/ps2xruntime.patch
# generated code of the executable (build/recomp/output): .cpp into
# src/runner, .h into include/, copying only what changed:
python tools/recomp/sync_generated.py build/recomp/output .../PS2Recomp-ext/ps2xRuntime
# then the overlays:
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

Before exporting the function map from Ghidra, run
`tools/ghidra/SplitFarChunks.java fix`: Ghidra can fold a small function
reached only by a tail jump into its caller, and PS2Recomp then recompiles
everything in between as one function (in Evergrace, 470 KB and a 37 MB
source file that took the compiler over 3 GB).

Keys: arrows, X = cross, C = circle, Z = square, V = triangle, Enter = start.
Escape closes the window.

## Debugging switches

| Variable | Effect |
|---|---|
| `PS2X_PAD_SCRIPT="450:right,460:none,500:cross"` | From each vsync tick on, hold the listed buttons (`+` joins several); replaces host input. |
| `PS2X_TRACE_PRESENT=1` | One line per latched frame: display registers, host time, a pixel checksum. |
| `PS2X_DUMP_VRAM=<tick>` | Raw GS memory and display registers of eight latches from that tick (`vram_*.bin`). |
| `PS2X_DUMP_VRAM=<t1>,<t2>,...` | One latch at each tick: a film strip of a run. `tools/recomp/vram_shot.py vram_*.bin --sheet s.png` turns the dumps into screenshots and a contact sheet. |
| `PS2X_TRACE_IO=1` | One line per `sceOpen`, `sceLseek` and `sceRead` (path, size, first word read). |
| `PS2X_WATCH=33b40c,3241f4` | With `PS2X_TRACE_PC`, the guest words at those (hex) addresses every two seconds. |
| `PS2X_TRACE_PAD=1` | Pad reads and button changes. |
| `PS2X_TRACE_PC=1` | Main thread PC, RA and SP every two seconds. |
| `PS2X_NO_DRAW=1` | Skip rasterisation (profiling). |
| `PS2X_CYCLE_PACED_VSYNC=1` | The old vblank pacing, by EE cycles. |

Configure with `-DPS2X_ENABLE_AGRESSIVE_LOGS=ON` (upstream spelling) to see the
runtime's own MPEG, SIF and GS traces (`[MPEG:DemuxPssRing]`,
`[MPEG:GetPicture:FRAME]`, ...); the Evergrace tree is built that way.
