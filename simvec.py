"""Bit-parallel redstone physics: SIMD-in-a-register across input vectors.

The serial verifier runs one whole tick-stepped simulation PER input vector,
so an n-input build costs O(2^n) simulations. Measured: alu4 (10 inputs, 34672
blocks) = 1024 vectors x 1.31s = 1337s, doubling per input added.

Every physics predicate is per-vector PURE -- dust level, block power, torch
state -- so the only thing separating two vectors is the input bits. One
Python int can therefore carry a whole vector's state per cell, and a bitwise
AND/OR evaluates every vector at once. That is SWAR: what 90s code lived on
before SIMD intrinsics were everywhere. Python's arbitrary-precision ints are
the register. 1024 vectors become ONE simulation, not 1024.

Lane layout, 6 bits per lane:
    bits 0..3   value: dust level / comparator output, 0..15
    bit  4      unused
    bit  5      HIGH: the comparison guard bit, and the encoding of TRUE

Booleans are HIGH masks (0x20 or 0 per lane), so boolean logic is plain
& | ^ against HIGH at one bignum op each. Levels sit in bits 0..3; raising the
guard bit in a lane before subtracting turns every lane-wise max/min/dec/
compare into shift+subtract with no carry escaping its lane. The rule set
below is sim._run_vec's rule set, one lane wider.

Event scheduling is Dial's bucket queue (1969): the longest delay is 4 (a
repeater) and ticks are integers, so 5 rotating buckets replace the binary
heap's log n comparisons and per-event tuple allocs.

WHERE THIS IS EXACT. A drained queue means every lane sits at a fixpoint of
the same equations the serial engine iterates; for a DAG build (no LATCH
gate) that fixpoint is unique, so sim._run_vec lands on it too, whatever order
it visited. Where uniqueness does not hold the run cannot drain -- it
oscillates or stalls -- and sim.verify_par hands the vectors back to the
serial engine, which keeps ownership of the loud diagnosis. So this module
never reports "settled" on anything order-dependent.
"""
import os as _os
import time as _time

from core import DIRS
from layout import dust_points

LANE = 6
SHIFT = 5

# sim._run_vec gates lever power on this; default "1" (on). Read once so the
# precomputed tables cannot disagree with the engine that uses them.
_LEVPOW = _os.environ.get("REDSTONE_LEVER_POWER", "1") == "1"


class Indecisive(RuntimeError):
    """The bit-parallel run could not settle every lane.

    `lanes` is the set of lane indices still changing when the budget ran out.
    It is a heuristic (a rolling window of the last few change masks), so the
    caller re-runs those vectors through the serial engine, which is the
    authority on what actually went wrong.
    """

    def __init__(self, lanes, churn, ticks, steps, why):
        self.lanes = tuple(sorted(lanes))
        self.churn = churn
        self.ticks = ticks
        self.steps = steps
        self.why = why
        super().__init__(f"bit-parallel sim hit {why} at tick {ticks} after "
                         f"{steps} steps; {len(self.lanes)} lane(s) still "
                         f"changing, churn={len(churn)}")


