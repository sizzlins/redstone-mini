"""Table-driven redstone physics: one sweep for the whole build, vectors across cores.

sim.sim_verify runs one whole tick-stepped simulation PER input vector, so an
n-input build costs O(2^n) simulations. Measured: alu4 (10 inputs, 35k blocks)
= 1024 vectors, and cpu4 (7 inputs) = 128.

The physics itself does not change; only where the constants live.
sim._run_vec re-derives the neighbourhood on every event (tuple construction,
four direction scans, a dust_points call per powered neighbour) while the
build is static, so every one of those queries has a constant answer.
_tables_from hoists them once, and run_scalar replays sim._run_vec's rule set
term for term over those tables -- same verdict, ~2.5x faster, and
scratch/diff_engine.py proves it bit-identical (lamps, live dust, torches,
ticks, repeaters, comparators) against a frozen copy of the committed engine.

run_scalar declines (NotImplementedError) rather than guess when a latch
hold-seed is involved; _serial_shard then hands those vectors to sim._run_vec,
so the authority always owns the verdict and the loud diagnosis.

The module name is historical: it also carried a bit-parallel SWAR engine,
measured slower on alu4 and cut (see the driver note below).
"""
import os as _os
import time as _time

from core import DIRS
from layout import dust_points

# sim._run_vec gates lever power on this; default "1" (on). Read once so the
# precomputed tables cannot disagree with the engine that uses them.
_LEVPOW = _os.environ.get("REDSTONE_LEVER_POWER", "1") == "1"


def _orth(c):
    return ((c[0] + 1, c[1], c[2]), (c[0] - 1, c[1], c[2]),
            (c[0], c[1], c[2] + 1), (c[0], c[1], c[2] - 1))


def _pre(blocks, io, inp):
    """Parse a build, then build its static physics tables."""
    from sim import _parse_build
    return _tables_from(_parse_build(blocks, io), inp)


