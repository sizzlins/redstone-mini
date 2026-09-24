"""Simulation: redstone physics verifier plus generate-and-test retry."""

import random

from core import DIRS, base
from layout import layout
from recipe import eval_net


def layout_retry(recipe, tries=12, verify=False, grows=3):
    """Randomized-restart maze routing: reshuffle net order until the field fits.
    With verify, keep the smallest build that also passes redstone sim
    (generate-and-test: the sim is the selector, not just the guard; restarts
    are free search, so ship the cheapest verified one).
    Field grows on failure (effectively infinite room, capped at 2000)."""
    last = None
    for grow in range(grows):
        out = None
        best = None
        for t in range(tries):
            try:
                out = layout(recipe, seed=None if t == 0 else t, grow=grow)
            except RuntimeError as e:
                last = e
                continue
            if not verify:
                return out + (None,)
            try:
                st = sim_verify(recipe, out[0], out[2], quiet=True, collect=True)
            except RuntimeError as e:
                e.blocks, e.size, e.io = out[:3]
                last = e
                continue
            if best is None or len(out[0]) < len(best[0]):
                best = out + (st,)
        if best is not None:
            return best
        # nothing verified this grow: keep last error, grow the field
    raise last



def sim_verify(recipe, blocks, io, seed=7, quiet=False, collect=False):
    """Independent redstone simulation of the PLACED build (ignores layout nets).
    Plays input vectors through tick-stepped torch/dust physics, compares
    lamps against eval_net. Catches opens/shorts the static guards can't see.
    # ponytail: flat single-level physics only (all our builds are); vanilla
    # tick delays (torch +1, repeater +its delay stage).
    """
    import random as _r
    dust, torch, lampat, rep, rblk, cob = set(), {}, set(), {}, set(), set()
    repdelay = {}
    for x, y, z, bid in blocks:
        if y != 1:
            continue
        b, c = base(bid), (x, z)
        if b == "minecraft:redstone_wire":
            dust.add(c)
        elif b == "minecraft:redstone_wall_torch":
            face = bid.split("facing=")[1].rstrip("]") if "facing=" in bid else "east"
            back = {"east": (-1, 0), "west": (1, 0), "south": (0, -1), "north": (0, 1)}[face]
            torch[c] = (c[0] + back[0], c[1] + back[1])
        elif b == "minecraft:redstone_lamp":
            lampat.add(c)
        elif b == "minecraft:repeater":
            face = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            rep[c] = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}[face]
            dly = bid.split("delay=")[1].split(",")[0].rstrip("]") if "delay=" in bid else "1"
            repdelay[c] = max(1, min(4, int(dly)))
        elif b == "minecraft:redstone_block":
            rblk.add(c)
        elif b == "minecraft:cobblestone":
            cob.add(c)
    lever = dict(io["levers"])
    lampnet = dict(io["lamps"])
    attach_rev = {}
    for t, a in torch.items():
        attach_rev.setdefault(a, []).append(t)

    def run(vec):
        # tick-accurate vanilla timing: dust/cobble settle instantly each tick,
        # torch outputs flip 1 tick after their block changes, repeaters flip
        # after their delay=1..4 stage. Levels still drain phantom latches.
        import heapq as _hq
        pw, pb, pbs = {}, {}, {}
        tl = {c: False for c in torch}
        ron = {c: False for c in rep}
        pending, tsched, rsched, seq, ticks, steps = [], set(), set(), [0], [0], [0]

        def sched(tick, kind, cell):
            seq[0] += 1
            _hq.heappush(pending, (tick, seq[0], kind, cell))

        def wake(now, c):
            # cell c changed output at tick now: re-eval everything it feeds.
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in dust:
                    sched(now, "d", m)
                elif m in cob:
                    sched(now, "c", m)
                elif m in rep:
                    d = rep[m]
                    if (m[0] - d[0], m[1] - d[1]) == c:
                        sched(now, "r", m)
            for t in attach_rev.get(c, []):
                sched(now, "t", t)

        def dust_lvl(c):
            lv = 0
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in torch and tl.get(m, False):
                    return 15
                if m in lever and vec.get(lever[m], False):
                    return 15
                if m in rblk:
                    return 15
                if m in cob and pbs.get(m, False):
                    return 15
                if m in dust:
                    lv = max(lv, pw.get(m, 0) - 1)
                if m in rep:
                    d = rep[m]
                    if (m[0] + d[0], m[1] + d[1]) == c and ron.get(m, False):
                        return 15
            return max(lv, 0)

        def cob_state(c):
            pwrd, strong = False, False
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in dust and pw.get(m, 0) >= 1:
                    pwrd = True
                if m in rblk:
                    pwrd, strong = True, True
                if m in rep:
                    d = rep[m]
                    if (m[0] + d[0], m[1] + d[1]) == c and ron.get(m, False):
                        pwrd, strong = True, True
            return pwrd, strong

        def rep_on(c):
            d = rep[c]
            b = (c[0] - d[0], c[1] - d[1])
            if b in dust and pw.get(b, 0) >= 1:
                return True
            if b in cob and pb.get(b, False):
                return True
            if b in lever and vec.get(lever[b], False):
                return True
            if b in rblk:
                return True
            # ponytail: repeaters chain back-to-back (standard); read upstream ron.
            if b in rep:
                d2 = rep[b]
                if (b[0] + d2[0], b[1] + d2[1]) == c and ron.get(b, False):
                    return True
            return False

        for c in dust:
            sched(0, "d", c)
        for c in cob:
            sched(0, "c", c)
        for c in torch:
            sched(0, "t", c)
        for c in rep:
            sched(0, "r", c)

        while pending:
            now, _, kind, c = _hq.heappop(pending)
            steps[0] += 1
            if now > 500 or steps[0] > 20000:
                live = {x: v for x, v in pw.items() if v}
                raise RuntimeError(f"sim not settling on {vec}. live: {sorted(live.items())} torches: {tl} ron: {ron}")
            ticks[0] = max(ticks[0], now)
            if kind == "d":
                v = dust_lvl(c)
                if pw.get(c, 0) != v:
                    pw[c] = v
                    wake(now, c)
            elif kind == "c":
                v, s = cob_state(c)
                if pb.get(c, False) != v or pbs.get(c, False) != s:
                    pb[c], pbs[c] = v, s
                    wake(now, c)
            elif kind == "t":
                if (not pb.get(torch[c], False)) != tl.get(c, False) and c not in tsched:
                    tsched.add(c)
                    sched(now + 1, "T", c)
            elif kind == "T":
                tsched.discard(c)
                v = not pb.get(torch[c], False)
                if tl.get(c, False) != v:
                    tl[c] = v
                    wake(now, c)
            elif kind == "r":
                if rep_on(c) != ron.get(c, False) and c not in rsched:
                    rsched.add(c)
                    sched(now + repdelay.get(c, 1), "R", c)
            elif kind == "R":
                rsched.discard(c)
                v = rep_on(c)
                if ron.get(c, False) != v:
                    ron[c] = v
                    wake(now, c)
        return ({net: any(pw.get((cell[0] + dx, cell[1] + dz), 0) >= 1
                         for dx, dz in DIRS)
                for cell, net in lampnet.items()},
                {c: v for c, v in pw.items() if v},
                {c: 1 if tl.get(c, False) else 0 for c in torch},
                ticks[0],
                {c: 1 if ron.get(c, False) else 0 for c in rep})

    ins = recipe["inputs"]
    if 2 ** len(ins) <= 4096:
        combos = [{ins[j]: (k >> j) & 1 for j in range(len(ins))} for k in range(2 ** len(ins))]
    else:
        rr = _r.Random(seed)
        combos = [{n: 0 for n in ins}, {n: 1 for n in ins},
                  {n: j % 2 for j, n in enumerate(ins)},
                  {n: (j + 1) % 2 for j, n in enumerate(ins)}]
        combos += [{n: rr.randint(0, 1) for n in ins} for _ in range(60)]
    bad = []
    lastlive = {}
    states = None
    if collect and len(combos) <= 16:
        states = {"inputs": list(ins),
                  "levers": {f"{x},{z}": n for (x, z), n in io["levers"].items()},
                  "lamps": {f"{x},{z}": n for (x, z), n in io["lamps"].items()},
                  "vectors": {}}
    for vec in combos:
        got, live, tlive, nticks, rlive = run(vec)
        exp = eval_net(recipe, vec)
        for net in recipe["outputs"]:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, got.get(net), bool(exp[net])))
                lastlive = live
        if states is not None:
            vkey = "".join(str(vec[n]) for n in ins)
            states["vectors"][vkey] = {
                "w": {f"{x},{z}": v for (x, z), v in live.items()},
                "t": {f"{x},{z}": v for (x, z), v in tlive.items()},
                "lamps": {f"{x},{z}": 1 if got.get(net, False) else 0
                          for (x, z), net in io["lamps"].items()},
                "ticks": nticks,
                "r": {f"{x},{z}": v for (x, z), v in rlive.items()}}
    if bad:
        raise RuntimeError(f"SIM MISMATCH x{len(bad)}: {bad[:4]} live: {sorted(lastlive.items())}")
    if not quiet:
        print(f"sim ok: {len(combos)} vectors, lamps match logic")
    return states


