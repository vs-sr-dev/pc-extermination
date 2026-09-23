#!/bin/sh
# Run ExportLoaders.java on an analysed Ghidra project, headless (Windows).
#
#   GHIDRA=D:/Tools/ghidra_12.1.2_PUBLIC JAVA_HOME=... \
#   sh tools/ghidra/export.sh build/ghidra extermination SCES_502.40 build/ghidra/out \
#       '\DATA\INDEX_' '@28cf40+c0' 'fn:200710+200260'
#
# The project is created once with the ghidra-emotionengine-reloaded
# extension installed:
#   analyzeHeadless build/ghidra extermination -import SCES_502.40 \
#       -processor r5900:LE:32:default
# Needles are passed through cmd, which splits on commas: join function
# addresses with '+'.
proj=$(cygpath -w "$1"); name="$2"; prog="$3"; out=$(cygpath -w "$4"); shift 4
here=$(cygpath -w "$(dirname "$0")")
: "${GHIDRA:?set GHIDRA to the Ghidra install directory}"
cmd //c "$(cygpath -w "$GHIDRA")\support\analyzeHeadless.bat" "$proj" "$name" \
    -process "$prog" -noanalysis -readOnly -scriptPath "$here" \
    -postScript ExportLoaders.java "$out" "$@" 2>&1 |
    grep -E "ExportLoaders.java>|ERROR|Exception"