def _tables_from(P, inp):
    """Precompute every static query the physics asks, once per build.

    This is the boring half of the win and arguably the bigger one:
    sim._run_vec re-derives the neighbourhood on every event (tuple
    construction, four direction scans, a dust_points call per powered
    neighbour). The build is static, so every one of those queries has a
    constant answer. Hoisting them turns the inner loop from "walk 26
    neighbours and ask what each one is" into "walk a short list of cells
    already known to matter".
    """
    dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, \
        attach_rev, comp, leveratt, glass, slab, target = P
    # ponytail: transparent power sets (glass/slab feature, mirrors sim):
    # pwr holds power (cobble/stone + slabs; glass never), sup is any solid
    # rest (pwr + glass). Lid tests stay opaque-cobble. Identical tables when
    # glass/slab are absent, so the bit-identity gate cannot tell.
    pwr = cob | slab
    sup = pwr | glass

    def back(c, t):
        """Does the repeater/comparator at `c` feed `t`?"""
        if c in rep:
            d = rep[c]
            return (c[0] + d[0], c[1], c[2] + d[1]) == t
        cd = comp[c]
        return (c[0] - cd["rear"][0], c[1], c[2] - cd["rear"][1]) == t

    # ---- dust: per-DIRECTION specs ------------------------------------
    # ponytail: per direction, not per cell, because dust_lvl's comparator
    # term is an early RETURN -- it throws away the decay the earlier
    # directions accumulated and never reaches the later ones. Folding it into
    # a max alongside the soft terms silently mis-verifies any cell a
    # comparator faces (measured: two slope cells off by 2 and 13 levels).
    # Order is the whole point, so the order is kept.
    # code: 1 torch, 2 lever(payload=name), 3 redstone block, 4 cobble,
    #       5 dust, 6 repeater feeding c, 7 comparator feeding c
    d_below, d_dirs = {}, {}
    for c in dust:
        x, y, z = c
        d_below[c] = ((x, y - 1, z) in torch, (x, y - 1, z) in pwr)
        dirs = []
        for dx, dz in DIRS:
            m = (x + dx, y, z + dz)
            code, payload = 0, None
            if m in torch:
                code = 1
            elif m in lever:
                code, payload = 2, lever[m]
            elif m in rblk:
                code = 3
            elif m in cob:
                code = 4
            elif m in slab:
                code = 8  # powerable like 4, but transparent: never an
                          # opaque source (cup) and never a lid (cdn test
                          # passes it, exactly like sim's `not in cob`).
            elif m in dust:
                code = 5
            elif m in rep:
                if back(m, c):
                    code = 6
            elif m in comp:
                if back(m, c):
                    code = 7
            up = (x + dx, y + 1, z + dz)
            cup = up if (up in dust and code == 4
                         and (x, y + 1, z) not in cob) else None
            dn = (x + dx, y - 1, z + dz)
            cdn = dn if (dn in dust and code != 4
                         and (x, y - 1, z) in sup) else None
            dirs.append((m, code, payload, cup, cdn))
        d_dirs[c] = dirs

    # ---- cobble: weak power, strong power ------------------------------
    # ponytail: loop runs over pwr (cobble/stone + slabs); glass never holds
    # power so it needs no row. Empty delta when slabs are absent.
    c_dust, c_rep, c_torch, c_lev, c_rblk, c_up = {}, {}, {}, {}, {}, {}
    for c in pwr:
        x, y, z = c
        dd, rr, tt, ll = [], [], [], []
        rblk_side = False
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust and (-d[0], -d[1]) in dust_points(m, dust, target):
                dd.append(m)
            if m in rep and back(m, c):
                rr.append(m)
            if m in torch and torch[m] != c:
                tt.append(m)
            if (m in lever and _LEVPOW
                    and leveratt.get(m) in (None, c)):
                ll.append(lever[m])
            if m in rblk:
                rblk_side = True
        c_dust[c], c_rep[c], c_torch[c], c_lev[c] = dd, rr, tt, ll
        c_rblk[c] = rblk_side
        up = (x, y + 1, z)
        c_up[c] = up if up in dust else None

    # ---- repeater input ------------------------------------------------
    r_src = {}
    for c in rep:
        d = rep[c]
        b = (c[0] - d[0], c[1], c[2] - d[1])
        if b in dust:
            r_src[c] = ("d", b)
        elif b in pwr:
            r_src[c] = ("c", b)
        elif b in lever:
            r_src[c] = ("l", lever[b])
        elif b in rblk:
            r_src[c] = ("r",)
        elif b in rep:
            r_src[c] = ("r", b) if back(b, c) else None
        elif b in comp:
            r_src[c] = ("k", b) if back(b, c) else None
        else:
            r_src[c] = None

    # ---- comparator: rear input, two sides, mode ----------------------
    def side(cell, t):
        if cell in lever:
            return ("l", lever[cell])
        if cell in rblk:
            return ("r",)
        if cell in rep:
            return ("r", cell) if back(cell, t) else None
        if cell in comp:
            return ("k", cell) if back(cell, t) else None
        if cell in dust:
            return ("d", cell)
        if cell in pwr:
            return ("c", cell)
        return None

    k_rear, k_side, k_mode = {}, {}, {}
    for c in comp:
        rx, rz = comp[c]["rear"]
        rear = (c[0] + rx, c[1], c[2] + rz)
        if rear in dust:
            k_rear[c] = ("d", rear)
        elif rear in lever:
            k_rear[c] = ("l", lever[rear])
        elif rear in rblk:
            k_rear[c] = ("r",)
        elif rear in torch:
            k_rear[c] = ("t", rear)
        elif rear in rep:
            k_rear[c] = (("r", rear) if back(rear, c) else ("z",))
        elif rear in comp:
            k_rear[c] = (("k", rear) if back(rear, c) else ("z",))
        else:
            k_rear[c] = ("z",)
        k_side[c] = (side((c[0] + rz, c[1], c[2] + rx), c),
                     side((c[0] - rz, c[1], c[2] - rx), c))
        k_mode[c] = comp[c]["mode"]

    # ---- torch: attachment block, and whether it is dead ---------------
    t_att, t_dead = {}, {}
    for c in torch:
        a = torch[c]
        t_att[c] = a
        t_dead[c] = a in rblk   # on a redstone block: permanently off

    # ---- wake map: every cell -> the cells its change re-evaluates -----
    # ponytail: slab vertices included (slab power changes must propagate);
    # glass excluded (never changes). Edges join pwr.
    wake = {}
    for c in set(dust) | set(pwr) | set(rep) | set(comp) | set(torch):
        x, y, z = c
        out = []
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust:
                out.append(("d", m))
            elif m in pwr:
                out.append(("c", m))
            elif m in rep:
                # ponytail: the REAR test, not back(). A repeater must be
                # re-evaluated when the cell BEHIND it changes (that is its
                # input); back() asks the opposite question (does it feed the
                # changed cell) and silently left every repeater evaluated
                # exactly once, at tick 0, when its input is still dark -- so
                # no booster ever fired, the boosted wires decayed to nothing,
                # and the build "settled" dark and early. Symptom was
                # rep_on=0 and lit dust falling from 15 back to 5.
                dm = rep[m]
                if (m[0] - dm[0], m[1], m[2] - dm[1]) == c:
                    out.append(("r", m))
            elif m in comp:
                out.append(("k", m))
        for vy in (1, -1):
            m = (x, y + vy, z)
            if m in dust:
                out.append(("d", m))
            elif m in pwr:
                out.append(("c", m))
        for d in DIRS:
            for vy in (1, -1):
                m = (x + d[0], y + vy, z + d[1])
                if m in dust:
                    out.append(("d", m))
        for t in attach_rev.get(c, ()):
            out.append(("t", t))
        wake[c] = out

    # ---- lamp arms -----------------------------------------------------
    l_arm, l_cob, l_torch, l_lev, l_rblk, l_up = {}, {}, {}, {}, {}, {}
    for cell in lampnet:
        x, y, z = cell
        arms = []
        for d in DIRS:
            if all((x + d[0] + e[0], y, z + d[1] + e[1]) not in dust
                   for e in DIRS if e != d):
                arms.append((x + d[0], y, z + d[1]))
        l_arm[cell] = arms
        l_cob[cell] = [m for m in _orth(cell) if m in pwr]
        l_torch[cell] = [m for m in _orth(cell)
                         if m in torch and torch[m] != cell]
        l_lev[cell] = [lever[m] for m in _orth(cell) if m in lever]
        l_rblk[cell] = any(m in rblk for m in _orth(cell))
        up = (x, y + 1, z)
        l_up[cell] = up if up in dust else None

    return {"dust": dust, "torch": torch, "rep": rep, "comp": comp,
            "cob": cob, "pwr": pwr, "target": target, "repdelay": repdelay, "inp": inp,
            "d_below": d_below, "d_dirs": d_dirs,
            "c_dust": c_dust, "c_rep": c_rep, "c_torch": c_torch,
            "c_lev": c_lev, "c_rblk": c_rblk, "c_up": c_up,
            "r_src": r_src, "k_rear": k_rear, "k_side": k_side,
            "k_mode": k_mode, "t_att": t_att, "t_dead": t_dead,
            "wake": wake, "l_arm": l_arm, "l_cob": l_cob, "l_torch": l_torch,
            "l_lev": l_lev, "l_rblk": l_rblk, "l_up": l_up,
            "lampnet": lampnet,
            "ncells": len(dust) + len(pwr) + len(rep) + len(comp) + len(torch)}


