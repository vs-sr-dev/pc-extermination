#!/bin/sh
# Export the function map of every overlay program in the Ghidra project with
# PS2Recomp's ExportPS2Functions.java, headless (Windows, Git Bash).
#
#   GHIDRA=D:/Tools/ghidra_12.1.2_PUBLIC JAVA_HOME=... \
#   sh tools/recomp/export_overlays.sh build/ghidra D:/Tools/PS2Recomp/ghidra_scripts build/recomp/ov
#
# The overlay programs are AREAnn.elf (build/ghidra/import_overlays.sh): each
# holds the host executable too, so the CSV covers both; ovl_recomp.py keeps
# the overlay's own text. The script asks for its two output files, answered
# through a .properties file next to a copy of it.
set -e
proj=$(cygpath -w "$1"); scripts="$2"; out="$3"
: "${GHIDRA:?set GHIDRA to the Ghidra install directory}"
mkdir -p "$out/scripts"
cp "$scripts/ExportPS2Functions.java" "$out/scripts/"
for p in $(ls "$1/ov" | grep -E '^AREA[0-9]+\.elf$'); do
  n=${p%.elf}
  printf 'Choose output TOML config file Save = %s\nChoose output CSV file Save = %s\n' \
    "$(cygpath -m "$out/$n.ghidra.toml")" "$(cygpath -m "$out/$n.ghidra.csv")" \
    > "$out/scripts/ExportPS2Functions.properties"
  cmd //c "$(cygpath -w "$GHIDRA")\support\analyzeHeadless.bat" "$proj" extermination \
    -process "$p" -noanalysis -readOnly -scriptPath "$(cygpath -w "$out/scripts")" \
    -postScript ExportPS2Functions.java 2>&1 | grep -E "ExportPS2Functions.java>|ERROR" | sed "s/^/$n /"
done