class _Ops:
    """Lane-wise arithmetic over packed words. Pure int ops, no branches."""

    __slots__ = ("ones", "high", "valm", "f15all", "nl")

    def __init__(self, nl):
        self.nl = nl
        one, high, valm = 1, 1 << SHIFT, (1 << SHIFT) - 1
        o = h = v = 0
        for _ in range(nl):
            o |= one
            h |= high
            v |= valm
            one <<= LANE
            high <<= LANE
            valm <<= LANE
        self.ones, self.high, self.valm = o, h, v
        self.f15all = self.f15(h)

    def nz(self, v):
        """HIGH mask where the lane value is >= 1 ('is powered')."""
        return ((v | self.high) - self.ones) & self.high

    def dec(self, v):
        """max(v-1, 0) lane-wise: vanilla dust decay."""
        t = (v | self.high) - self.ones      # lane value + 31, never borrows
        keep = t & self.high                # bit 5 set iff v >= 1
        keep -= keep >> SHIFT               # 0x1F in those lanes
        return t & self.valm & keep

    def ge(self, a, b):
        """0x1F in every lane where a >= b."""
        g = ((a | self.high) - b) & self.high
        return g - (g >> SHIFT)

    def vmax(self, a, b):
        m = self.ge(a, b)
        return (a & m) | (b & (self.valm ^ m))

    def sub(self, a, b):
        """max(a-b, 0) lane-wise: comparator subtract mode."""
        return ((a | self.high) - b) & self.valm & self.ge(a, b)

    def f15(self, m):
        """Broadcast a HIGH boolean mask into the value 15."""
        h = m >> SHIFT
        return h | (h << 1) | (h << 2) | (h << 3)


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
        attach_rev, comp, leveratt = P

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
        d_below[c] = ((x, y - 1, z) in torch, (x, y - 1, z) in cob)
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
                         and (x, y - 1, z) in cob) else None
            dirs.append((m, code, payload, cup, cdn))
        d_dirs[c] = dirs

    # ---- cobble: weak power, strong power ------------------------------
    c_dust, c_rep, c_torch, c_lev, c_rblk, c_up = {}, {}, {}, {}, {}, {}
    for c in cob:
        x, y, z = c
        dd, rr, tt, ll = [], [], [], []
        rblk_side = False
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust and (-d[0], -d[1]) in dust_points(m, dust):
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
        elif b in cob:
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
        if cell in cob:
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
    wake = {}
    for c in set(dust) | set(cob) | set(rep) | set(comp) | set(torch):
        x, y, z = c
        out = []
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust:
                out.append(("d", m))
            elif m in cob:
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
            elif m in cob:
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
        l_cob[cell] = [m for m in _orth(cell) if m in cob]
        l_torch[cell] = [m for m in _orth(cell)
                         if m in torch and torch[m] != cell]
        l_lev[cell] = [lever[m] for m in _orth(cell) if m in lever]
        l_rblk[cell] = any(m in rblk for m in _orth(cell))
        up = (x, y + 1, z)
        l_up[cell] = up if up in dust else None

    return {"dust": dust, "torch": torch, "rep": rep, "comp": comp,
            "cob": cob, "repdelay": repdelay, "inp": inp,
            "d_below": d_below, "d_dirs": d_dirs,
            "c_dust": c_dust, "c_rep": c_rep, "c_torch": c_torch,
            "c_lev": c_lev, "c_rblk": c_rblk, "c_up": c_up,
            "r_src": r_src, "k_rear": k_rear, "k_side": k_side,
            "k_mode": k_mode, "t_att": t_att, "t_dead": t_dead,
            "wake": wake, "l_arm": l_arm, "l_cob": l_cob, "l_torch": l_torch,
            "l_lev": l_lev, "l_rblk": l_rblk, "l_up": l_up,
            "lampnet": lampnet,
            "ncells": len(dust) + len(cob) + len(rep) + len(comp) + len(torch)}