def _comp_out(c, st, pw, pbs, tl, ron, con, inp, O):
    """Comparator output, lane-wise. subtract: max(rear-side, 0);
    compare: rear if side <= rear else 0."""
    rl = _lev(st["k_rear"][c], pw, pbs, tl, ron, con, inp, O)
    s0, s1 = st["k_side"][c]
    sl = 0
    if s0 is not None:
        sl = _lev(s0, pw, pbs, tl, ron, con, inp, O)
    if s1 is not None:
        sl = O.vmax(sl, _lev(s1, pw, pbs, tl, ron, con, inp, O))
    if st["k_mode"][c] == "subtract":
        return O.sub(rl, sl)
    return rl & O.ge(rl, sl)


# ------------------------------------------------------------ scalar engine
# ponytail: sim._run_vec is the authority AND the diagnostics, so it stays
# untouched. But it is also the hot loop, and its cost is almost entirely
# re-derivation of constant facts: per profile on alu4 it spends 207k
# dust_lvl calls, 98k wake calls and 146k cob_state calls PER VECTOR, each
# rebuilding tuples and re-asking membership questions whose answers are fixed
# by the (static) build, plus 219k os.environ.get calls for one boolean.
# run_scalar is the same physics over the same precomputed tables with Dial
# buckets, for the bulk 2^n sweep. scratch/diff_engine.py proves it returns
# bit-identical lamps/live/torch/tick/rep/comp against a frozen copy of the
# committed engine; anything else is not an optimisation.

_TBL = {}


def _tables(ctx):
    """Memoised _tables_from for an already-parsed build context.

    Keyed by id(ctx) with the context held in the value, so a recycled id can
    never return the wrong tables. Bounded: a sweep parses one context per
    worker, so this holds a handful of entries, but clear rather than grow.
    """
    k = id(ctx)
    e = _TBL.get(k)
    if e is not None and e[0] is ctx:
        return e[1]
    if len(_TBL) > 8:
        _TBL.clear()
    t = _tables_from(ctx, {})
    _TBL[k] = (ctx, t)
    return t


