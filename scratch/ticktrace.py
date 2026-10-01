"""Tick trace: when does a net first light, and what was driving it then?

Usage: python scratch/ticktrace.py <merge.pkl> <recipe.txt> <net> [bits]
Reports, for each target net, the tick at which it first becomes lit and every
later transition, with the local drive (how many of the net's cells are lit).

ONE SIMULATION. The old version called _run_vec(until=T) once per stop, and
_run_vec re-runs the whole prefix every time, so 47 stops cost 47 x the fixed
startup -- measured 191s each on alu4, i.e. ~2.4 hours for a single trace, and
silent the whole way (it printed only on change). Now a single run_scalar with
snap_at serves every stop, and the per-stop O(len(blocks)) scan over `at` is
precomputed once into a net -> cells map.

NEVER HANGS: the child heartbeats on every tick boundary, the parent uses
poll() with a deadline on every recv, and the child is terminated at the
deadline. Parent CPU reads ~0 by design (it blocks in recv); that is not a hang.
"""
import os
import sys
import time
import pickle
import multiprocessing as mp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

STOPS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22,
         25, 28, 32, 36, 40, 45, 50, 60, 70, 80, 100, 120, 150, 200, 260, 320,
         400, 500, 700, 1000, 1500, 2500, 5000, 10000, 20000]
DEADLINE = 1800.0


def child(conn, pkl, src, targets, bits):
    try:
        from recipe import parse_recipe
        from sim import _parse_build
        import simvec
        d = pickle.load(open(pkl, "rb"))
        r = parse_recipe(open(src).read())
        blocks, io = d["blocks"], d["io"]
        nets = io["nets"]
        # one pass over the build instead of one per target per stop
        bynet = {}
        for x, y, z, _b in blocks:
            n = nets.get((x, y, z))
            if n is not None:
                bynet.setdefault(n, []).append((x, y, z))
        vec = {n: int(bits[i]) for i, n in enumerate(r["inputs"])}
        pst = _parse_build(blocks, io)
        conn.send(("cells", ", ".join(
            "%s:%d" % (t, len(bynet.get(t, ()))) for t in targets)))
        conn.send(("go", "one simulation, %d stops" % len(STOPS)))

        snaps = {t: None for t in STOPS}
        t0 = time.monotonic()
        try:
            simvec.run_scalar(vec, pst, snap_at=snaps)
        except NotImplementedError:
            conn.send(("err", "latch build: run_scalar has no hold-seed "
                              "pre-solve; use sim._run_vec"))
            return
        except RuntimeError as e:
            conn.send(("note", "RED %s" % str(e)[:160]))
        conn.send(("hb", "run finished in %.1fs" % (time.monotonic() - t0)))

        prev = {}
        for until in STOPS:
            live = snaps.get(until) or {}
            changed = []
            for t in targets:
                oc = bynet.get(t, ())
                qc = bynet.get(t + "~qb", ())
                lit = sum(1 for c in oc if live.get(c))
                qlit = sum(1 for c in qc if live.get(c))
                st = (lit > 0, qlit > 0)
                if prev.get(t) != st:
                    prev[t] = st
                    changed.append("%s lit=%d/%d ~qb=%d/%d"
                                   % (t, lit, len(oc), qlit, len(qc)))
            if changed:
                conn.send(("tr", "t=%-6d %s" % (until, "  ".join(changed))))
        conn.send(("done",))
    except Exception as e:                        # noqa: BLE001
        import traceback
        conn.send(("err", "%s: %s\n%s" % (type(e).__name__, e,
                                          traceback.format_exc()[-1200:])))
    finally:
        conn.close()


def main():
    pkl, src = sys.argv[1], sys.argv[2]
    targets = sys.argv[3].split(",")
    bits = sys.argv[4] if len(sys.argv) > 4 else "0101010"
    p, c = mp.Pipe(duplex=False)
    pr = mp.Process(target=child, args=(c, pkl, src, targets, bits),
                    daemon=False)
    t0 = time.monotonic()
    pr.start()
    c.close()
    deadline = t0 + DEADLINE
    last = t0
    while True:
        if not p.poll(1.0):
            # a parent blocked in recv reads ~0 CPU by design; judge by the
            # clock and the log, never by parent CPU
            if time.monotonic() > deadline:
                pr.terminate()
                pr.join(3)
                if pr.is_alive():
                    pr.kill()
                    pr.join(3)
                print("KILLED at %.0fs" % DEADLINE, flush=True)
                sys.exit(1)
            if time.monotonic() - last > 30:
                last = time.monotonic()
                print("   ... alive %.0fs" % (time.monotonic() - t0), flush=True)
            continue
        try:
            msg = p.recv()
        except EOFError:
            break
        if msg[0] == "err":
            print("ERR", msg[1], flush=True)
            pr.join(5)
            sys.exit(1)
        print(*msg[:2], flush=True)
        if msg[0] == "done":
            break
    pr.join(5)
    if pr.is_alive():
        pr.terminate()
        pr.join(3)
    print("total %.1fs" % (time.monotonic() - t0), flush=True)


if __name__ == "__main__":
    main()