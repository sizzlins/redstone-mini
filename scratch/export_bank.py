"""Export the banked alu4 build to .schem / .mcfunction / .html.

Hard-bounded: a fixed pickle in, files out. No compose, no sim, no search, so
there is nothing here that can hang -- the only unbounded part upstream is the
stitch, and hier_stitch kills its own child.

GATED (2026-10-05). The 10/4 handoff's next step 3, and the reason this file
mattered: a build used to be exported on nothing but a sim-green, and a
sim-green is exactly how a build can quietly overfit the simulator. Export now
runs scratch/verify2.py --diff-all first -- our sim AND cmc, per cell -- and
refuses to write anything unless both engines pass every vector and the
per-cell differential is empty. Two builds in the tree would have been caught
by this: not_full.pkl (sim cannot power a non-pin lever, cmc can -- see LOG
Finding 3) and alu4bank_ins.pkl (21619/103260 cells disagree).

The gate runs as a subprocess under a hard timeout and its exit code is
CHECKED (the opt agent's hier_verify discarded it, and certified a stale
merge.pkl that way). --force is the operator's escape hatch: it records that
the export is ungated rather than pretending it was gated.

Usage: python scratch/export_bank.py <merge.pkl> <label> [--no-gate]
                                  [--force] [--gate-timeout S]
                                  [--max-vectors N] [--recipe PATH]
"""
import os
import pickle
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)
from export import export_html, export_mcfunction, export_schem  # noqa: E402


def find_recipe(d):
    """Which recipe is this build supposed to implement? The pkl's own `recipe`
    field if it has one, else match the io pin NAMES against recipes/*.txt --
    the same auto-match sweep.py uses, because scoring a build against the
    wrong recipe is how alu4_build.pkl once looked like a physics failure."""
    r = d.get("recipe")
    if r:
        p = r if os.path.isabs(r) else os.path.join(r"D:\redstone-mini", r)
        if os.path.exists(p):
            return p
    try:
        import sweep
        io = d["io"]
        ins = sorted({str(v) for v in (io.get("levers") or {}).values()})
        outs = sorted({str(v) for v in (io.get("lamps") or {}).values()})
        if ins and outs:
            for f, ri, ro in sweep.candidate_recipes():
                if set(ri) == set(ins) and set(ro) == set(outs):
                    return f
    except Exception:                                       # noqa: BLE001
        pass
    return None


def gate(pkl, recipe, timeout, max_vectors):
    """Run the dual-engine gate. Returns (ok, detail). Never hangs."""
    cmd = [sys.executable, "-u", os.path.join(HERE, "verify2.py"),
           recipe, pkl, "--diff-all",
           "--max-vectors", str(max_vectors),
           "--sim-timeout", str(timeout), "--cmc-timeout", str(timeout)]
    print("gate: %s %s (timeout %ds each engine)"
          % (os.path.basename(recipe), os.path.basename(pkl), timeout),
          flush=True)
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout * 2 + 300,
                           cwd=r"D:\redstone-mini")
        out, rc = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        return False, "GATE TIMEOUT after %ds" % (timeout * 2 + 300)
    for line in out.splitlines():
        if line.startswith(("SIM", "CMC", "DIFF", "DUAL-ENGINE", "doc:")):
            print("  " + line, flush=True)
    # Never discard the exit code. 0 green, 1 red, anything else is a crash and
    # must be loud -- a crash is not a pass.
    ok = rc == 0
    return ok, ("exit=%d in %.0fs" % (rc, time.monotonic() - t0))


def flagval(name, default):
    """Value of --name, from the FULL argv. ponytail: filtering argv down to
    only the --args first (which is what I did first) silently drops the
    VALUE, because `300` does not start with `--`."""
    a = sys.argv[1:]
    if name in a:
        i = a.index(name)
        if i + 1 < len(a):
            return a[i + 1]
    return default


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    pkl = args[0] if args else r"D:\redstone-mini\scratch\alu4bank.pkl"
    label = args[1] if len(args) > 1 else "alu4"
    do_gate = "--no-gate" not in flags
    force = "--force" in flags
    timeout = int(flagval("--gate-timeout", 3600))
    max_vectors = int(flagval("--max-vectors", 16))
    forced_recipe = flagval("--recipe", None)

    d = pickle.load(open(pkl, "rb"))

    # Gate FIRST, before we touch the build at all. An ungated build must not
    # be able to fail halfway through writing exports.
    if do_gate:
        recipe = forced_recipe or find_recipe(d)
        if recipe is None:
            print("gate: SKIPPED -- cannot tell which recipe %s implements, and "
                  "guessing is how a stale artifact gets scored against the "
                  "wrong netlist. Pass --recipe PATH to gate it anyway."
                  % os.path.basename(pkl), flush=True)
            if not force:
                return 2
        else:
            ok, detail = gate(pkl, recipe, timeout, max_vectors)
            print("gate: %s (%s)" % ("GREEN" if ok else "RED", detail),
                  flush=True)
            if not ok and not force:
                print("\nREFUSING TO EXPORT an ungated build.\n"
                      "Both engines must pass and the per-cell diff must be "
                      "empty.\nIf you know this build is fine anyway, re-run "
                      "with --force; the export will be marked UNGATED.",
                      flush=True)
                return 1

    blocks = d["blocks"]
    size = d.get("size")
    io = d["io"]
    if size is None:
        # ponytail: hand-built probe artifacts (not_full.pkl and its kin) carry
        # no size because no router measured them. Deriving bounds here beats
        # crashing on the third of three exports after two files are already
        # on disk -- which is precisely the "fail halfway" this file exists to
        # prevent. A wrong size only mislabels the html viewport, never the
        # blocks, so this fallback cannot corrupt an export.
        xs = [b[0] for b in blocks]
        zs = [b[2] for b in blocks]
        size = (max(xs) - min(xs) + 1, max(zs) - min(zs) + 1)
        print("note: no size in pkl, derived %s from block bounds"
              % (size,), flush=True)
    lev = io.get("levers", {})
    xs = [c[0] for c in lev] or [0]
    zs = [c[1] for c in lev] or [0]
    print("blocks=%d size=%s levers=%d x %d..%d z %d..%d"
          % (len(blocks), size, len(lev), min(xs), max(xs), min(zs), max(zs)),
          flush=True)
    stem = os.path.join(r"D:\redstone-mini", "build_" + label)
    for name, fn, args2 in (
            ("mcfunction", export_mcfunction, (blocks, stem + ".mcfunction")),
            ("schem", export_schem, (blocks, stem + ".schem")),
            ("html", export_html, (blocks, size, stem + ".html", label, None))):
        t = time.monotonic()
        fn(*args2)
        p = args2[-1] if name != "html" else args2[2]
        print("%-10s %6.2fs  %d bytes  %s"
              % (name, time.monotonic() - t, os.path.getsize(p), p), flush=True)
    if do_gate and force:
        note = stem + ".UNGATED.txt"
        with open(note, "w") as f:
            f.write("Exported with --force: the dual-engine gate was NOT "
                    "green for this build.\npkl: %s\nrecipe: %s\n"
                    "Do not paste this without re-gating.\n"
                    % (pkl, find_recipe(d)))
        print("NOTE: wrote %s" % note, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())