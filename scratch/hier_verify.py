"""The hier gate: generate + verify a big banded recipe, staged and resumable.

Usage: python scratch/hier_verify.py <recipes/xxx.txt> [bandsecs] [stitchsecs]
Stages (each short, each resumable; nothing here runs longer than minutes):
  1. bands  = hier_bands.py  (parallel, hard-killed, cached to .pkl)
  2. merge  = hier_stitch.py (merge+stitch+smoke, hard-killed)
  3. verify = verify_par.py  (staged vector chunks, cached)
Exit 0 with VERIFY OK only when every vector is cached green. This is the
authoritative gate for hier recipes (alu4, cpu4): layout_retry would take an
hour of silence for the same verdict (50 silent sim minutes), which reads as
a hang and gets killed. Same sim, same blocks, staged instead.
"""
import os, sys, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def run(args, tl, extra=None):
    print("+ " + " ".join(args), flush=True)
    env = dict(os.environ)
    if extra:
        env.update(extra)
    try:
        # ponytail: propagate the child's exit code. check=False + discarding
        # it meant a RED stage (stitch sys.exit(1)) was swallowed and the
        # pipeline went on to verify the PREVIOUS merge.pkl -- a cached green
        # for a build that no longer exists (measured: alu1 printed
        # "STITCH RED ... no ground for t3" and then "VERIFY OK 32/32" from
        # the stale merge, in the same run).
        r = subprocess.run(args, cwd=os.path.dirname(HERE), timeout=tl,
                           check=False, env=env)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {tl}s: {' '.join(args)}", flush=True)
        return 1
    return r.returncode


def ins_target_coords(src):
    """Coordinates for the load-bearing ins_target pillar swap, from a
    `<recipe>.ins_target` sibling -- the same convention hier_bands.py already
    uses for `<recipe>.skip`, so the pin outlives the shell that found it.
    Returns [] when there is no sibling.

    Why this step exists at all (2026-10-05): the 10/4 handoff calls ins_target
    "load-bearing -- without it the merge smokes 3/4 (Y2 wrong on 1010101010)"
    and its own cold-start reproduce lists it between stitch and verify. But
    hier_verify.py, the thing the handoff calls "the authoritative gate for
    hier recipes", never called it at all -- so
        python scratch/hier_verify.py recipes/alu4.txt
    died at `SMOKE 1010101010 MISMATCH ['Y2']` and exited 1, while the
    documented manual chain went 4/4 GREEN and VERIFY OK 1024/1024. The gate
    was missing a step the project depends on, and nobody noticed because the
    bands and the merge both reproduced perfectly right up to the smoke.

    The coordinates are MERGE-SPECIFIC (the handoff says so, and means it:
    re-derive with scratch/y2trace.py if the layout moves), which is exactly
    why they belong in a file next to the recipe rather than in the code.
    """
    p = os.path.splitext(src)[0] + ".ins_target"
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p):
        line = line.split("#", 1)[0]
        # whitespace separated, commas PRESERVED: ins_target.py takes each
        # pillar as one "x,y,z" argv entry (_parse does s.split(",")).
        out += line.split()
    return out


def main():
    src = sys.argv[1]
    bandsecs = sys.argv[2] if len(sys.argv) > 2 else "45"
    stitchsecs = sys.argv[3] if len(sys.argv) > 3 else "100"
    # ponytail: HIER_NCHUNKS fans the verify out finer (default 16).
    # Tail evidence: 64-vector chunks on alu4 skewed 105s vs 468s (4.5x);
    # finer chunks pack stragglers tighter (top-up loop already exists).
    # Fresh key namespace per nchunks ("64:i" vs "16:i"), so existing
    # caches are untouched -- but a new value re-verifies from scratch
    # once. Rounds scale so a full sweep always fits.
    nchunks = os.environ.get("HIER_NCHUNKS", "")
    cache = os.path.join("scratch", os.path.basename(src).replace(".txt", "bands.pkl"))
    merge = cache.replace("bands.pkl", "merge.pkl")
    target = merge
    py = sys.executable
    if run([py, "scratch/hier_bands.py", src, cache[:-4], bandsecs], 600):
        return 1
    if run([py, "scratch/hier_stitch.py", cache, src, stitchsecs], 300,
           {"REDSTONE_HIERDUMP2": merge}):
        return 1
    # pillar swap, then verify the SWAPPED build -- verifying the raw stitch
    # output is what made this gate disagree with the documented reproduce.
    coords = ins_target_coords(src)
    if coords:
        fixed = merge.replace(".pkl", "_g.pkl")
        if run([py, "scratch/ins_target.py", merge, fixed] + coords, 300):
            return 1
        target = fixed
        print("verify target: %s (ins_target %d pillars)"
              % (target, len(coords) // 3), flush=True)
    else:
        print("verify target: %s (no <recipe>.ins_target sibling; if this "
              "recipe needs the pillar swap, the gate will smoke 3/4 and stop)"
              % target, flush=True)
    # verify_par stages itself. per_call=0 means "every pending chunk": worker
    # count alone sets the parallelism, so each worker builds simvec's tables
    # ONCE for its whole group instead of once per chunk (measured 7.78s and
    # 103 MB per build on alu4 -- 16 chunk-spawns wasted 126s rebuilding
    # constant tables). The loop below is now a safety net, not the unit of
    # work: one call normally finishes the sweep.
    per_call, rounds = 0, 12
    if nchunks and per_call > 0:
        rounds = max(12, (int(nchunks) + per_call - 1) // per_call + 2)
    for _ in range(rounds):
        args = [py, "scratch/verify_par.py", target, src,
                "16", "400", str(per_call)]
        if nchunks:
            args.append(nchunks)
        r = subprocess.run(args,
                           cwd=os.path.dirname(HERE), timeout=900, capture_output=True, text=True)
        print(r.stdout[-1500:], flush=True)
        if "VERIFY OK" in r.stdout:
            return 0
        if "VERIFY RED" in r.stdout:
            return 1
    print("STAGED verify did not finish in %d rounds" % rounds, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