def _dust_lvl(c, st, pw, pbs, tl, ron, con, inp, O):
    """Dust level, lane-wise. Mirrors sim._run_vec's dust_lvl term for term and
    IN ITS ORIGINAL ORDER, because the order is observable: a comparator facing
    this cell returns its output outright. Lanes a hard term (=>15) already
    decided are carried in `hard` and masked out of everything after, which is
    what a per-vector `return` does.

    The guard-bit dec/max are INLINED here rather than called on _Ops: this is
    the hot loop, run once per dust cell per event, and at ~34k cells a Python
    call per operation costs more than the arithmetic it wraps.
    """
    ones, high, valm = O.ones, O.high, O.valm
    live = high
    hard = 0
    lv = 0
    if st["d_below"][c][0]:
        h = tl.get((c[0], c[1] - 1, c[2]), 0)
        hard |= h
        live ^= h
    if st["d_below"][c][1]:
        h = pbs.get((c[0], c[1] - 1, c[2]), 0)
        hard |= h
        live ^= h
    for m, code, payload, cup, cdn in st["d_dirs"][c]:
        if not live:
            break
        if code == 1:
            h = live & tl.get(m, 0)
        elif code == 2:
            h = live & inp[payload]
        elif code == 3:
            h = live
        elif code == 4:
            h = live & pbs.get(m, 0)
        elif code == 6:
            h = live & ron.get(m, 0)
        else:
            h = 0
        if h:
            hard |= h
            live ^= h
            if not live:
                break
        lm = live - (live >> SHIFT)      # HIGH mask -> 0x1F per undecided lane
        if code == 5:
            a = lv & lm
            t = (pw.get(m, 0) | high) - ones
            k = t & high
            k -= k >> SHIFT
            b = t & valm & k & lm
            g = ((a | high) - b) & high    # lane-wise a >= b
            g -= g >> SHIFT
            lv = (a & g) | (b & (valm ^ g))
        elif code == 7:
            # every undecided lane returns here; `lv` is discarded, exactly as
            # the original `return con.get(m, 0)`
            h = live >> SHIFT
            return O.f15(hard) | (con.get(m, 0) & (live - h))
        if cup is not None:
            a = lv & lm
            t = (pw.get(cup, 0) | high) - ones
            k = t & high
            k -= k >> SHIFT
            b = t & valm & k & lm
            g = ((a | high) - b) & high
            g -= g >> SHIFT
            lv = (a & g) | (b & (valm ^ g))
        if cdn is not None:
            a = lv & lm
            t = (pw.get(cdn, 0) | high) - ones
            k = t & high
            k -= k >> SHIFT
            b = t & valm & k & lm
            g = ((a | high) - b) & high
            g -= g >> SHIFT
            lv = (a & g) | (b & (valm ^ g))
    return O.f15(hard) | (lv & (live - (live >> SHIFT)))


def _cob_state(c, st, pw, pb, pbs, tl, ron, inp, O):
    """(weakly powered, strongly powered) for a block, lane-wise."""
    pwrd = 0
    for m in st["c_dust"][c]:
        pwrd |= O.nz(pw.get(m, 0))
    strong = 0
    if st["c_rblk"][c]:
        pwrd |= O.high
        strong = O.high
    for m in st["c_lev"][c]:
        pwrd |= inp[m]
        strong |= O.high
    for m in st["c_torch"][c]:
        pwrd |= tl.get(m, 0)
        strong |= O.high
    for m in st["c_rep"][c]:
        pwrd |= ron.get(m, 0)
        strong |= O.high
    if st["c_up"][c] is not None:
        pwrd |= O.nz(pw.get(st["c_up"][c], 0))
    return pwrd, strong


def _lev(spec, pw, pbs, tl, ron, con, inp, O):
    """Level a comparator spec contributes, lane-wise."""
    if spec is None:
        return 0
    k = spec[0]
    if k == "d":
        return pw.get(spec[1], 0)
    if k == "l":
        return O.f15(inp[spec[1]])
    if k == "t":
        return O.f15(tl.get(spec[1], 0))
    if k == "r":
        return O.f15all if len(spec) == 1 else O.f15(ron.get(spec[1], 0))
    if k == "c":
        return O.f15(pbs.get(spec[1], 0))
    if k == "k":
        return con.get(spec[1], 0)
    return 0


def _on(spec, pw, pb, tl, ron, con, inp, O):
    """Boolean a repeater spec contributes, lane-wise."""
    if spec is None:
        return 0
    k = spec[0]
    if k == "d":
        return O.nz(pw.get(spec[1], 0))
    if k == "c":
        return pb.get(spec[1], 0)
    if k == "l":
        return inp[spec[1]]
    if k == "t":
        return tl.get(spec[1], 0)
    if k == "r":
        return O.high if len(spec) == 1 else ron.get(spec[1], 0)
    if k == "k":
        return O.nz(con.get(spec[1], 0))
    return 0


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


