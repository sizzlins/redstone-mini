"""Simulation: redstone physics verifier plus generate-and-test retry."""

import random

from core import DIRS, base
from layout import layout
from recipe import eval_net


def layout_retry(recipe, tries=12, verify=False, grows=3):
    """Randomized-restart maze routing: reshuffle net order until the field fits.
    With verify, keep going until the placed build also passes redstone sim
    (generate-and-test: the sim is the selector, not just the guard).
    Field grows on failure (effectively infinite room, capped at 2000)."""
    last = None
    for grow in range(grows):
        for t in range(tries):
            try:
                out = layout(recipe, seed=None if t == 0 else t, grow=grow)
            except RuntimeError as e:
                last = e
                continue
            if not verify:
                return out
        try:
            sim_verify(recipe, out[0], out[2], quiet=True)
            return out
        except RuntimeError as e:
            e.blocks, e.size, e.io = out
            last = e
    raise last



def sim_verify(recipe, blocks, io, seed=7, quiet=False):
    """Independent redstone simulation of the PLACED build (ignores layout nets).
    Plays input vectors through torch/dust physics to a fixed point, compares
    lamps against eval_net. Catches opens/shorts the static guards can't see.
    # ponytail: flat single-level physics only (all our builds are); delay unmodeled.
    """
    import random as _r
    from collections import deque
    dust, torch, lampat, rep, rblk, cob = set(), {}, set(), {}, set(), set()
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
        # signal levels 0-15 (dust loses 1 per block). Levels drain phantom
        # latches that boolean models can't: no source => decays to 0.
        pw, pb, pbs, tl, ron = {}, {}, {}, {}, {}
        for c in torch:
            tl[c] = False
        q = deque()
        q.extend(("d", c) for c in dust)
        q.extend(("c", c) for c in cob)
        q.extend(("t", c) for c in torch)
        q.extend(("r", c) for c in rep)

        def push_dependents(kind, c):
            for dx, dz in DIRS:
                m = (c[0] + dx, c[1] + dz)
                if m in dust:
                    q.append(("d", m))
                elif m in cob:
                    q.append(("c", m))
                elif m in rep:
                    d = rep[m]
                    if (m[0] - d[0], m[1] - d[1]) == c:
                        q.append(("r", m))

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

        n = 0
        from collections import Counter as _Counter
        hot = _Counter()
        while q:
            n += 1
            if n > 20000:
                live = {c: v for c, v in pw.items() if v}
                raise RuntimeError(f"sim not settling on {vec}. live: {sorted(live.items())} torches: {tl} ron: {ron}")
            kind, c = q.popleft()
            hot[(kind, c)] += 1
            if kind == "d":
                v = dust_lvl(c)
                if pw.get(c, 0) != v:
                    pw[c] = v
                    push_dependents(kind, c)
            elif kind == "c":
                v, s = cob_state(c)
                if pb.get(c, False) != v or pbs.get(c, False) != s:
                    pb[c], pbs[c] = v, s
                    push_dependents(kind, c)
                    for t in attach_rev.get(c, []):
                        q.append(("t", t))
            elif kind == "t":
                v = not pb.get(torch[c], False)
                if tl.get(c, False) != v:
                    tl[c] = v
                    push_dependents(kind, c)
            elif kind == "r":
                v = rep_on(c)
                if ron.get(c, False) != v:
                    ron[c] = v
                    push_dependents(kind, c)
        return ({net: any(pw.get((cell[0] + dx, cell[1] + dz), 0) >= 1
                         for dx, dz in DIRS)
                for cell, net in lampnet.items()},
                {c: v for c, v in pw.items() if v},
                {c: 1 if tl.get(c, False) else 0 for c in torch})

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
    for vec in combos:
        got, live, _tl = run(vec)
        exp = eval_net(recipe, vec)
        for net in recipe["outputs"]:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, got.get(net), bool(exp[net])))
                lastlive = live
    if bad:
        raise RuntimeError(f"SIM MISMATCH x{len(bad)}: {bad[:4]} live: {sorted(lastlive.items())}")
    if not quiet:
        print(f"sim ok: {len(combos)} vectors, lamps match logic")

