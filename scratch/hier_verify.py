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
        subprocess.run(args, cwd=os.path.dirname(HERE), timeout=tl, check=False,
                       env=env)
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT after {tl}s: {' '.join(args)}", flush=True)
        return 1
    return 0


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
    py = sys.executable
    if run([py, "scratch/hier_bands.py", src, cache[:-4], bandsecs], 600):
        return 1
    if run([py, "scratch/hier_stitch.py", cache, src, stitchsecs], 300,
           {"REDSTONE_HIERDUMP2": merge}):
        return 1
    # verify_par stages itself (2 chunks/call); loop until it claims VERIFY OK
    per_call, rounds = 2, 12
    if nchunks:
        rounds = max(12, (int(nchunks) + per_call - 1) // per_call + 2)
    for _ in range(rounds):
        args = [py, "scratch/verify_par.py", merge, src,
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