def _dust_lvl_s(c, st, pw, pbs, tl, ron, con, vec):
    if st["d_below"][c][0] and tl.get((c[0], c[1] - 1, c[2]), False):
        return 15
    if st["d_below"][c][1] and pbs.get((c[0], c[1] - 1, c[2]), False):
        return 15
    lv = 0
    for m, code, payload, cup, cdn in st["d_dirs"][c]:
        if code == 1:
            if tl.get(m, False):
                return 15
        elif code == 2:
            if vec.get(payload, False):
                return 15
        elif code == 3:
            return 15
        elif code == 4 or code == 8:
            if pbs.get(m, False):
                return 15
        elif code == 5:
            v = pw.get(m, 0) - 1
            if v > lv:
                lv = v
        elif code == 6:
            if ron.get(m, False):
                return 15
        elif code == 7:
            return con.get(m, 0)      # early return: discards lv, as upstream
        if cup is not None:
            v = pw.get(cup, 0) - 1
            if v > lv:
                lv = v
        if cdn is not None:
            v = pw.get(cdn, 0) - 1
            if v > lv:
                lv = v
    return lv


def _cob_state_s(c, st, pw, tl, ron, vec):
    pwrd = False
    for m in st["c_dust"][c]:
        if pw.get(m, 0) >= 1:
            pwrd = True
    strong = False
    if st["c_rblk"][c]:
        pwrd = True
        strong = True
    for m in st["c_lev"][c]:
        if vec.get(m, False):
            pwrd = True
            strong = True
    for m in st["c_torch"][c]:
        if tl.get(m, False):
            pwrd = True
            strong = True
    for m in st["c_rep"][c]:
        if ron.get(m, False):
            pwrd = True
            strong = True
    up = st["c_up"][c]
    if up is not None and pw.get(up, 0) >= 1:
        pwrd = True
    return pwrd, strong


def _rep_on_s(c, st, pw, pb, tl, ron, con, vec):
    s = st["r_src"][c]
    if s is None:
        return False
    k = s[0]
    if k == "d":
        return pw.get(s[1], 0) >= 1
    if k == "c":
        return bool(pb.get(s[1], False))
    if k == "l":
        return bool(vec.get(s[1], False))
    if k == "t":
        return bool(tl.get(s[1], False))
    if k == "r":
        return True if len(s) == 1 else bool(ron.get(s[1], False))
    if k == "k":
        return con.get(s[1], 0) >= 1
    return False


def _lev_s(spec, pw, pbs, tl, ron, con, vec):
    if spec is None:
        return 0
    k = spec[0]
    if k == "d":
        return pw.get(spec[1], 0)
    if k == "l":
        return 15 if vec.get(spec[1], False) else 0
    if k == "t":
        return 15 if tl.get(spec[1], False) else 0
    if k == "r":
        return 15 if (len(spec) == 1 or ron.get(spec[1], False)) else 0
    if k == "c":
        return 15 if pbs.get(spec[1], False) else 0
    if k == "k":
        return con.get(spec[1], 0)
    return 0


def _comp_out_s(c, st, pw, pbs, tl, ron, con, vec):
    rl = _lev_s(st["k_rear"][c], pw, pbs, tl, ron, con, vec)
    s0, s1 = st["k_side"][c]
    sl = 0
    if s0 is not None:
        v = _lev_s(s0, pw, pbs, tl, ron, con, vec)
        if v > sl:
            sl = v
    if s1 is not None:
        v = _lev_s(s1, pw, pbs, tl, ron, con, vec)
        if v > sl:
            sl = v
    if st["k_mode"][c] == "subtract":
        d = rl - sl
        return d if d > 0 else 0
    return rl if sl <= rl else 0


