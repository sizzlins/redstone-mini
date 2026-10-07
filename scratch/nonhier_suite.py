"""Bounded suite check for the NON-HIER recipes, after the input-bank changes.

Two of the three engine fixes live in `lwire`, which every partition
composition uses, not just the hier ones. This is the evidence that they did
not move anyone else's geometry: block counts are compared against the numbers
recorded in notes/handoff.md.

Hard-bounded: one child per recipe, hard-killed at CAP, so a dense recipe that
cannot go green reports a capped fail instead of running for hours.
"""
import multiprocessing as mp
import os
import sys
import time

sys.path.insert(0, r"D:\redstone-mini")

# blocks as recorded in notes/handoff.md before the input-bank work
EXPECT = {"alu1": 13300, "ctrl_decode": 5499}
NAMES = ["example_and", "example_2gates", "latch_sr", "example_xor", "micro1",
         "alu1", "ctrl_decode"]
CAP = {n: (150 if n.startswith("example") or n in ("latch_sr", "micro1") else 420)
       for n in NAMES}


def child(conn, name):
    try:
        from recipe import parse_recipe
        from compose import compose
        from sim import sim_verify
        r = parse_recipe(open(rf"D:\redstone-mini\recipes\{name}.txt").read())
        blocks, size, io = compose(r)
        sim_verify(r, blocks, io, quiet=True)
        conn.send(("ok", len(blocks), size, len(io.get("levers", {}))))
    except Exception as e:
        conn.send(("err", f"{type(e).__name__}: {e}", 0, 0))
    finally:
        conn.close()


def run(name):
    parent, ch = mp.Pipe(duplex=False)
    p = mp.Process(target=child, args=(ch, name), daemon=False)
    t0 = time.monotonic()
    p.start()
    ch.close()
    got = None
    if parent.poll(CAP[name]):
        try:
            got = parent.recv()
        except EOFError:
            got = None
    p.join(2)
    if p.is_alive():
        p.terminate()
        p.join(3)
        if p.is_alive():
            p.kill()
            p.join(3)
        return "KILLED at %gs" % CAP[name]
    parent.close()
    if got is None:
        return "DIED (no result)"
    if got[0] == "err":
        return "RED " + got[1][:70]
    exp = EXPECT.get(name)
    tag = "" if exp is None else ("  == %d" % exp if got[1] == exp
                                  else "  != %d MISMATCH" % exp)
    return "GREEN blocks=%-6d levers=%-3d size=%s%s" % (got[1], got[3],
                                                       got[2], tag)


if __name__ == "__main__":
    for n in NAMES:
        t0 = time.monotonic()
        print("%-14s %-58s %5.1fs" % (n, run(n), time.monotonic() - t0),
              flush=True)