def run(ins, blocks, io, combos, tick_cap, step_cap, stall, state_out=None):
    """Simulate every vector in `combos` in one pass.

    Returns (lamps, ticks): lamps maps net -> HIGH mask whose lane L bit is set
    iff that net's lamp is lit under combos[L]. A caller compares against a
    bit-parallel eval_net with one XOR per net, not 1024 comparisons.
    Raises Indecisive if any lane fails to settle.
    """
    nl = len(combos)
    O = _Ops(nl)
    inp = {}
    for name in ins:
        m = 0
        for l, v in enumerate(combos):
            if v[name]:
                m |= 1 << (l * LANE + SHIFT)
        inp[name] = m
    st = _pre(blocks, io, inp)
    dust, cob, rep, comp = st["dust"], st["cob"], st["rep"], st["comp"]
    torch = st["torch"]
    pw, pb, pbs, tl, ron, con = {}, {}, {}, {}, {}, {}
    nz, wake, repdelay = O.nz, st["wake"], st["repdelay"]
    high = O.high

    RING = 5                       # longest delay is 4, so 5 slots never collide
    buckets = [[] for _ in range(RING)]
    b0 = buckets[0]
    for c in dust:
        b0.append(("d", c))
    for c in cob:
        b0.append(("c", c))
    for c in torch:
        b0.append(("t", c))
    for c in rep:
        b0.append(("r", c))
    for c in comp:
        b0.append(("k", c))
    alive = len(b0)
    steps = now = idle = 0
    stall_cap = max(stall, 3 * st["ncells"])
    tsched, rsched, ksched = set(), set(), set()
    flips = {}
    recent = []                    # rolling window of change masks, for triage

    while alive:
        if now > tick_cap or steps > step_cap:
            why = "tick cap" if now > tick_cap else "step cap"
            lanes = set()
            for m in recent:
                for l in range(nl):
                    if m >> (l * LANE + SHIFT) & 1:
                        lanes.add(l)
            raise Indecisive(lanes, _churn(flips), now, steps, why)
        i = now % RING
        items = buckets[i]
        if not items:
            now += 1
            idle += 1
            if idle > stall_cap:
                raise Indecisive(range(nl), _churn(flips), now, steps, "stall")
            continue
        idle = 0
        buckets[i] = []
        alive -= len(items)
        here = buckets[i]      # same-tick wakes land in this slot
        hset = set()      # ...and this dedups them (see run_scalar) fresh list
        for kind, c in items:
            steps += 1
            if kind == "d":
                v = _dust_lvl(c, st, pw, pbs, tl, ron, con, inp, O)
                old = pw.get(c, 0)
                if old != v:
                    pw[c] = v
                    flips[c] = flips.get(c, 0) + 1
                    idle = 0
                    recent.append(nz(v) ^ nz(old))
                    del recent[:-8]
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "c":
                pwrd, strong = _cob_state(c, st, pw, pb, pbs, tl, ron, inp, O)
                opb, ops = pb.get(c, 0), pbs.get(c, 0)
                if opb != pwrd or ops != strong:
                    pb[c], pbs[c] = pwrd, strong
                    flips[c] = flips.get(c, 0) + 1
                    idle = 0
                    recent.append((opb ^ pwrd) | (ops ^ strong))
                    del recent[:-8]
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "t":
                if c in tsched or st["t_dead"][c]:
                    continue
                if (~pb.get(st["t_att"][c], 0)) & high != tl.get(c, 0):
                    tsched.add(c)
                    buckets[(now + 1) % RING].append(("T", c))
                    alive += 1
            elif kind == "T":
                tsched.discard(c)
                v = (~pb.get(st["t_att"][c], 0)) & high
                old = tl.get(c, 0)
                if old != v:
                    tl[c] = v
                    flips[c] = flips.get(c, 0) + 1
                    idle = 0
                    recent.append(old ^ v)
                    del recent[:-8]
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "r":
                if c in rsched:
                    continue
                if _on(st["r_src"][c], pw, pb, tl, ron, con, inp, O) \
                        != ron.get(c, 0):
                    rsched.add(c)
                    buckets[(now + repdelay.get(c, 1)) % RING].append(("R", c))
                    alive += 1
            elif kind == "R":
                rsched.discard(c)
                v = _on(st["r_src"][c], pw, pb, tl, ron, con, inp, O)
                if ron.get(c, 0) != v:
                    ron[c] = v
                    idle = 0
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1
            elif kind == "k":
                if c in ksched:
                    continue
                if _comp_out(c, st, pw, pbs, tl, ron, con, inp, O) != con.get(c, 0):
                    ksched.add(c)
                    buckets[(now + 1) % RING].append(("K", c))
                    alive += 1
            elif kind == "K":
                ksched.discard(c)
                v = _comp_out(c, st, pw, pbs, tl, ron, con, inp, O)
                if con.get(c, 0) != v:
                    con[c] = v
                    idle = 0
                    for k2, c2 in wake[c]:
                        if c2 not in hset:
                            hset.add(c2)
                            here.append((k2, c2))
                            alive += 1

    if state_out is not None:
        state_out.update(pw=pw, pb=pb, pbs=pbs, tl=tl, ron=ron, con=con)
    lamps = {}
    for cell, net in st["lampnet"].items():
        m = 0
        for a in st["l_arm"][cell]:
            m |= nz(pw.get(a, 0))
        if st["l_up"][cell] is not None:
            m |= nz(pw.get(st["l_up"][cell], 0))
        for b in st["l_cob"][cell]:
            m |= pb.get(b, 0)
        for t in st["l_torch"][cell]:
            m |= tl.get(t, 0)
        if st["l_rblk"][cell]:
            m |= high
        for nm in st["l_lev"][cell]:
            m |= inp[nm]
        lamps[net] = lamps.get(net, 0) | m
    return lamps, now