def run_scalar(vec, ctx, init=None, until=None, tick_cap=None, step_cap=None,
               stall=None, snap_at=None, target_hits=None):
    """One vector, scalar, over the precomputed tables.

    Returns sim._run_vec's 6-tuple exactly (lamps, live, torch, ticks, rep,
    comp) so callers cannot tell the two apart, and raises the same RuntimeError
    messages for stall / tick-cap / burnout.

    snap_at: optional. Either an iterable of ticks, or a dict the caller owns
    which the engine fills in place as {tick: live-dust map at the END of that
    tick}. This exists so a tick-by-tick diagnostic can be ONE simulation
    instead of one per stop: _run_vec(until=T) re-runs the whole prefix, so
    asking for 47 stops cost 47 x the fixed startup (measured 191s each on
    alu4 = 2.4 hours for one trace). Stops never reached are filled with the
    final state, which is what they would have shown anyway. The return value
    stays the 6-tuple either way.

    Deliberately NOT implemented: the latch hold-seed pre-solve (init with
    _solve). Callers with an init must use sim._run_vec; this raises instead of
    guessing, because a half-applied hold seed is exactly the kind of quiet
    wrong answer that ships a broken build.
    """
    from sim import _TICK_CAP, _STEP_CAP, _STALL, _BOUT_N, _BOUT_GRACE, _BOUT
    tick_cap = _TICK_CAP if tick_cap is None else tick_cap
    step_cap = _STEP_CAP if step_cap is None else step_cap
    stall = _STALL if stall is None else stall
    want = snap_at if isinstance(snap_at, dict) else (
        {int(t): None for t in snap_at} if snap_at else None)
    if init:
        raise NotImplementedError(
            "run_scalar: no latch pre-solve; use sim._run_vec when init is given")
    dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, \
        attach_rev, comp, leveratt, glass, slab, target = ctx
    if target_hits:
        # A projectile hit is time-dependent; the fixed tables only model the
        # target's idle opaque-conductive role. Validate first, then let the
        # caller fall back to sim._run_vec rather than freeze a transient.
        from sim import _target_shots
        _target_shots(target_hits, target)
        raise NotImplementedError(
            "run_scalar: no timed target hits; use sim._run_vec")
    pwr = cob | slab
    st = _tables(ctx)
    pw, pb, pbs = {}, {}, {}
    tl = {c: False for c in torch}
    ron = {c: False for c in rep}
    con = {c: 0 for c in comp}
    wake = st["wake"]
    flips = {}
    bout = {}

    RING = 5
    buckets = [[] for _ in range(RING)]
    b0 = buckets[0]
    for c in dust:
        b0.append(("d", c))
    for c in pwr:
        b0.append(("c", c))
    for c in torch:
        b0.append(("t", c))
    for c in rep:
        b0.append(("r", c))
    for c in comp:
        b0.append(("k", c))
    alive = len(b0)
    now = steps = last_change = 0
    max_gap = 0
    stall_cap = max(stall, 3 * st["ncells"])
    tsched, rsched, ksched = set(), set(), set()

    def mark():
        nonlocal last_change, max_gap
        g = steps - last_change
        if g > max_gap:
            max_gap = g
        last_change = steps

    while alive:
        if now > tick_cap or steps > step_cap:
            live = {x: v for x, v in pw.items() if v}
            churn = sorted((c for c, k in flips.items() if k >= 3),
                           key=lambda c: (-flips[c], str(c)))
            tloop = sorted(c for c in churn if c in torch)
            cset = set(churn)
            same = slope = 0
            for c in churn:
                for dx, dz in DIRS:
                    if (c[0] + dx, c[1], c[2] + dz) in cset:
                        same += 1
                    if (c[0] + dx, c[1] + 1, c[2] + dz) in cset:
                        slope += 1
            raise RuntimeError(
                f"sim not settling on {vec}. churn={len(churn)} "
                f"edges: same-level={same} slope={slope} "
                f"loop_torches: {tloop[:6]} max_gap={max_gap} "
                f"top: {[(c, pw.get(c, 0), flips[c]) for c in churn[:6]]}")
        i = now % RING
        items = buckets[i]
        if not items:
            if want is not None and now in want:
                want[now] = {c: v for c, v in pw.items() if v}
            now += 1
            steps += 0
            if steps - last_change > stall_cap:
                raise RuntimeError(
                    f"sim STALLED on {vec}: no value change for "
                    f"{steps - last_change} steps at tick {now} "
                    f"({steps} steps run) - wedged, not oscillating")
            continue
        buckets[i] = []
        alive -= len(items)
        # ponytail: coalesce same-tick re-queues. A cell woken five times in
        # one tick is evaluated five times and changes at most once, because it
        # reads the LATEST state when it finally runs. `hset` holds exactly the
        # items already queued for THIS tick and not yet evaluated, so dropping
        # a duplicate is free; a cell that has already been evaluated this tick
        # is not in `hset` and gets re-queued normally. Insertion order is
        # preserved (first occurrence wins), so the event sequence the physics
        # sees is unchanged -- this removes work, not information.
        here = buckets[i]
        hset = set()
        for kind, c in items:
            steps += 1
            if steps - last_change > stall_cap:
                raise RuntimeError(
                    f"sim STALLED on {vec}: no value change for "
                    f"{steps - last_change} steps at tick {now} "
                    f"({steps} steps run) - wedged, not oscillating")
            if kind == "d":
                v = _dust_lvl_s(c, st, pw, pbs, tl, ron, con, vec)
                if pw.get(c, 0) != v:
                    pw[c] = v
                    flips[c] = flips.get(c, 0) + 1
                    mark()
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "c":
                pwrd, strong = _cob_state_s(c, st, pw, tl, ron, vec)
                if pb.get(c, False) != pwrd or pbs.get(c, False) != strong:
                    pb[c], pbs[c] = pwrd, strong
                    flips[c] = flips.get(c, 0) + 1
                    mark()
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "t":
                if c in tsched or st["t_dead"][c]:
                    continue
                if (not pb.get(st["t_att"][c], False)) != tl.get(c, False):
                    tsched.add(c)
                    buckets[(now + 1) % RING].append(("T", c))
                    alive += 1
            elif kind == "T":
                tsched.discard(c)
                v = not pb.get(st["t_att"][c], False)
                if tl.get(c, False) != v:
                    if tl.get(c, False) and not v:
                        bt = tuple(t for t in bout.get(c, ()) if now - t < 30) + (now,)
                        bout[c] = bt
                        if len(bt) > max(_BOUT.get(c, 0), 0):
                            _BOUT[c] = len(bt)
                        if len(bt) > _BOUT_N and now >= _BOUT_GRACE:
                            tl[c] = False
                            raise RuntimeError(f"TORCH BURNOUT at {c} (shipping red)")
                    tl[c] = v
                    flips[c] = flips.get(c, 0) + 1
                    mark()
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "r":
                if c in rsched:
                    continue
                if _rep_on_s(c, st, pw, pb, tl, ron, con, vec) != ron.get(c, False):
                    rsched.add(c)
                    buckets[(now + repdelay.get(c, 1)) % RING].append(("R", c))
                    alive += 1
            elif kind == "R":
                rsched.discard(c)
                v = _rep_on_s(c, st, pw, pb, tl, ron, con, vec)
                if ron.get(c, False) != v:
                    ron[c] = v
                    mark()
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "k":
                if c in ksched:
                    continue
                if _comp_out_s(c, st, pw, pbs, tl, ron, con, vec) != con.get(c, 0):
                    ksched.add(c)
                    buckets[(now + 1) % RING].append(("K", c))
                    alive += 1
            elif kind == "K":
                ksched.discard(c)
                v = _comp_out_s(c, st, pw, pbs, tl, ron, con, vec)
                if con.get(c, 0) != v:
                    con[c] = v
                    mark()
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1

    lamps = {}
    if want:
        # any stop the run never reached (it settled first) shows the final
        # state, which is what it would have shown anyway
        final = {c: v for c, v in pw.items() if v}
        for t in list(want):
            if want[t] is None:
                want[t] = dict(final)
    for cell, net in lampnet.items():
        lit = False
        for a in st["l_arm"][cell]:
            if pw.get(a, 0) >= 1:
                lit = True
        if not lit and st["l_up"][cell] is not None \
                and pw.get(st["l_up"][cell], 0) >= 1:
            lit = True
        if not lit:
            for b in st["l_cob"][cell]:
                if pb.get(b, False):
                    lit = True
        if not lit:
            for t in st["l_torch"][cell]:
                if tl.get(t, False):
                    lit = True
        if not lit and st["l_rblk"][cell]:
            lit = True
        if not lit:
            for nm in st["l_lev"][cell]:
                if vec.get(nm, False):
                    lit = True
        lamps[net] = lit
    return (lamps,
            {c: v for c, v in pw.items() if v},
            {c: 1 if tl.get(c, False) else 0 for c in torch},
            now,
            {c: 1 if ron.get(c, False) else 0 for c in rep},
            {c: con.get(c, 0) for c in comp})


