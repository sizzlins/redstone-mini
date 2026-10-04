"""Bounded ladder for ONE recipe file with extended spreads."""
import os
import sys
import time

ROOT = os.environ.get("RS_ROOT", r"D:\redstone-mini")
sys.path.insert(0, ROOT)


def child(conn, path):
    try:
        os.environ["REDSTONE_SIM_GATE"] = "1"
        import compose
        from recipe import parse_recipe
        from sim import sim_verify
        r = parse_recipe(open(path).read())
        t0 = time.monotonic()
        blocks, size, io = compose.compose(r)
        ct = time.monotonic() - t0
        try:
            sim_verify(r, blocks, io, quiet=True)
        except RuntimeError as e:
            conn.send(("sim-red", len(blocks), size, round(ct, 1),
                       " ".join(str(e).split())[:120]))
        else:
            conn.send(("GREEN", len(blocks), size, round(ct, 1), ""))
    except Exception as e:
        conn.send(("red", 0, None, 0,
                   " ".join(f"{type(e).__name__}: {e}".split())[:120]))
    finally:
        conn.close()


def one(path, force, cap):
    import multiprocessing as mp
    parent, ch = mp.Pipe(duplex=False)
    env = os.environ.get("REDSTONE_FORCE")
    os.environ["REDSTONE_FORCE"] = force
    p = mp.Process(target=child, args=(ch, path), daemon=False)
    t0 = time.monotonic()
    p.start()
    os.environ.pop("REDSTONE_FORCE", None)
    if env:
        os.environ["REDSTONE_FORCE"] = env
    ch.close()
    got = None
    if parent.poll(cap):
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
        return "KILLED at %gs" % cap
    parent.close()
    if got is None:
        return "DIED"
    return "%-8s blocks=%-6s size=%-12s %4.1fs  %s" % (
        got[0], got[1] or "-", got[2], got[3], got[4])


if __name__ == "__main__":
    path = sys.argv[1]
    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 90.0
    # Extended spreads: 1-10
    rungs = [f"{s},{o},{j}" for j in ("short", "long")
             for s in (1, 2, 3, 4, 5, 6, 8, 10) for o in ("gates_first", "inputs_first")]
    for f in rungs:
        print("%-22s %s" % (f, one(path, f, cap)), flush=True)