if __name__ == "__main__":
    # ponytail: one runnable check — delay-4 chain must settle at exactly tick 4.
    _blocks = [(1, 1, 0, "minecraft:repeater[facing=east,delay=4]"),
               (2, 1, 0, "minecraft:redstone_wire"),
               (3, 1, 0, "minecraft:redstone_lamp")]
    _io = {"levers": {(0, 0): "a"}, "lamps": {(3, 0): "y"}, "nets": {}}
    _recipe = {"inputs": ["a"], "outputs": ["y"],
               "gates": [{"out": "y", "op": "OR", "args": ["a", "a"]}]}
    _st = sim_verify(_recipe, _blocks, _io, quiet=True, collect=True)
    assert _st["vectors"]["1"]["lamps"] == {"3,0": 1}, _st["vectors"]["1"]
    assert _st["vectors"]["1"]["ticks"] == 4, _st["vectors"]["1"]["ticks"]
    assert _st["vectors"]["0"]["lamps"] == {"3,0": 0}, _st["vectors"]["0"]
    print("tick ok: delay-4 settles at tick 4")
    from export import export_html
    _blocks = [(0, 1, 0, "minecraft:lever"),
               (1, 1, 0, "minecraft:repeater[facing=east,delay=4]"),
               (2, 1, 0, "minecraft:redstone_wire"),
               (3, 1, 0, "minecraft:redstone_wall_torch[facing=east]"),
               (4, 1, 0, "minecraft:redstone_lamp")]
    _io = {"levers": {(0, 0): "a"}, "lamps": {(4, 0): "y"}, "nets": {}}
    _st = {"inputs": ["a"], "levers": {"0,0": "a"}, "lamps": {"4,0": "y"},
           "vectors": {"0": {"w": {}, "t": {"3,0": 0}, "lamps": {"4,0": 0},
                             "ticks": 0, "r": {"1,0": 0}}}}
    export_html(_blocks, (6, 1), r"C:\Users\LOQ\AppData\Local\Temp\opencode\stages.html",
                "s", _st)
    import json as _json
    _h = open(r"C:\Users\LOQ\AppData\Local\Temp\opencode\stages.html").read()
    _i = _h.find("const B=")
    _data = _json.loads(_h[_i + len("const B="):_h.find(";const s=", _i)])
    _reps = [d for d in _data if d["b"] == "minecraft:repeater"]
    assert _reps and _reps[0]["dl"] == 4 and _reps[0]["f"] == [1, 0], _reps
    _to = [d for d in _data if d["b"] == "minecraft:redstone_wall_torch"]
    assert _to and _to[0]["f"] == [1, 0] and _to[0]["m"] == 0, _to
    assert "applyState(INPUTS.map(n=>'0').join(''))" in _h, "no initial applyState"
    print("stages ok: delay-4 stamped, torch facing pinned, initial paint")

