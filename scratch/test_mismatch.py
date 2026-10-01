"""Exercise verify_par's mismatch branch and its daemon guard.

Agent 3's catch, and it is right: the bad alu4 chunks all raised NOT-SETTLING,
so the logic-MISMATCH collection path had never once been observed reporting
correctly -- and I had just changed the physics that eval_net's expectation is
compared against. The first build with a genuine logic error would have got its
answer from a path nobody had watched succeed.

This builds a deliberately MISCOMPUTING recipe (one gate's op flipped), routes
it, and asserts the mismatch is reported with the right shape and the right
( got, want ) -- not swallowed, not mislabelled as RED.

NEVER HANGS: tiny 3-input build (8 vectors), engine caps in force, and the
daemon case runs inside a 2-worker pool that is joined with a timeout.
Usage: python scratch/test_mismatch.py
"""
import os
import sys
import time
import copy

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)

TXT = ("IN a, b, c\nOUT y\nt = a AND b\n"
       "u = t OR c\nv = u XOR a\ny = v OR c\n")

OUT = r"C:\Users\LOQ\AppData\Local\Temp\opencode\daemon_result.txt"


def _daemon_worker(payload):
    """Module level: Windows spawn pickles the target BY REFERENCE, so a nested
    def dies with "Can't pickle local object"."""
    import simvec as sv
    e, bl, io_, n = payload
    try:
        b, _t = sv.verify_par(e["inputs"], e["gates"], e["outputs"], bl, io_,
                              [{i: (k >> j) & 1 for j, i in enumerate(e["inputs"])}
                               for k in range(n)])
        open(OUT, "w").write("ok %d" % len(b))
    except BaseException as e2:                        # noqa: BLE001
        open(OUT, "w").write("err %s: %s" % (type(e2).__name__, e2))


def build(mutate):
    from recipe import parse_recipe
    from compose import compose
    r = parse_recipe(TXT)
    blocks, size, io = compose(r)
    exp = copy.deepcopy(r)
    if mutate:
        # flip the first AND into an OR: the build computes AND, so every
        # vector where the two differ is a genuine logic MISMATCH
        for g in exp["gates"]:
            if g["op"] == "AND":
                g["op"] = "OR"
                break
    return exp, blocks, io


def main():
    import simvec
    ok = True

    exp, blocks, io = build(mutate=False)
    bad, ticks = simvec.verify_par(exp["inputs"], exp["gates"], exp["outputs"],
                                   blocks, io,
                                   [{i: (k >> j) & 1 for j, i in
                                     enumerate(exp["inputs"])}
                                    for k in range(8)])
    print("green case: bad=%d ticks=%s" % (len(bad), ticks), flush=True)
    if bad:
        print("  FAIL expected no mismatch, got", bad[:2])
        ok = False

    exp2, blocks2, io2 = build(mutate=True)
    bad2, ticks2 = simvec.verify_par(exp2["inputs"], exp2["gates"],
                                     exp2["outputs"], blocks2, io2,
                                     [{i: (k >> j) & 1 for j, i in
                                       enumerate(exp2["inputs"])}
                                      for k in range(8)])
    print("mismatch case: bad=%d" % len(bad2), flush=True)
    if not bad2:
        print("  FAIL expected a mismatch, got none -- the branch is dead")
        ok = False
    else:
        for vec, net, got, want in bad2[:4]:
            print("    vec=%s net=%s got=%s want=%s" % (vec, net, got, want),
                  flush=True)
        for vec, net, got, want in bad2:
            if net == "RED" or got == "RED":
                print("  FAIL a logic mismatch was reported as a structural "
                      "fault:", (vec, net, got))
                ok = False
            if got is not None and want is not None and got == want:
                print("  FAIL reported a mismatch where got == want:", bad2[0])
                ok = False

    # daemon guard: verify_par called from inside a DAEMONIC process must run
    # in-process, not spawn a nested pool (which is a fork bomb under spawn).
    # The worker reports via a FILE, not a Queue: passing a Queue handle into a
    # spawn child trips WinError 5 on Windows and would confuse the result.
    import multiprocessing as _mp
    if os.path.exists(OUT):
        os.remove(OUT)

    ctx = _mp.get_context("spawn")
    t0 = time.monotonic()
    pr = ctx.Process(target=_daemon_worker,
                     args=((exp2, blocks2, io2, 8),), daemon=True)
    pr.start()
    pr.join(120)
    if pr.is_alive():
        pr.terminate()
        pr.join(3)
        got = ("err", "daemon worker did not exit (fork bomb?)")
    else:
        got = (open(OUT).read() if os.path.exists(OUT)
               else ("err", "no result file"))
    print("daemon guard: %s in %.1fs" % (got, time.monotonic() - t0), flush=True)
    if not str(got).startswith("ok"):
        print("  FAIL daemon caller did not complete cleanly:", got)
        ok = False

    print("\n%s" % ("MISMATCH BRANCH OK" if ok else "MISMATCH BRANCH BROKEN"),
          flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())