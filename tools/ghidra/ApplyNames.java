// Apply a names file to the current program: rename (or create) functions
// and attach comments.
//
// analyzeHeadless <proj> <name> -process <prog> -noanalysis
//     -scriptPath tools/ghidra -postScript ApplyNames.java <names.tsv>
//
// names.tsv: address <TAB> name [<TAB> comment]; '#' starts a comment line.
//@category ps2kit
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.CodeUnit;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

import java.nio.file.Files;
import java.nio.file.Paths;

public class ApplyNames extends GhidraScript {
    @Override
    public void run() throws Exception {
        int named = 0, created = 0;
        for (String line : Files.readAllLines(Paths.get(getScriptArgs()[0]))) {
            line = line.strip();
            if (line.isEmpty() || line.startsWith("#")) continue;
            String[] f = line.split("\t");
            Address a = toAddr(Long.parseLong(f[0].replaceFirst("^0x", ""), 16));
            Function fn = getFunctionAt(a);
            if (fn == null) {
                disassemble(a);
                fn = createFunction(a, f[1]);
                created++;
            }
            if (fn == null) {
                println("cannot create a function at " + a);
                continue;
            }
            fn.setName(f[1], SourceType.USER_DEFINED);
            if (f.length > 2) fn.setComment(f[2]);
            named++;
        }
        println("named " + named + " functions (" + created + " created)");
    }
}