def _churn(flips):
    return sorted((c for c, k in flips.items() if k >= 3), key=lambda c: -flips[c])


def eval_net_par(ins, gates, outputs, combos):
    """eval_net over every vector at once: one nl-lane bitwise pass.

    Same Gauss-Seidel sweep as recipe.eval_net, but each signal is a HIGH
    mask, so "and" is "&" and the whole circuit costs ~80 bigint ops instead
    of gates x vectors Python-level evaluations.
    """
    nl = len(combos)
    O = _Ops(nl)
    sig = {"0": 0, "1": O.high}
    for name in ins:
        m = 0
        for l, v in enumerate(combos):
            if v[name]:
                m |= 1 << (l * LANE + SHIFT)
        sig[name] = m
    for _ in range(20):
        before = dict(sig)
        for g in gates:
            a = [sig.get(x) for x in g["args"]]
            if any(x is None for x in a):
                bad = [x for x, y in zip(g["args"], a) if y is None]
                raise KeyError(f"eval_net_par reads undefined signal {bad[0]!r}")
            op = g["op"]
            if op == "AND":
                sig[g["out"]] = a[0] & a[1]
            elif op == "OR":
                sig[g["out"]] = a[0] | a[1]
            elif op == "XOR":
                sig[g["out"]] = a[0] ^ a[1]
            elif op == "NOT":
                sig[g["out"]] = ~a[0] & O.high
            elif op == "LATCH":
                o = g["out"]
                sig[o + "~qb"] = ~(a[0] | sig.get(o, 0)) & O.high
                sig[o] = ~(a[1] | sig.get(o + "~qb", 0)) & O.high
            else:
                raise ValueError(f"eval_net_par: unknown op {op!r}")
        if sig == before:
            break
    else:
        raise ValueError("no stable state (oscillating loop?)")
    missing = [n for n in outputs if n not in sig]
    if missing:
        raise KeyError(f"output {missing[0]!r} is never driven")
    return sig, O


