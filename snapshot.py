"""Compilation snapshots: one JSON per attempt, replayable.

Copy of RC `compilation_snapshots.md` shrunk to what this compiler actually has.
RC ships a directory tree (manifest, summary, ir/logical, ir/routable, routes,
candidates, pnr) because it has six IR layers and a candidate cache; mini has
two IR layers and no cache, so the tree is one file per DISTINCT build,
content-hashed — the ladder re-runs the same seed every session, and a re-run
that lands the same build overwrites instead of littering.

The job is unchanged: a failed attempt stays inspectable forever. Every probe
in the handoff lived in TEMP and is now stale, and re-deriving one netspec
costs an hour. `replay` re-runs the sim gate over a recorded build, which is
also how the s7/s10 Q datum (`Q cells lit 16/126 vs 111/111`) gets read again:
the SIM MISMATCH message already carries the whole live map, so the record and
the analysis are the same file.
"""

import hashlib
import json
import os
import pathlib

SNAPDIR = pathlib.Path(__file__).parent / ".snapshots"


def mode():
    """REDSTONE_SNAPSHOT=fail|all; unset = off, so the suite writes nothing."""
    v = (os.environ.get("REDSTONE_SNAPSHOT") or "").strip().lower()
    return v if v in ("fail", "all") else ""


def target():
    """Where snapshots land. Env, not a rebindable global: `python
    snapshot.py` runs as __main__ while sim.py imports a second copy of this
    module, so a global set in the self-test would only move one of them."""
    return pathlib.Path(os.environ.get("REDSTONE_SNAPSHOT_DIR") or SNAPDIR)


def _k(c):
    return ",".join(str(x) for x in c)


def _c(s):
    return tuple(int(x) for x in s.split(","))


def write(recipe, blocks, io, states, meta):
    """Record one attempt. `blocks`/`io` may be None (a failure before any
    placement — the log is all there is). Returns the path, or None when off."""
    m = mode()
    if not m or (m == "fail" and not meta.get("error")):
        return None
    b, lv, lm, nt = ([], {}, {}, {}) if not blocks else (
        [[x, y, z, i] for x, y, z, i in blocks],
        {_k(c): n for c, n in io["levers"].items()},
        {_k(c): n for c, n in io["lamps"].items()},
        {_k(c): n for c, n in io["nets"].items()})
    from recipe import expand_gates
    h = hashlib.sha1(json.dumps([b, lv, lm, nt] if b else meta.get("attempts"),
                                sort_keys=True).encode()).hexdigest()[:12]
    d = target()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{h}.json"
    # ponytail: the whole build as one JSON -- no pruning, no compression, no
    # diff against the previous attempt. Content-hashing is what bounds it (a
    # re-run landing the same build overwrites), but N distinct builds is N
    # files forever. ceiling: no eviction; alu4 at 24k blocks is ~2MB.
    # upgrade: prune by count/mtime in target(), or gzip. trigger:
    # `.snapshots/` past ~100MB, or past a few hundred files.
    path.write_text(json.dumps({
        "manifest": {"recipe": recipe, **meta},
        "summary": {"blocks": len(b),
                    "elevated": sum(1 for x in b if x[1] >= 2),
                    "dust": sum(1 for x in b if x[3].startswith("minecraft:redstone_wire"))},
        # inputs matter: expand_gates relays input nets only when told they are
        # inputs, so calling it without them records a routable IR the build
        # never used.
        "ir": {"logical": recipe["gates"],
               "routable": expand_gates(recipe["gates"], recipe["inputs"])},
        "routes": {"nets": nt},
        "blocks": b, "io": {"levers": lv, "lamps": lm, "nets": nt}, "states": states}))
    return path


def replay(path):
    """Re-run the sim gate over a recorded build. Raises the original verdict
    again if it still fails; returns (blocks, io, states, ticks) if it doesn't."""
    from sim import sim_verify
    d = json.loads(pathlib.Path(path).read_text())
    io = {"levers": {_c(k): n for k, n in d["io"]["levers"].items()},
          "lamps": {_c(k): n for k, n in d["io"]["lamps"].items()},
          "nets": {_c(k): n for k, n in d["io"]["nets"].items()}}
    blocks = [tuple(x[:3]) + (x[3],) for x in d["blocks"]]
    st, ticks = sim_verify(d["manifest"]["recipe"], blocks, io, quiet=True, collect=True)
    return blocks, io, st, ticks


if __name__ == "__main__":
    import tempfile
    from recipe import parse_recipe
    from sim import layout_retry
    _d = tempfile.gettempdir()
    os.environ["REDSTONE_SNAPSHOT_DIR"] = _d + r"\rs-snapshot-selftest"
    os.environ["REDSTONE_SNAPSHOT"] = "all"
    r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    layout_retry(r, verify=True)
    got = sorted(target().glob("*.json"))
    assert len(got) == 1, got
    blocks, io, st, ticks = replay(got[0])
    assert len(blocks) > 0 and st["vectors"], (len(blocks), st)
    replay(got[0])  # idempotent: the same build verifies the same way twice
    os.environ["REDSTONE_SNAPSHOT_DIR"] = _d + r"\rs-snapshot-selftest-fail"
    os.environ["REDSTONE_SNAPSHOT"] = "fail"
    layout_retry(r, verify=True)
    assert not target().exists(), "fail mode must not record a good build"
    print("snapshot ok: content-hashed write, sim-gated replay, fail-only mode")
