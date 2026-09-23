// Decompile the functions that use given strings, directly or through a
// pointer table, and list every function of the program.
//
// analyzeHeadless <proj> <name> -process <prog> -noanalysis
//     -scriptPath tools/ghidra -postScript ExportLoaders.java <outdir> <needle>...
//
// Writes <outdir>/functions.tsv and <outdir>/<needle>.c with the decompiled
// users of each needle: a substring of a string in memory, "@addr[+len]"
// for the users of an address range (a table, a global), or "fn:addr+addr..."
// for the functions at those addresses themselves.
//@category ps2kit
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.TreeSet;

public class ExportLoaders extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        File out = new File(args[0]);
        out.mkdirs();
        try (PrintWriter w = new PrintWriter(new File(out, "functions.tsv"), "UTF-8")) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                w.printf("%s\t%s\t%d%n", f.getEntryPoint(), f.getName(), f.getBody().getNumAddresses());
            }
        }
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        Memory mem = currentProgram.getMemory();
        for (int i = 1; i < args.length; i++) {
            String needle = args[i];
            Set<Function> users = new LinkedHashSet<>();
            Set<String> notes = new TreeSet<>();
            if (needle.startsWith("fn:")) {
                for (String x : needle.substring(3).split("[,+]")) {
                    Function f = getFunctionContaining(toAddr(Long.parseLong(x, 16)));
                    if (f != null) users.add(f);
                }
                write(out, needle, users, notes, dec);
                continue;
            }
            if (needle.startsWith("@")) {
                String[] p = needle.substring(1).split("\\+");
                Address base = toAddr(Long.parseLong(p[0], 16));
                int len = p.length > 1 ? Integer.parseInt(p[1], 16) : 1;
                for (int k = 0; k < len; k++) collect(base.add(k), users, notes, 0);
                write(out, needle, users, notes, dec);
                continue;
            }
            byte[] pat = needle.getBytes(StandardCharsets.ISO_8859_1);
            Address a = mem.getMinAddress();
            while (true) {
                a = mem.findBytes(a, pat, null, true, monitor);
                if (a == null) break;
                // back up to the start of the string
                Address s = a;
                while (true) {
                    byte b = mem.getByte(s.subtract(1));
                    if (b == 0 || (b & 0xFF) < 0x20) break;
                    s = s.subtract(1);
                }
                collect(s, users, notes, 2);
                a = a.add(1);
            }
            write(out, needle, users, notes, dec);
        }
    }

    private void write(File out, String needle, Set<Function> users, Set<String> notes,
                       DecompInterface dec) throws Exception {
        String name = needle.replaceAll("[^A-Za-z0-9_]", "_") + ".c";
        try (PrintWriter w = new PrintWriter(new File(out, name), "UTF-8")) {
            for (String n : notes) w.println("// " + n);
            for (Function f : users) {
                DecompileResults r = dec.decompileFunction(f, 120, monitor);
                w.printf("%n// ==== %s @ %s%n", f.getName(), f.getEntryPoint());
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed");
            }
        }
        println(needle + ": " + users.size() + " functions");
    }

    // Functions referencing addr; for data references (pointer tables) follow
    // up to `depth` levels, also from the start of the table.
    private void collect(Address addr, Set<Function> users, Set<String> notes, int depth) throws Exception {
        for (Reference r : getReferencesTo(addr)) {
            Address from = r.getFromAddress();
            Function f = getFunctionContaining(from);
            if (f != null) {
                users.add(f);
                notes.add(addr + " used by " + f.getName() + " at " + from);
            } else if (depth > 0) {
                notes.add(addr + " pointed to from data at " + from);
                collect(from, users, notes, depth - 1);
                // tables are usually referenced by their first entry
                Address t = from;
                for (int k = 0; k < 64 && getReferencesTo(t).length == 0; k++) t = t.subtract(4);
                if (!t.equals(from)) collect(t, users, notes, depth - 1);
            }
        }
    }
}