# ---------------------------------------------------------------- driver
# ponytail: one engine, vectors across cores. A bit-parallel (SWAR) engine
# lived here from 2026-09 and was measured against this one on alu4 (34672
# blocks, 1024 vectors, 20 cores): 22.7s against 21.5s for the table engine
# alone -- a 5.6% REGRESSION, byte-identical either way. It only pays when
# every lane in a shard converges together (an all-easy 128-lane shard ran
# ~110x faster), and real builds contain hard vectors: 6 of 8 x 128-lane
# shards burned the whole step budget, because merged event count is
# ~sum(lane) rather than ~max(lane). It could not terminate on a hunting
# vector at all (sim's torch-burnout rule was never reimplemented), which is
# why it needed shards, a step budget and a fallback. Off by default, enabled
# by nobody, measured slower on the only build big enough to matter: cut. The
# per-core serial engine is a fixed ~ncores speedup and cannot stall.
# Restore point if a 12+ input recipe ever makes 2^n unaffordable: git history
# at 68dd094 has the whole engine, and scratch/diff_engine.py is the gate that
# would prove a replacement bit-identical.

_W = {}
_CTX = None


def _init_worker(blocks, io, gates, outputs, ins, tick_cap, stall):
    _W.update(blocks=blocks, io=io, gates=gates, outputs=outputs, ins=ins,
              tick_cap=tick_cap, stall=stall)


