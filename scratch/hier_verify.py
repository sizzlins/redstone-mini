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
    # ponytail: lever-bank pitch LADDER, so the tight default is permanent
    # without being reckless. Measured: add8 is green at pitch 2 (44,634
    # blocks) and at 10 (46,502), but pitch is per-build.
    #   alu1  green at 2
    #   alu4  STITCH RED at 2, and -- the trap -- it stitches fine at 3 and
    #         then VERIFIES RED, while pitch 10 is green. A rung that only has
    #         to survive the stitch is not good enough; the rung has to survive
    #         the VERIFY. Measured, not assumed: the first version of this
    #         ladder escalated on stitch exit code alone and turned a green
    #         alu4 gate red.
    # So each rung runs stitch -> ins_target -> verify, and only a green verify
    # settles the pitch. A `<recipe>.bank` sibling is an explicit pin: one
    # attempt, no escalation -- if you pinned it you meant it.
    #
    # Only the STITCH re-runs per rung: the bank is laid during the merge
    # (hier_stitch._apply_bank_pin), not per band, so the band cache is valid
    # at every rung and a rerun costs seconds rather than a band compose.
    LADDER = ("2", "3", "4", "6", "10")
    pinned = os.path.exists(os.path.splitext(src)[0] + ".bank")
    rungs = [None] if pinned else list(LADDER)
    coords = ins_target_coords(src)
    for pitch in rungs:
        # Per-rung paths, and this is load-bearing rather than tidy: verify_par
        # caches chunk verdicts keyed by the TARGET FILE, so if every rung wrote
        # alu4merge_g.pkl then rung 4 would read rung 3's cached RED and the
        # ladder would be judging a build that no longer exists. Caught by
        # watching "4 bad chunks (progress cached)" repeat verbatim across rungs.
        rung_merge = merge if pinned else merge.replace(
            ".pkl", "_p%s.pkl" % (pitch or "pin"))
        env = {"REDSTONE_HIERDUMP2": rung_merge}
        if pitch:
            env["REDSTONE_BANK_PITCH"] = pitch
        print("stitch attempt: %s"
              % ("pinned by <recipe>.bank" if pinned else "pitch %s" % pitch),
              flush=True)
        if run([py, "scratch/hier_stitch.py", cache, src, stitchsecs], 300,
               env):
            if pitch == LADDER[-1]:
                print("STITCH RED at every pitch %s" % (LADDER,), flush=True)
                return 1
            continue
        if _stitch_to_verify(py, src, rung_merge, coords, nchunks) == 0:
            print("lever-bank pitch settled at %s" % (pitch or "pinned"),
                  flush=True)
            return 0
        if pinned or pitch == LADDER[-1]:
            print("VERIFY RED and no rung left to try", flush=True)
            return 1
        print("VERIFY RED at pitch %s -- escalating to a roomier bank" % pitch,
              flush=True)
    return 1


def _stitch_to_verify(py, src, merge, coords, nchunks):
    """ins_target swap, then the staged verify. 0 only on VERIFY OK."""
    # pillar swap, then verify the SWAPPED build -- verifying the raw stitch
    # output is what made this gate disagree with the documented reproduce.
    if coords:
        fixed = merge.replace(".pkl", "_g.pkl")
        if run([py, "scratch/ins_target.py", merge, fixed] + coords, 300):
            return 1
        target = fixed
        print("verify target: %s (ins_target %d pillars)"
              % (target, len(coords) // 3), flush=True)
    else:
        target = merge
        print("verify target: %s (no <recipe>.ins_target sibling; if this "
              "recipe needs the pillar swap, the gate will smoke 3/4 and stop)"
              % target, flush=True)
    # verify_par stages itself. per_call=0 means "every pending chunk": worker
    # count alone sets the parallelism, so each worker builds simvec's tables
    # ONCE for its whole group instead of once per chunk (measured 7.78s and
    # 103 MB per build on alu4 -- 16 chunk-spawns wasted 126s rebuilding
    # constant tables). The loop below is a safety net, not the unit of work.
    per_call, rounds = 0, 12
    for _ in range(rounds):
        args = [py, "scratch/verify_par.py", target, src,
                "16", "400", str(per_call)]
        if nchunks:
            args.append(nchunks)
        # ponytail: a round that outruns the 900s cap is INCOMPLETE, not
        # failed -- verify_par caches finished chunks, so the next round
        # resumes. Previously TimeoutExpired propagated and killed the whole
        # gate (seen on 65k-vector add8); continuing is the staged design.
        try:
            r = subprocess.run(args, cwd=os.path.dirname(HERE), timeout=900,
                               capture_output=True, text=True)
        except subprocess.TimeoutExpired:
            print("verify round hit 900s cap; progress cached, continuing",
                  flush=True)
            continue
        print(r.stdout[-1500:], flush=True)
        if "VERIFY OK" in r.stdout:
            return 0
        if "VERIFY RED" in r.stdout:
            return 1
    print("STAGED verify did not finish in %d rounds" % rounds, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
