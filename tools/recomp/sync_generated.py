#!/usr/bin/env python3
"""Copy PS2Recomp's generated code into a runtime tree, touching only what changed.

    python tools/recomp/sync_generated.py build/recomp/output \
        D:/Tools/PS2Recomp-ext/ps2xRuntime

.cpp files go to src/runner, .h files to include. Unchanged files keep their
timestamps, so ninja rebuilds only the unity batches that really changed
(a plain cp of 20 000 files rebuilds everything, 15-25 minutes). With
--prev, .cpp files the previous output had and the new one does not are
removed from src/runner; files the generator never writes (such as the
zz_ovl_* tables) are left alone.
"""
import argparse
import filecmp
import os
import shutil


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("output", help="ps2_recomp output directory")
    ap.add_argument("runtime", help="the ps2xRuntime directory of the build tree")
    ap.add_argument("--prev", help="previous output directory: .cpp files only there are removed")
    args = ap.parse_args()

    runner = os.path.join(args.runtime, "src", "runner")
    include = os.path.join(args.runtime, "include")
    changed = []
    names = sorted(os.listdir(args.output))
    for name in names:
        src = os.path.join(args.output, name)
        dst = os.path.join(include if name.endswith(".h") else runner, name)
        if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
            continue
        shutil.copyfile(src, dst)
        changed.append(name)

    removed = []
    if args.prev:
        new = set(names)
        for name in os.listdir(args.prev):
            if name.endswith(".cpp") and name not in new:
                path = os.path.join(runner, name)
                if os.path.exists(path):
                    os.remove(path)
                    removed.append(name)

    for name in changed[:20]:
        print("changed", name)
    for name in removed[:20]:
        print("removed", name)
    print(f"{len(names)} files: {len(changed)} changed, {len(removed)} removed")


if __name__ == "__main__":
    main()