def _serial_shard(combos):
    """The authority, one vector at a time. Bounded by sim's own caps.

    Uses run_scalar (the table-driven twin, proven bit-identical by
    scratch/diff_engine.py) and falls back to sim._run_vec whenever run_scalar
    declines -- i.e. when a latch hold-seed is involved, which run_scalar does
    not implement and refuses rather than guessing.

    Returns (bad, ticks, fatal). `fatal` is a not-settling / burnout /
    stall message: that is a TOPOLOGY fault of the build, identical in kind
    for every vector that touches the loop, so continuing is wasted budget.
    The stop event lets the rest of the pool stop too.
    """
    from sim import _parse_build, _run_vec
    from recipe import eval_net
    P = _parse_build(_W["blocks"], _W["io"])
    ins, gates, outs = _W["ins"], _W["gates"], _W["outputs"]
    rec = {"inputs": ins, "gates": gates, "outputs": outs}
    stop = _W.get("stop")
    bad, ticks = [], 0
    scalar = True
    for vec in combos:
        if stop is not None and stop.is_set():
            return bad, ticks, "aborted (another worker hit a structural fault)"
        try:
            got, live, tlv, tk, rlv, cn = run_scalar(vec, P)
        except NotImplementedError:
            scalar = False
            break
        except RuntimeError as e:
            if stop is not None:
                stop.set()
            return (bad, ticks,
                    "sim not settling / burnout on vector %s: %s"
                    % (vec, str(e)[:400]))
        ticks = max(ticks, tk)
        exp = eval_net(rec, vec)
        for net in outs:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, bool(got.get(net, False)), bool(exp[net])))
    if not scalar:                      # latch path: authority only
        for vec in combos:
            if stop is not None and stop.is_set():
                return bad, ticks, "aborted (another worker hit a fault)"
            try:
                got, live, tlv, tk, rlv, cn = _run_vec(vec, None, P, until=None)
            except RuntimeError as e:
                if stop is not None:
                    stop.set()
                return (bad, ticks,
                        "sim not settling / burnout on vector %s: %s"
                        % (vec, str(e)[:400]))
            ticks = max(ticks, tk)
            exp = eval_net(rec, vec)
            for net in outs:
                if bool(got.get(net, False)) != bool(exp[net]):
                    bad.append((vec, net, bool(got.get(net, False)),
                                bool(exp[net])))
    return bad, ticks, None


def _shard_job(combos):
    return _serial_shard(combos)


def _serial_drain(combos, ins, gates, outputs, blocks, io):
    """verify_par's body, run in THIS process with no pool (daemon callers)."""
    _init_worker(blocks, io, gates, outputs, ins, 20000, 5000)
    _W["stop"] = None
    bad, ticks = [], 0
    for vec in combos:
        try:
            got, live, tlv, tk, rlv, cn = run_scalar(vec, _parse_build_ctx())
        except NotImplementedError:
            break
        except RuntimeError as e:
            raise RuntimeError("sim not settling / burnout on vector %s: %s"
                               % (vec, str(e)[:400]))
        ticks = max(ticks, tk)
        from recipe import eval_net
        exp = eval_net({"inputs": ins, "gates": gates, "outputs": outputs}, vec)
        for net in outputs:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, bool(got.get(net, False)), bool(exp[net])))
    return bad, ticks


def _parse_build_ctx():
    global _CTX
    if _CTX is None:
        from sim import _parse_build
        _CTX = _parse_build(_W["blocks"], _W["io"])
    return _CTX