def lanes_of(mask, nl):
    """HIGH mask -> the lane indices it selects."""
    return [l for l in range(nl) if mask >> (l * LANE + SHIFT) & 1]


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
        elif code == 4:
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
               stall=None, snap_at=None):
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
        attach_rev, comp, leveratt = ctx
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
    for c in cob:
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
# ponytail: measured reality of the SWAR path on alu4 (34672 blocks, 1024
# vectors, 20 cores), because it decides the whole design:
#     8 lanes   1.13s     32 lanes  1.27s    128 lanes 1.54s
#   -> where lanes converge together they SHARE events and this is ~110x.
#     256-1023 -> 6 of 8 x 128-lane shards burn a 4M-step budget; at 20M steps
#     they are still going (tick 4090). Merged event count is ~sum(lane), not
#     max(lane), so one hard vector costs the whole shard its serial cost
#     x shard_size. On this build SWAR is a big win on the easy vectors and a
#     LOSS on the hard ones, and the hard ones dominate.
# Also: a single run over all 1024 lanes can NEVER terminate if any one vector
# hunts, because sim's torch-burnout rule -- a termination device -- is not
# reimplemented here. Hence shards, hard bounds, and a fallback.
#
# So the default driver is the boring one: vectors across cores, serial engine,
# which is a fixed ~ncores speedup and cannot stall. SWAR is per shard and
# opt-in (REDSTONE_VEC_SWAR=1); a shard that does not settle inside its budget
# falls back to the serial engine for those vectors, so the verdict always
# comes from an engine that finished.

_W = {}


def _init_worker(blocks, io, gates, outputs, ins, tick_cap, stall):
    _W.update(blocks=blocks, io=io, gates=gates, outputs=outputs, ins=ins,
              tick_cap=tick_cap, stall=stall)


def _serial_shard(combos):
    """The authority, one vector at a time. Bounded by sim's own caps.

    Uses run_scalar (the table-driven twin, proven bit-identical by
    scratch/diff_engine.py) and falls back to sim._run_vec whenever run_scalar
    declines -- i.e. when a latch hold-seed is involved, which run_scalar does
    not implement and refuses rather than guessing.
    """
    from sim import _parse_build, _run_vec
    from recipe import eval_net
    P = _parse_build(_W["blocks"], _W["io"])
    ins, gates, outs = _W["ins"], _W["gates"], _W["outputs"]
    rec = {"inputs": ins, "gates": gates, "outputs": outs}
    bad, ticks = [], 0
    scalar = True
    for vec in combos:
        try:
            got, live, tlv, tk, rlv, cn = run_scalar(vec, P)
        except NotImplementedError:
            scalar = False
            break
        except RuntimeError as e:
            bad.append((vec, "RED", str(e)[:80], None))
            continue
        ticks = max(ticks, tk)
        exp = eval_net(rec, vec)
        for net in outs:
            if bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, bool(got.get(net, False)), bool(exp[net])))
    if not scalar:                      # latch path: authority only
        for vec in combos:
            try:
                got, live, tlv, tk, rlv, cn = _run_vec(vec, None, P, until=None)
            except RuntimeError as e:
                bad.append((vec, "RED", str(e)[:80], None))
                continue
            ticks = max(ticks, tk)
            exp = eval_net(rec, vec)
            for net in outs:
                if bool(got.get(net, False)) != bool(exp[net]):
                    bad.append((vec, net, bool(got.get(net, False)),
                                bool(exp[net])))
    return bad, ticks, []


def _swar_shard(combos, step_cap):
    """Try the bit-parallel engine on this shard.

    Returns (bad, ticks) on success, or None if it cannot decide -- in which
    case the caller re-dispatches those vectors ONE PER TASK. Bundling the
    fallback into the same shard is what made a 1024-vector run take 20
    minutes: a shard containing one hunting vector held a worker for the whole
    serial sweep of all 8 of its vectors while 19 workers sat idle.
    """
    ins, gates, outs = _W["ins"], _W["gates"], _W["outputs"]
    try:
        lamps, tk = run(ins, _W["blocks"], _W["io"], combos, _W["tick_cap"],
                        step_cap, _W["stall"])
        sig, _O = eval_net_par(ins, gates, outs, combos)
    except (Indecisive, Exception):               # noqa: BLE001
        return None
    nl = len(combos)
    full = (1 << (nl * LANE)) - 1
    bad = []
    for net in outs:
        lm = lamps.get(net, 0)
        d = (lm ^ sig[net]) & full
        if d:
            for l in lanes_of(d, nl):
                bad.append((combos[l], net, l in lanes_of(lm, nl),
                            bool(sig[net] >> (l * LANE + SHIFT) & 1)))
    return bad, tk


