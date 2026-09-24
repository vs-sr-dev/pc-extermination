// Find functions whose body is split into far-apart pieces and, with "fix",
// make each far piece a function of its own.
//
// analyzeHeadless <proj> <name> -process <prog> -noanalysis
//     -scriptPath tools/ghidra -postScript SplitFarChunks.java [fix] [gap]
//
// Ghidra sometimes folds a block reached by a branch (a shared tail, code
// after a jump table) into the function that branches to it, even when the
// block sits hundreds of KB away. PS2Recomp's exporter writes each function
// as one Start..End range, so such a function swallows everything in
// between: in Evergrace one 1 KB function became a 470 KB one with 117 000
// jump-table cases. gap: the distance (hex, default 0x1000) past which a
// piece counts as far.
//@category ps2kit
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.AddressRange;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;

import java.util.ArrayList;
import java.util.List;

public class SplitFarChunks extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        boolean fix = args.length > 0 && args[0].equals("fix");
        long gap = args.length > 1 ? Long.parseLong(args[1].replaceFirst("^0x", ""), 16) : 0x1000;
        List<Function> todo = new ArrayList<>();
        for (Function fn : currentProgram.getFunctionManager().getFunctions(true)) todo.add(fn);
        int found = 0, made = 0;
        for (Function fn : todo) {
            AddressSetView body = fn.getBody();
            if (body.getNumAddressRanges() < 2) continue;
            long end = fn.getEntryPoint().getOffset();
            List<AddressRange> far = new ArrayList<>();
            for (AddressRange r : body) {
                if (r.getMinAddress().getOffset() - end > gap) far.add(r);
                else end = Math.max(end, r.getMaxAddress().getOffset());
            }
            if (far.isEmpty()) continue;
            found++;
            StringBuilder sb = new StringBuilder();
            for (AddressRange r : body) sb.append(' ').append(r.getMinAddress()).append('-').append(r.getMaxAddress());
            println(fn.getName() + " @" + fn.getEntryPoint() + ":" + sb);
            if (!fix) continue;
            for (AddressRange r : far) {
                if (getFunctionAt(r.getMinAddress()) != null) continue;
                fn.setBody(fn.getBody().subtract(new ghidra.program.model.address.AddressSet(r)));
                if (createFunction(r.getMinAddress(), null) != null) made++;
                else println("  cannot create a function at " + r.getMinAddress());
            }
        }
        println(found + " functions with far pieces, " + made + " functions created");
    }
}