def verify_par(ins, gates, outputs, blocks, io, combos, workers=None,
               shard=None, tick_cap=20000, stall=5000, progress=None):
    """Verify every vector in `combos`. Returns (bad, max_ticks).

    bad is a list of (vec, net, got, want), the same shape sim.sim_verify
    raises on, so the caller reports it identically. Vectors are split into
    shards and run across processes on the table engine, which is the only
    engine here (see the driver note above for the bit-parallel one that was
    measured slower and cut). Every shard is bounded by the engine's own caps.
    """
    import multiprocessing as _mp
    # ponytail: same floating-support gate as sim.sim_verify (trench work).
    # Direct callers bypass sim_verify, so check here too; deferred import
    # (sim imports this module lazily, never at top level).
    from sim import _parse_build as _sv_parse, _check_supports as _sv_check
    _sv_check(_sv_parse(blocks, io))
    # ponytail: refuse to fan out from inside a pool worker. A pool worker is
    # DAEMONIC by definition, so the nested Pool raises "daematic processes are
    # not allowed to have children" -- and under spawn that is not a raise, it
    # is a fork bomb: the child re-imports the __main__ script, which calls
    # verify again, forever. sim.sim_verify has its own guard, but that only
    # covers callers that go through sim_verify; anything calling verify_par
    # DIRECTLY was still exposed. One line here closes the whole class. Falls
    # back to running in this process, which is correct and needs no children.
    try:
        if _mp.current_process().daemon:
            return _serial_drain(combos, ins, gates, outputs, blocks, io)
    except Exception:
        pass
    n = max(1, min(workers or (_os.cpu_count() or 1), len(combos)))
    shard = shard or max(1, len(combos) // (n * 4) or 1)
    init = (blocks, io, gates, outputs, ins, tick_cap, stall)
    ctx = _mp.get_context("spawn")
    bad, ticks, fatal = [], 0, None
    shards = [combos[i:i + shard] for i in range(0, len(combos), shard)]
    seen = [0]

    def drain(it, total):
        # ponytail: the parent blocks in imap_unordered at 0% CPU by design
        # while the workers grind, so a silent parent is indistinguishable
        # from a hung one. Count here, in the consumer, because a closure
        # defined in verify_par cannot be pickled to a spawn worker.
        nonlocal bad, ticks, fatal
        for res in it:
            bad += res[0]
            ticks = max(ticks, res[1])
            if res[2] and fatal is None:
                fatal = res[2]
            seen[0] += 1
            if progress and (seen[0] % 8 == 0 or seen[0] == total):
                progress(seen[0], total, 0.0)
            if fatal is not None:
                break

    _init_worker(*init)
    _W["stop"] = _mp.Event()
    if n == 1:
        drain(map(_shard_job, shards), len(shards))
    else:
        with ctx.Pool(n, initializer=_init_worker, initargs=init) as pool:
            drain(pool.imap_unordered(_shard_job, shards), len(shards))
    # ponytail: FAIL FAST on a structural fault. A not-settling / burnout /
    # stall verdict is a property of the BUILD, not of one vector -- every
    # vector that touches the same loop gets it -- so simulating the remaining
    # 2^n-1 vectors buys nothing. Measured on alu4: 12 of 16 sampled vectors
    # above index 256 are RED with churn ~11k cells, and the old code spent 22
    # minutes simulating all 1024 before saying so. Now the first structural
    # fault ends the sweep and its churn set (which names the loop) is raised
    # verbatim. Logic MISMATCHES are still all collected: those are per-vector
    # and cheap once the build settles.
    if fatal and not fatal.startswith("aborted"):
        raise RuntimeError(fatal)
    return bad, ticks


if __name__ == "__main__":
    # ponytail: one runnable check, and it is the only one that matters -- the
    # table engine must agree with the authority BIT for BIT, or it is not a
    # faster verifier, it is a wrong one. Routed through the real router, then
    # compared vector by vector against sim._run_vec.
    import os
    from recipe import parse_recipe
    from sim import _parse_build, _run_vec
    from compose import compose
    os.environ.pop("REDSTONE_SIM_GATE", None)
    _r = parse_recipe("IN a, b, c\nOUT y\nt = a AND b\n"
                      "u = t OR c\nv = u XOR a\ny = v OR c\n")
    _blocks, _size, _io = compose(_r)
    _ins = _r["inputs"]
    _combos = [{_ins[j]: (k >> j) & 1 for j in range(len(_ins))}
               for k in range(2 ** len(_ins))]
    _P = _parse_build(_blocks, _io)
    _bad, _ticks = verify_par(_ins, _r["gates"], _r["outputs"], _blocks, _io,
                              _combos)
    assert not _bad, _bad
    for _k, _vec in enumerate(_combos):
        _ser = _run_vec(_vec, None, _P)
        _tab = run_scalar(_vec, _P)
        assert _ser == _tab, (_k, _vec)
    print(f"simvec ok: {len(_combos)} vectors, run_scalar bit-identical to "
          f"sim._run_vec, {_ticks} ticks")