def _shard_job(combos):
    if _W.get("swar") and len(combos) > 1:
        got = _swar_shard(combos, _W["swar_cap"])
        if got is not None:
            bad, tk = got
            return bad, tk, []
        return [], 0, list(combos)        # could not decide: re-dispatch singly
    return _serial_shard(combos)


def verify_par(ins, gates, outputs, blocks, io, combos, workers=None,
               shard=None, tick_cap=20000, step_cap=4000000, stall=5000,
               swar=None, progress=None):
    """Verify every vector in `combos`. Returns (bad, max_ticks).

    bad is a list of (vec, net, got, want), the same shape sim.sim_verify
    raises on, so the caller reports it identically. Two passes: the SWAR
    shards first, then whatever they could not decide re-dispatched one vector
    per task so the pool can balance the stragglers.
    """
    import multiprocessing as _mp
    swar = int(_os.environ.get("REDSTONE_VEC_SWAR", "1")) if swar is None else swar
    n = max(1, min(workers or (_os.cpu_count() or 1), len(combos)))
    shard = shard or max(1, len(combos) // (n * 4) or 1)
    init = (blocks, io, gates, outputs, ins, tick_cap, stall)
    ctx = _mp.get_context("spawn")
    bad, ticks, retry = [], 0, []
    total = max(1, len(combos) // shard)

    def drain(it):
        nonlocal bad, ticks
        for b, t, r in it:
            bad += b
            ticks = max(ticks, t)
            retry.extend(r)

    _init_worker(*init)
    _W["swar"], _W["swar_cap"] = swar, step_cap
    shards = [combos[i:i + shard] for i in range(0, len(combos), shard)]
    seen = [0]

    def drain(it, total, label=""):
        # ponytail: the parent blocks in imap_unordered at 0% CPU by design
        # while the workers grind, so a silent parent is indistinguishable
        # from a hung one. Count here, in the consumer, because a closure
        # defined in verify_par cannot be pickled to a spawn worker.
        nonlocal bad, ticks
        for res in it:
            b, t = res[0], res[1]
            bad += b
            ticks = max(ticks, t)
            if len(res) > 2:
                retry.extend(res[2])
            seen[0] += 1
            if progress and (seen[0] % 8 == 0 or seen[0] == total):
                progress(seen[0], total, 0.0)

    if n == 1:
        drain(map(_shard_job, shards), len(shards))
        drain(map(_serial_shard, ([v] for v in retry)), len(retry))
        return bad, ticks
    with ctx.Pool(n, initializer=_init_worker, initargs=init) as pool:
        drain(pool.imap_unordered(_shard_job, shards), len(shards))
        if retry:
            if progress:
                print("   SWAR settled most shards; re-dispatching %d vectors "
                      "one per task for load balance" % len(retry), flush=True)
            seen[0] = 0
            drain(pool.imap_unordered(_serial_shard, ([v] for v in retry)),
                  len(retry))
    return bad, ticks


if __name__ == "__main__":
    # ponytail: one runnable check, and it is the only one that matters -- the
    # bit-parallel engine must agree with the serial engine BIT for BIT, or it
    # is not a faster verifier, it is a wrong one. Routed through the real
    # router, then compared vector by vector against sim._run_vec.
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
    _lamps, _ticks = run(_ins, _blocks, _io, _combos, 20000, 2000000, 5000)
    _sig, _O = eval_net_par(_ins, _r["gates"], _r["outputs"], _combos)
    assert _lamps["y"] == _sig["y"], (lanes_of(_lamps["y"], 8),
                                       lanes_of(_sig["y"], 8))
    _sel = lanes_of(_lamps["y"], len(_combos))
    for _k, _vec in enumerate(_combos):
        _serial = _run_vec(_vec, None, _P)[0]["y"]
        assert _serial == (_k in _sel), (_k, _vec, _serial, _k in _sel)
    print(f"simvec ok: {len(_combos)} vectors, bit-identical to "
          f"sim._run_vec, {_ticks} ticks")