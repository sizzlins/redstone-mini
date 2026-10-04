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


def _spread21(v):
    """Interleave 21 bits of v into every other bit position (Z-order)."""
    v &= 0x1FFFFF
    v = (v | (v << 32)) & 0x1F00000000FFFF
    v = (v | (v << 16)) & 0x1F0000FF0000FF
    v = (v | (v << 8)) & 0x100F00F00F00F00F
    v = (v | (v << 4)) & 0x10C30C30C30C30C3
    v = (v | (v << 2)) & 0x1249249249249249
    return v


def _morton_order(cells):
    """Z-order the cells, so a cell's neighbours land NEAR it in id space.

    ponytail: this is a pure RELABELLING. Every table is id-indexed, so the
    physics cannot see it -- scratch/tbl_diff.py proves the two engines
    bit-identical across it, and the event logs stay identical. It exists
    because ids from sorted((x,y,z)) put a cell's eight physically-adjacent
    neighbours thousands of ids apart, so every wake edge was a random access
    into a 31 MB table. Measured cost of that, per vector: 0.233s alone,
    0.377s with 4 workers, 0.775s with 16 -- a 3.3x inflation from
    concurrency alone, which capped effective parallelism at ~4.8x on 16
    workers and was the single largest remaining loss. Interleaving the bits
    of x/y/z puts a cell and its 3x3x3 neighbourhood within a few hundred ids
    of each other, so the wake walk is a scan, not a scatter.

    Only DETERMINISM is required, not Morton-ness: this is a locality
    heuristic, so a coordinate past 21 bits merely loses locality and the
    ordering stays a valid total order. Two workers must still agree on the
    ids, which is why the key is a pure function of the cell.
    """
    ox = min(c[0] for c in cells)
    oy = min(c[1] for c in cells)
    oz = min(c[2] for c in cells)
    return sorted(cells, key=lambda c: (_spread21(c[0] - ox)
                                        | (_spread21(c[1] - oy) << 1)
                                        | (_spread21(c[2] - oz) << 2)))


def _tables_from(P, inp):
    """Precompute every static query the physics asks, once per build.

    This is the boring half of the win and arguably the bigger one:
    sim._run_vec re-derives the neighbourhood on every event (tuple
    construction, four direction scans, a dust_points call per powered
    neighbour). The build is static, so every one of those queries has a
    constant answer. Hoisting them turns the inner loop from "walk 26
    neighbours and ask what each one is" into "walk a short list of cells
    already known to matter".

    ponytail: every table is indexed by a dense CELL ID (an int), not by the
    (x,y,z) tuple. Measured on alu4 (71560 blocks, 71542 cells) the tuple-keyed
    form cost 112 MB and 7.78s to build: `wake` alone was 59 MB because it
    stored a (kind, cell) 2-tuple per edge, and `d_dirs` 28 MB because each of
    30582 dust cells held four 5-tuples that each embedded another cell tuple.
    Three things come out of the rewrite, and they are the same change:

      - MEMORY. 112 MB -> ~20 MB per worker. At hier_verify's 16 workers that
        is the difference between fitting in RAM and thrashing, which is what
        the handoff could not explain about "8 concurrent children run 2.1x
        slower each than one alone".
      - CACHE. The working set per worker drops below L3 instead of streaming
        112 MB of pointer-chasing structures through it on every settle.
      - SPEED. A bytearray index beats `dict.get(tuple_key, default)`: no
        tuple hash, no compare, and the result is a small int that already
        exists. `pw`/`pb`/`pbs`/`tl`/`ron`/`con` are all bytearrays now.

    The `wake` table also stops carrying a kind. Each cell has exactly one
    type, so (kind, cell) was redundant: the ring bucket holds bare ids and the
    kind comes from `kind[id]`. That deletes ~340k tuple allocations per vector
    (measured 1699175 appends / 5 vectors) and makes the hset a set of ints
    instead of a set of hashed 3-tuples.
    """
    dust, torch, rep, rblk, cob, repdelay, lever, lampnet, \
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

    # ---- cell ids: one dense int per cell the tables can name -----------
    # Z-order, not sorted(): both are deterministic functions of the build (so
    # two workers always agree on the ids), but sorting lays the field out along
    # x and leaves a cell's eight neighbours thousands of ids apart, which
    # costs 3.3x under concurrency. See _morton_order.
    uni = set()
    for d in (dust, pwr, rep, comp, torch, lampnet, lever, rblk, glass, slab,
              target, attach_rev, leveratt):
        uni |= set(d)
    for v in leveratt.values():
        if v is not None:           # a lever may attach to its OWN cell (None)
            uni.add(v)
    for c in torch:                       # torch attachment blocks
        a = torch[c]
        if a is not None:
            uni.add(a)
    for v in attach_rev.values():
        uni |= set(v)
    cell = _morton_order(uni)
    nid = len(cell)
    cid = {c: i for i, c in enumerate(cell)}

    # kind: what evaluation this cell needs when it is popped off the ring.
    # ponytail: the ORIGINAL per-direction order inside _dust_lvl_s was never
    # load-bearing, and dropping it is what lets d_dirs split by class. Codes
    # 1/2/3/4/6/8 all `return 15` and 15 is the maximum level, so whichever
    # fires first the answer is 15; codes 5/7 and the cup/cdn terms only
    # accumulate a max, and max does not care about order. So the answer is
    # "15 if any fifteen-source, else the largest decay term" either way.
    K_D, K_C, K_T, K_R, K_K, K_X = 0, 1, 2, 4, 6, 9
    kind = bytearray([K_X]) * nid
    for c in dust:
        kind[cid[c]] = K_D
    for c in pwr:
        kind[cid[c]] = K_C
    for c in torch:
        kind[cid[c]] = K_T
    for c in rep:
        kind[cid[c]] = K_R
    for c in comp:
        kind[cid[c]] = K_K
    dust_ids = tuple(cid[c] for c in dust)
    pwr_ids = tuple(cid[c] for c in pwr)
    torch_ids = tuple(cid[c] for c in torch)
    rep_ids = tuple(cid[c] for c in rep)
    comp_ids = tuple(cid[c] for c in comp)

    # ---- dust: one list per SOURCE CLASS -------------------------------
    # ponytail: E is a shared empty tuple. Most cells have no neighbour in
    # most classes, so `[E] * nid` costs 8 bytes a cell instead of building an
    # empty list per cell per class (8 x 71542 list objects before).
    E = ()
    d_torch = [E] * nid
    d_lev = [E] * nid
    d_cob = [E] * nid
    d_dust = [E] * nid
    d_rep = [E] * nid
    d_comp = [E] * nid
    d_cup = [E] * nid
    d_cdn = [E] * nid
    d_rblk = bytearray(nid)
    d_bt = [-1] * nid          # cell BELOW, if it is a torch
    d_bp = [-1] * nid          # cell BELOW, if it holds power
    for c in dust:
        i = cid[c]
        x, y, z = c
        below = (x, y - 1, z)
        if below in torch:
            d_bt[i] = cid[below]
        if below in pwr:
            d_bp[i] = cid[below]
        lt = ll = lc = ld = lr = lk = lu = ln = None
        for dx, dz in DIRS:
            m = (x + dx, y, z + dz)
            # code: 1 torch, 2 lever, 3 redstone block, 4 cobble, 5 dust,
            #       6 repeater feeding c, 7 comparator feeding c, 8 slab
            code = 0
            if m in torch:
                code = 1
            elif m in lever:
                code = 2
            elif m in rblk:
                code = 3
            elif m in cob:
                code = 4
            elif m in slab:
                code = 8     # powerable like 4, but transparent: never an
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
            if code == 1:
                lt = (cid[m],) if lt is None else lt + (cid[m],)
            elif code == 2:
                ll = (lever[m],) if ll is None else ll + (lever[m],)
            elif code == 3:
                d_rblk[i] = 1
            elif code == 4 or code == 8:
                lc = (cid[m],) if lc is None else lc + (cid[m],)
            elif code == 5:
                ld = (cid[m],) if ld is None else ld + (cid[m],)
            elif code == 6:
                lr = (cid[m],) if lr is None else lr + (cid[m],)
            elif code == 7:
                lk = (cid[m],) if lk is None else lk + (cid[m],)
            up = (x + dx, y + 1, z + dz)
            if up in dust and code == 4 and (x, y + 1, z) not in cob:
                lu = (cid[up],) if lu is None else lu + (cid[up],)
            dn = (x + dx, y - 1, z + dz)
            if dn in dust and code != 4 and (x, y - 1, z) in sup:
                ln = (cid[dn],) if ln is None else ln + (cid[dn],)
        if lt is not None:
            d_torch[i] = lt
        if ll is not None:
            d_lev[i] = ll
        if lc is not None:
            d_cob[i] = lc
        if ld is not None:
            d_dust[i] = ld
        if lr is not None:
            d_rep[i] = lr
        if lk is not None:
            d_comp[i] = lk
        if lu is not None:
            d_cup[i] = lu
        if ln is not None:
            d_cdn[i] = ln

    # ---- cobble/solid: weak power, strong power -------------------------
    # ponytail: loop runs over pwr (cobble/stone + slabs); glass never holds
    # power so it needs no row. Empty delta when slabs are absent.
    # ponytail: below-feeds mirror sim cob_state (torch/dust beneath powers
    # solid; see sim.py). Below-dust carries no pointing condition, same as
    # sim; torch/rblk/lever keep their same-y conditions.
    c_dust = [E] * nid
    c_rep = [E] * nid
    c_torch = [E] * nid
    c_lev = [E] * nid
    c_rblk = bytearray(nid)
    c_up = [-1] * nid
    for c in pwr:
        i = cid[c]
        x, y, z = c
        dd = rr = tt = ll = None
        rb = False
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust and (-d[0], -d[1]) in dust_points(m, dust, target):
                dd = (cid[m],) if dd is None else dd + (cid[m],)
            if m in rep and back(m, c):
                rr = (cid[m],) if rr is None else rr + (cid[m],)
            if m in torch and torch[m] != c:
                tt = (cid[m],) if tt is None else tt + (cid[m],)
            if (m in lever and _LEVPOW
                    and leveratt.get(m) in (None, c)):
                ll = (lever[m],) if ll is None else ll + (lever[m],)
            if m in rblk:
                rb = True
        dn = (x, y - 1, z)
        if dn in dust:
            dd = (cid[dn],) if dd is None else dd + (cid[dn],)
        if dn in torch and torch[dn] != c:
            tt = (cid[dn],) if tt is None else tt + (cid[dn],)
        if dn in rblk:
            rb = True
        if (dn in lever and _LEVPOW and leveratt.get(dn) in (None, c)):
            ll = (lever[dn],) if ll is None else ll + (lever[dn],)
        if dd is not None:
            c_dust[i] = dd
        if rr is not None:
            c_rep[i] = rr
        if tt is not None:
            c_torch[i] = tt
        if ll is not None:
            c_lev[i] = ll
        if rb:
            c_rblk[i] = 1
        up = (x, y + 1, z)
        if up in dust:
            c_up[i] = cid[up]

    # ---- repeater input, delay, lock sides ------------------------------
    # spec codes shared with _lev_s / _rep_on_s:
    #   1 dust cell, 2 lever NAME, 3 torch cell, 4 redstone block (always 15),
    #   5 repeater cell, 6 powerable solid cell, 7 comparator cell, 8 nothing.
    # A lever spec carries a NAME, not a cell: `vec` is keyed by net name, so
    # that one payload stays a string. Levers are ~10 per build, so it costs
    # nothing to keep the rare case rare.
    r_src = [None] * nid
    r_side = [None] * nid
    r_delay = [1] * nid
    for c in rep:
        i = cid[c]
        d = rep[c]
        r_delay[i] = repdelay.get(c, 1)
        b = (c[0] - d[0], c[1], c[2] - d[1])
        if b in dust:
            r_src[i] = (1, cid[b])
        elif b in pwr:
            r_src[i] = (6, cid[b])
        elif b in lever:
            r_src[i] = (2, lever[b])
        elif b in rblk:
            r_src[i] = (4, -1)
        elif b in rep:
            r_src[i] = (5, cid[b]) if back(b, c) else None
        elif b in comp:
            r_src[i] = (7, cid[b]) if back(b, c) else None
        else:
            r_src[i] = None

    def rside(cellc, t):
        # ponytail: ONLY a repeater/comparator facing into the side locks
        # (wiki Repeater page + cmc, both explicit). Dust, blocks, levers,
        # torches and redstone blocks beside a repeater do NOT lock -- the
        # old branches modeled the same phantom sim just deleted.
        if cellc in rep:
            return (5, cid[cellc]) if back(cellc, t) else None
        if cellc in comp:
            return (7, cid[cellc]) if back(cellc, t) else None
        return None

    for c in rep:
        d = rep[c]
        r_side[cid[c]] = (rside((c[0] + d[1], c[1], c[2] + d[0]), c),
                          rside((c[0] - d[1], c[1], c[2] - d[0]), c))

    # ---- comparator: rear input, two sides, mode ------------------------
    # ponytail: sides mirror sim.comp_in (dust, redstone blocks per wiki
    # 15w47a, facing-in repeaters/comparators). Levers, torches, plain
    # blocks and target do not feed sides.
    def side(cellc, t):
        if cellc in rblk:
            return (4, -1)
        if cellc in rep:
            return (5, cid[cellc]) if back(cellc, t) else None
        if cellc in comp:
            return (7, cid[cellc]) if back(cellc, t) else None
        if cellc in dust:
            return (1, cid[cellc])
        return None

    k_rear = [None] * nid
    k_side = [None] * nid
    k_mode = [None] * nid
    for c in comp:
        i = cid[c]
        rx, rz = comp[c]["rear"]
        rear = (c[0] + rx, c[1], c[2] + rz)
        if rear in dust:
            k_rear[i] = (1, cid[rear])
        elif rear in lever:
            k_rear[i] = (2, lever[rear])
        elif rear in rblk:
            k_rear[i] = (4, -1)
        elif rear in torch:
            k_rear[i] = (3, cid[rear])
        elif rear in rep:
            k_rear[i] = (5, cid[rear]) if back(rear, c) else (8, -1)
        elif rear in comp:
            k_rear[i] = (7, cid[rear]) if back(rear, c) else (8, -1)
        elif rear in pwr:
            # ponytail: strong-block rear read (mirrors sim; the solid term is
            # strong-powered only, so the mirror is exact).
            k_rear[i] = (6, cid[rear])
        else:
            k_rear[i] = (8, -1)
        k_side[i] = (side((c[0] + rz, c[1], c[2] + rx), c),
                     side((c[0] - rz, c[1], c[2] - rx), c))
        k_mode[i] = comp[c]["mode"]

    # ---- torch: attachment block, and whether it is dead ----------------
    t_att = [0] * nid
    t_dead = bytearray(nid)
    for c in torch:
        a = torch[c]
        i = cid[c]
        # ponytail: -1 means "no attachment block". sim reads it as
        # `pb.get(None, False)` -- an absent host, i.e. unpowered -- so a torch
        # with no attachment block reads as always lit. Must NOT index pb[-1]:
        # that is a real cell (the last id) and would silently wire the torch
        # to whatever happens to live there.
        t_att[i] = cid[a] if a is not None else -1
        t_dead[i] = 1 if (a is not None and a in rblk) else 0

    # ---- wake map: every cell -> the cells its change re-evaluates -------
    # ponytail: bare ids, no kind (see the module note). slab vertices
    # included (slab power changes must propagate); glass excluded (never
    # changes). Edges join pwr.
    wake = [E] * nid
    for c in set(dust) | pwr | set(rep) | set(comp) | set(torch):
        i = cid[c]
        x, y, z = c
        out = []
        for d in DIRS:
            m = (x + d[0], y, z + d[1])
            if m in dust:
                out.append(cid[m])
            elif m in pwr:
                out.append(cid[m])
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
                    out.append(cid[m])
            elif m in comp:
                out.append(cid[m])
        for vy in (1, -1):
            m = (x, y + vy, z)
            if m in dust:
                out.append(cid[m])
            elif m in pwr:
                out.append(cid[m])
        for d in DIRS:
            for vy in (1, -1):
                m = (x + d[0], y + vy, z + d[1])
                if m in dust:
                    out.append(cid[m])
        for t in attach_rev.get(c, ()):
            out.append(cid[t])
        wake[i] = out

    # ponytail: repeater lock sides wake their repeater (mirrors sim's
    # wake fix: a side lighting mid-run must re-evaluate, or a lock
    # engages/releases silently stale). Static neighbors (lever/rblk)
    # never emit, so their edges cost nothing.
    lock_edges = []
    for c in rep:
        i = cid[c]
        d = rep[c]
        for s in ((c[0] + d[1], c[1], c[2] + d[0]),
                  (c[0] - d[1], c[1], c[2] - d[0])):
            j = cid.get(s)
            if j is None:
                # A cell beside a repeater that is not itself simulated (air,
                # mostly) can never change value, so the old `wake.setdefault(s,
                # [])` wrote an entry nothing ever read. Skip it rather than
                # widen the id universe with dead cells.
                continue
            if i in wake[j]:
                continue
            lock_edges.append((j, i))
            if isinstance(wake[j], list):
                wake[j].append(i)
            else:
                wake[j] = [i]      # was the shared empty tuple

    # ---- lamp arms ------------------------------------------------------
    l_arm = [E] * nid
    l_cob = [E] * nid
    l_torch = [E] * nid
    l_lev = [E] * nid
    l_rblk = bytearray(nid)
    l_up = [-1] * nid
    for lc in lampnet:
        i = cid[lc]
        x, y, z = lc
        arms = []
        for d in DIRS:
            if all((x + d[0] + e[0], y, z + d[1] + e[1]) not in dust
                   for e in DIRS if e != d):
                a = (x + d[0], y, z + d[1])
                # Only a dust arm can ever read a level: pw is written for dust
                # cells and nothing else, so a non-dust arm was always 0 and
                # keeping it just meant naming a cell with no id.
                if a in dust:
                    arms.append(cid[a])
        l_arm[i] = tuple(arms)
        l_cob[i] = tuple(cid[m] for m in _orth(lc) if m in pwr)
        l_torch[i] = tuple(cid[m] for m in _orth(lc)
                           if m in torch and torch[m] != lc)
        l_lev[i] = tuple(lever[m] for m in _orth(lc) if m in lever)
        if any(m in rblk for m in _orth(lc)):
            l_rblk[i] = 1
        up = (x, y + 1, z)
        if up in dust:
            l_up[i] = cid[up]

    # ---- exact wake: drop edges no relation can ever read ----------------
    # ponytail: `wake` above is GEOMETRIC -- every cell that changes wakes all
    # ~26 cells around it, because geometry is where a dependency could hide.
    # But run_scalar reads a cell variable only through the named relations
    # below, so most of that walk is provably dead. Measured on alu4 with
    # scratch/wake_need.py: 279376 geometric edges vs 126946 real
    # dependencies -- **54.6% dead**, and ZERO of the real dependencies were
    # missing from the geometric map, so the exact map is a strict SUBSET.
    #
    # Why subset + order-preserving makes this safe rather than hopeful:
    #   - every dropped edge connects a change to a cell with NO relation to it,
    #     so evaluating that cell was a no-op that could not append anything;
    #   - survivors keep their original RELATIVE order, so the ring queue is a
    #     subsequence of the old one, not a reordering.
    # Together: same values, same tick counts. Verified, not assumed -- see the
    # tbl_diff and 1024-vector entries in LOG.md.
    #
    # Completeness rests on one claim: run_scalar touches a cell variable ONLY
    # through the tables enumerated here (plus a torch's attachment block).
    # Miss a relation and the affected cell keeps a stale value, which every
    # gate would show as a changed verdict -- diff_engine's 3-way agreement, the
    # 1024-vector alu4 verify, the 32-vector alu1 verify, the nonhier suite.
    # REDSTONE_WAKE_EXACT=0 restores the geometric map instantly if that is ever
    # in doubt; it costs ~nothing to keep the switch.
    if _os.environ.get("REDSTONE_WAKE_EXACT", "1") == "1":
        SH = 24                      # packs (target, reader) into one int
        pairs = set()
        bpairs = set()               # subset that only wants TRUTHINESS
        add = pairs.add
        addb = bpairs.add
        # ponytail: a boolean edge only needs waking when the value CROSSES
        # zero. A wire decaying 15->14->13 changes three times and crosses
        # once, so most boolean wakes are pure waste. Measured on alu4: 57.4%
        # of the exact edges are boolean-only, and only dust and comparator
        # outputs are multi-valued enough for a crossing to exist -- solids,
        # torches and repeaters are already 0/1, so every one of their changes
        # IS a crossing and they are never suppressed.
        def _e(t, r, level=False):
            if t >= 0:
                key = (t << SH) | r
                add(key)
                if not level and (kind[t] == 0 or kind[t] == 6):
                    addb(key)

        for i in range(nid):
            k = kind[i]
            if k == 0:               # dust READS these
                for m in d_dust[i]:
                    _e(m, i, True)
                for m in d_cup[i]:
                    _e(m, i, True)
                for m in d_cdn[i]:
                    _e(m, i, True)
                for m in d_comp[i]:
                    _e(m, i, True)
                for m in d_cob[i]:
                    _e(m, i)
                for m in d_torch[i]:
                    _e(m, i)
                for m in d_rep[i]:
                    _e(m, i)
                _e(d_bt[i], i)
                _e(d_bp[i], i)
            elif k == 1:             # a powered solid READS these
                for m in c_dust[i]:
                    _e(m, i)
                for m in c_torch[i]:
                    _e(m, i)
                for m in c_rep[i]:
                    _e(m, i)
                _e(c_up[i], i)
            elif k == 4:             # a repeater READS its one input + sides
                sp = r_src[i]
                if sp is not None and sp[0] != 2:
                    _e(sp[1], i)
                s0, s1 = r_side[i]
                if s0 is not None and s0[0] != 2:
                    _e(s0[1], i)
                if s1 is not None and s1[0] != 2:
                    _e(s1[1], i)
            elif k == 6:             # a comparator READS rear + two sides
                sp = k_rear[i]
                if sp is not None and sp[0] != 2:
                    _e(sp[1], i)
                s0, s1 = k_side[i]
                if s0 is not None and s0[0] != 2:
                    _e(s0[1], i)
                if s1 is not None and s1[0] != 2:
                    _e(s1[1], i)
            elif k == 2:             # a torch READS its attachment block
                _e(t_att[i], i)
        for j, i in lock_edges:     # repeater lock sides (already exact)
            add((j << SH) | i)
        if _os.environ.get("REDSTONE_WAKE_BOOL", "1") == "0":
            bpairs = set()
        for i in range(nid):
            w = wake[i]
            if w:
                # wake[i] is "cells to re-evaluate when cell i CHANGES", so i
                # is the TARGET and m is the READER. Getting this backwards
                # drops almost every edge and the engine settles in one tick
                # with nothing lit -- it is the whole ballgame.
                #
                # A boolean edge is stored NEGATED (~m) so the SAME list keeps
                # the SAME order whether or not the suppression is on: the ring
                # queue stays a subsequence of the geometric one, which is what
                # makes skipping them safe rather than merely fast.
                out = []
                for m in w:
                    key = (i << SH) | m
                    if key in pairs:
                        out.append(~m if key in bpairs else m)
                wake[i] = out

    return {"cell": cell, "cid": cid, "nid": nid, "kind": kind,
            "dust_ids": dust_ids, "pwr_ids": pwr_ids, "torch_ids": torch_ids,
            "rep_ids": rep_ids, "comp_ids": comp_ids,
            "d_bt": d_bt, "d_bp": d_bp, "d_torch": d_torch, "d_lev": d_lev,
            "d_rblk": d_rblk, "d_cob": d_cob, "d_dust": d_dust,
            "d_rep": d_rep, "d_comp": d_comp, "d_cup": d_cup, "d_cdn": d_cdn,
            "c_dust": c_dust, "c_rep": c_rep, "c_torch": c_torch,
            "c_lev": c_lev, "c_rblk": c_rblk, "c_up": c_up,
            "r_src": r_src, "r_side": r_side, "r_delay": r_delay,
            "k_rear": k_rear, "k_side": k_side, "k_mode": k_mode,
            "t_att": t_att, "t_dead": t_dead, "wake": wake,
            "l_arm": l_arm, "l_cob": l_cob, "l_torch": l_torch,
            "l_lev": l_lev, "l_rblk": l_rblk, "l_up": l_up,
            "ncells": len(dust) + len(pwr) + len(rep) + len(comp) + len(torch)}


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
    """Dust level at cell id `c`.

    ponytail: order of the tests is irrelevant and that is WHY this can be
    split per source class. Every fifteen-source returns 15 immediately, and 15
    is the maximum level, so whichever fires first the answer is 15; everything
    else accumulates a max. The old per-direction 5-tuple loop interleaved the
    two, which cost a tuple unpack and a code compare per direction per cell
    (173242 calls/vector) to express an order that cannot matter.
    """
    t = st["d_bt"][c]
    if t >= 0 and tl[t]:
        return 15
    p = st["d_bp"][c]
    if p >= 0 and pbs[p]:
        return 15
    if st["d_rblk"][c]:
        return 15
    # NOT DONE, and the reason is worth keeping: guarding each class with
    # `if v:` to skip the iterator setup for empty ones looks free and is not.
    # Measured by interleaved ratio it was 2.19x vs 2.14x -- i.e. a ~2% win,
    # inside the run-to-run spread, so it was left out for the simpler code.
    # The trap that nearly made me revert it the other way: comparing ABSOLUTE
    # times said 2.19s -> 2.50s, which looks like a 14% regression. Both
    # engines had drifted 20% slower between runs because the co-tenant agent
    # changed the machine's load. On this box only the interleaved ratio means
    # anything.
    for m in st["d_cob"][c]:
        if pbs[m]:
            return 15
    for m in st["d_torch"][c]:
        if tl[m]:
            return 15
    for m in st["d_rep"][c]:
        if ron[m]:
            return 15
    for nm in st["d_lev"][c]:
        if vec.get(nm, False):
            return 15
    lv = 0
    for m in st["d_dust"][c]:
        x = pw[m] - 1
        if x > lv:
            lv = x
    # ponytail: OR, do not override -- mirrors the sim.py comparator-front
    # fix. A dust cell in front of a comparator is driven by the comparator AND
    # by anything else adjacent (vanilla ORs every contribution to a cell). The
    # old early return discarded all other sources and read 0 whenever the
    # comparator was off, so sim and simvec had to be changed together or
    # diff_engine would diverge.
    for m in st["d_comp"][c]:
        x = con[m]
        if x > lv:
            lv = x
    for m in st["d_cup"][c]:
        x = pw[m] - 1
        if x > lv:
            lv = x
    for m in st["d_cdn"][c]:
        x = pw[m] - 1
        if x > lv:
            lv = x
    return lv


def _cob_state_s(c, st, pw, tl, ron, vec):
    # ponytail: strong sources first and return immediately. Every strong
    # source also sets weak power, so once one fires the answer is exactly
    # (True, True) and the remaining lists cannot change it. Only the
    # dust/up terms need a full scan.
    if st["c_rblk"][c]:
        return True, True
    # Left unguarded for the same measured reason as in _dust_lvl_s: the
    # `if v:` variant was ~2% by interleaved ratio, i.e. noise, so the simpler
    # form ships.
    for m in st["c_torch"][c]:
        if tl[m]:
            return True, True
    for m in st["c_rep"][c]:
        if ron[m]:
            return True, True
    for nm in st["c_lev"][c]:
        if vec.get(nm, False):
            return True, True
    pwrd = False
    for m in st["c_dust"][c]:
        if pw[m]:
            pwrd = True
    u = st["c_up"][c]
    if u >= 0 and pw[u]:
        pwrd = True
    return pwrd, False


def _lev_s(spec, pw, pbs, tl, ron, con, vec):
    """Level feeding one input. Spec is (int code, payload); see _tables_from."""
    if spec is None:
        return 0
    k = spec[0]
    if k == 1:
        return pw[spec[1]]
    if k == 2:
        return 15 if vec.get(spec[1], False) else 0
    if k == 3:
        return 15 if tl[spec[1]] else 0
    if k == 4:
        return 15                      # redstone block: always
    if k == 5:
        return 15 if ron[spec[1]] else 0
    if k == 6:
        return 15 if pbs[spec[1]] else 0
    if k == 7:
        return con[spec[1]]
    return 0


def _rep_on_s(c, st, pw, pb, tl, ron, con, vec):
    # ponytail: side-lock (mirrors sim.rep_val): a powered side holds
    # the last output instead of following the input. ron starts 0
    # here exactly as in sim (power-on locked stays off).
    s0, s1 = st["r_side"][c]
    if s0 is not None and _lev_s(s0, pw, pb, tl, ron, con, vec) >= 1:
        return bool(ron[c])
    if s1 is not None and _lev_s(s1, pw, pb, tl, ron, con, vec) >= 1:
        return bool(ron[c])
    s = st["r_src"][c]
    if s is None:
        return False
    k = s[0]
    if k == 1:
        return pw[s[1]] >= 1
    if k == 6:
        return bool(pb[s[1]])
    if k == 2:
        return bool(vec.get(s[1], False))
    if k == 3:
        return bool(tl[s[1]])
    if k == 4:
        return True
    if k == 5:
        return bool(ron[s[1]])
    if k == 7:
        return con[s[1]] >= 1
    return False


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
    dust, torch, rep, rblk, cob, repdelay, lever, lampnet, \
        attach_rev, comp, leveratt, glass, slab, target = ctx
    if target_hits:
        # A projectile hit is time-dependent; the fixed tables only model the
        # target's idle opaque-conductive role. Validate first, then let the
        # caller fall back to sim._run_vec rather than freeze a transient.
        from sim import _target_shots
        _target_shots(target_hits, target)
        raise NotImplementedError(
            "run_scalar: no timed target hits; use sim._run_vec")
    st = _tables(ctx)
    cell = st["cell"]
    kind = st["kind"]
    nid = st["nid"]
    dust_ids = st["dust_ids"]
    torch_ids = st["torch_ids"]
    rep_ids = st["rep_ids"]
    comp_ids = st["comp_ids"]
    # ponytail: state is six bytearrays indexed by cell id. Levels are 0..15
    # and the flags are 0/1, so a bytearray is not a compromise here, it is the
    # natural type -- and reading one is a bounds-checked index returning an
    # interned small int, where the old code hashed a 3-tuple per lookup
    # (1244222 dict.get calls per vector).
    pw = bytearray(nid)
    pb = bytearray(nid)
    pbs = bytearray(nid)
    tl = bytearray(nid)
    ron = bytearray(nid)
    con = bytearray(nid)
    tsched = bytearray(nid)
    rsched = bytearray(nid)
    ksched = bytearray(nid)
    flips = [0] * nid
    wake = st["wake"]
    bout = {}
    d_bt = st["d_bt"]
    d_bp = st["d_bp"]
    d_torch = st["d_torch"]
    d_lev = st["d_lev"]
    d_rblk = st["d_rblk"]
    d_cob = st["d_cob"]
    d_dust = st["d_dust"]
    d_rep = st["d_rep"]
    d_comp = st["d_comp"]
    d_cup = st["d_cup"]
    d_cdn = st["d_cdn"]
    c_dust = st["c_dust"]
    c_rep = st["c_rep"]
    c_torch = st["c_torch"]
    c_lev = st["c_lev"]
    c_rblk = st["c_rblk"]
    c_up = st["c_up"]
    r_src = st["r_src"]
    r_side = st["r_side"]
    r_delay = st["r_delay"]
    t_att = st["t_att"]
    t_dead = st["t_dead"]

    # ponytail: a ring item is ONE int. Non-negative means "re-evaluate this
    # cell"; NEGATIVE means "this cell's scheduled tick is firing", decoded as
    # `~item`. The packing is not a micro-optimisation, it is a correctness
    # requirement found by diffing the two engines' event logs: a repeater with
    # delay 0 schedules its fire into the CURRENT bucket while its own
    # re-evaluation is already queued EARLIER in that same bucket, so both items
    # are legitimately pending at once and they mean different things. A tuple
    # (kind, cell) said which; a single per-cell flag could not, because both
    # items share the cell -- the rewrite ran the FIRE branch for the eval item,
    # repeaters came on one tick early, and every vector settled a tick sooner
    # with the same final state.
    #
    # Why negative and not `(id << 1) | firing`: wake appends are the hot path
    # (268293 per vector) and `id << 1` allocates a fresh int every time.
    # Sign encoding leaves the common case a plain reference to an int that
    # already exists in the table, so appending allocates nothing; only the
    # rare fire events (a few thousand per vector) pay for `~c`. Ids are >= 0,
    # so the two can never collide.
    RING = 5
    buckets = [[] for _ in range(RING)]
    b0 = buckets[0]
    b0.extend(dust_ids)
    b0.extend(st["pwr_ids"])
    b0.extend(torch_ids)
    b0.extend(rep_ids)
    b0.extend(comp_ids)
    alive = len(b0)
    # ponytail: one coalescing marker per ring slot, REUSED across ticks.
    # A fresh set() per bucket cost 268293 set-adds plus 268293 hashed
    # 3-tuple-ish lookups per vector; a bytearray index is a direct byte test.
    # The mark is cleared when a cell is POPPED, which is exactly the old
    # hset semantics (queued for this tick and not yet evaluated), so a cell
    # evaluated earlier in the tick is re-queueable again -- and since every
    # appended item is popped in the SAME tick, the slot is clean by the time
    # the ring comes back around to it.
    qmark = [bytearray(nid) for _ in range(RING)]
    now = steps = last_change = 0
    max_gap = 0
    stall_cap = max(stall, 3 * st["ncells"])

    while alive:
        if now > tick_cap or steps > step_cap:
            churn = sorted((j for j in range(nid) if flips[j] >= 3),
                           key=lambda j: (-flips[j], str(cell[j])))
            tloop = sorted(cell[j] for j in churn if cell[j] in torch)
            cset = set(cell[j] for j in churn)
            same = slope = 0
            # ponytail: `churn` holds integer IDS, not cells. This loop used to
            # walk `churn` and then subscript it as a cell, so reaching this
            # branch raised `TypeError: 'int' object is not subscriptable`
            # instead of the "sim not settling" report it exists to write --
            # which is precisely how a not-settling build gets misread as a
            # router fault (see the _TICK_CAP note at the top of sim.py). Every
            # neighbouring line (799, 800, 812) indexes correctly via `j`; only
            # this one did not. Iterate the CELLS. No verdict can change: this
            # is the error path for a build that already failed.
            for c in cset:
                for dx, dz in DIRS:
                    if (c[0] + dx, c[1], c[2] + dz) in cset:
                        same += 1
                    if (c[0] + dx, c[1] + 1, c[2] + dz) in cset:
                        slope += 1
            raise RuntimeError(
                f"sim not settling on {vec}. churn={len(churn)} "
                f"edges: same-level={same} slope={slope} "
                f"loop_torches: {tloop[:6]} max_gap={max_gap} "
                f"top: {[(cell[j], pw[j], flips[j]) for j in churn[:6]]}")
        i = now % RING
        items = buckets[i]
        if not items:
            if want is not None and now in want:
                want[now] = {cell[j]: pw[j] for j in dust_ids if pw[j]}
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
        # reads the LATEST state when it finally runs. `qc` holds exactly the
        # items already queued for THIS tick and not yet evaluated, so dropping
        # a duplicate is free; a cell that has already been evaluated this tick
        # has had its mark cleared and gets re-queued normally. Insertion order
        # is preserved (first occurrence wins), so the event sequence the
        # physics sees is unchanged -- this removes work, not information. It
        # is a bytearray per ring slot, not a set, so the membership test is a
        # byte load instead of a hash-table probe.
        here = buckets[i]
        qc = qmark[i]
        for it in items:
            if it >= 0:
                c = it
                f = 0
            else:
                c = ~it
                f = 1
            qc[c] = 0
            steps += 1
            if steps - last_change > stall_cap:
                raise RuntimeError(
                    f"sim STALLED on {vec}: no value change for "
                    f"{steps - last_change} steps at tick {now} "
                    f"({steps} steps run) - wedged, not oscillating")
            k = kind[c]
            if k == 0:                       # dust
                v = _dust_lvl_s(c, st, pw, pbs, tl, ron, con, vec)
                if pw[c] != v:
                    # ponytail: a boolean edge only needs waking if this
                    # change CROSSED zero. A wire decaying 15->14->13 wakes
                    # nothing boolean until the 1->0 at the end, which is the
                    # whole point: 57.4% of edges are boolean-only and most
                    # changes are not crossings. Level edges (adjacent dust,
                    # cup/cdn slopes, comparator outputs) are always walked.
                    old = pw[c]
                    pw[c] = v
                    crossing = (old != 0) != (v != 0)
                    flips[c] += 1
                    g = steps - last_change
                    if g > max_gap:
                        max_gap = g
                    last_change = steps
                    for c2 in wake[c]:
                        if c2 < 0:
                            if not crossing:
                                continue
                            c2 = ~c2
                        if not qc[c2]:
                            qc[c2] = 1
                            here.append(c2)
                            alive += 1
            elif k == 1:                     # cobble / powerable solid
                pwrd, strong = _cob_state_s(c, st, pw, tl, ron, vec)
                if pb[c] != pwrd or pbs[c] != strong:
                    pb[c] = pwrd
                    pbs[c] = strong
                    flips[c] += 1
                    g = steps - last_change
                    if g > max_gap:
                        max_gap = g
                    last_change = steps
                    for c2 in wake[c]:
                        if not qc[c2]:
                            qc[c2] = 1
                            here.append(c2)
                            alive += 1
            elif k == 2:                     # torch: re-evaluate, or fire
                if f:
                    tsched[c] = 0
                    a = t_att[c]
                    v = not (pb[a] if a >= 0 else False)
                    if tl[c] != v:
                        if tl[c] and not v:
                            bt = tuple(t for t in bout.get(c, ())
                                       if now - t < 30) + (now,)
                            bout[c] = bt
                            if len(bt) > max(_BOUT.get(cell[c], 0), 0):
                                _BOUT[cell[c]] = len(bt)
                            if len(bt) > _BOUT_N and now >= _BOUT_GRACE:
                                tl[c] = 0
                                raise RuntimeError(
                                    f"TORCH BURNOUT at {cell[c]} (shipping red)")
                        tl[c] = v
                        flips[c] += 1
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        for c2 in wake[c]:
                            if not qc[c2]:
                                qc[c2] = 1
                                here.append(c2)
                                alive += 1
                else:
                    if tsched[c] or t_dead[c]:
                        continue
                    a = t_att[c]
                    if (not (pb[a] if a >= 0 else False)) != tl[c]:
                        tsched[c] = 1
                        buckets[(now + 1) % RING].append(~c)
                        alive += 1
            elif k == 4:                     # repeater: re-evaluate, or fire
                if f:
                    rsched[c] = 0
                    v = _rep_on_s(c, st, pw, pb, tl, ron, con, vec)
                    if ron[c] != v:
                        ron[c] = v
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        for c2 in wake[c]:
                            if not qc[c2]:
                                qc[c2] = 1
                                here.append(c2)
                                alive += 1
                else:
                    if rsched[c]:
                        continue
                    if _rep_on_s(c, st, pw, pb, tl, ron, con, vec) != ron[c]:
                        rsched[c] = 1
                        buckets[(now + r_delay[c]) % RING].append(~c)
                        alive += 1
            else:                            # comparator: re-evaluate, or fire
                if f:
                    ksched[c] = 0
                    v = _comp_out_s(c, st, pw, pbs, tl, ron, con, vec)
                    if con[c] != v:
                        # a comparator output is multi-valued (0..15), so it
                        # gets the same crossing rule as dust
                        old = con[c]
                        con[c] = v
                        crossing = (old != 0) != (v != 0)
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        for c2 in wake[c]:
                            if c2 < 0:
                                if not crossing:
                                    continue
                                c2 = ~c2
                            if not qc[c2]:
                                qc[c2] = 1
                                here.append(c2)
                                alive += 1
                else:
                    if ksched[c]:
                        continue
                    if _comp_out_s(c, st, pw, pbs, tl, ron, con, vec) != con[c]:
                        ksched[c] = 1
                        buckets[(now + 1) % RING].append(~c)
                        alive += 1

    lamps = {}
    l_arm = st["l_arm"]
    l_cob = st["l_cob"]
    l_torch = st["l_torch"]
    l_lev = st["l_lev"]
    l_rblk = st["l_rblk"]
    l_up = st["l_up"]
    for lc, net in lampnet.items():
        i = st["cid"][lc]
        lit = False
        for a in l_arm[i]:
            if pw[a]:
                lit = True
        if not lit and l_up[i] >= 0 and pw[l_up[i]]:
            lit = True
        if not lit:
            for b in l_cob[i]:
                if pb[b]:
                    lit = True
        if not lit:
            for t in l_torch[i]:
                if tl[t]:
                    lit = True
        if not lit and l_rblk[i]:
            lit = True
        if not lit:
            for nm in l_lev[i]:
                if vec.get(nm, False):
                    lit = True
        lamps[net] = lit
    if want:
        # any stop the run never reached (it settled first) shows the final
        # state, which is what it would have shown anyway
        final = {cell[j]: pw[j] for j in dust_ids if pw[j]}
        for t in list(want):
            if want[t] is None:
                want[t] = dict(final)
    return (lamps,
            {cell[j]: pw[j] for j in dust_ids if pw[j]},
            {cell[j]: 1 if tl[j] else 0 for j in torch_ids},
            now,
            {cell[j]: 1 if ron[j] else 0 for j in rep_ids},
            {cell[j]: con[j] for j in comp_ids})


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
    # ponytail: drop the parsed-tables cache with the inputs. _CTX keys on
    # nothing; without this, two verify_par calls in one process (compose
    # check runs four builds back to back) would simulate builds 2-4 with
    # build 1's tables -- a wrong-build green. One parse per worker per
    # verify, shared by all its shards.
    global _CTX
    _CTX = None


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
    # ponytail: parse once per worker, not per shard. _serial_shard
    # re-parsed the whole build for every shard it ran (a 16-worker pool
    # over 64 shards parsed 64x instead of 16x); the tables are a pure
    # function of (blocks, io), so the _parse_build_ctx cache is exact.
    # Saves (shards - workers) parses per verify -- seconds on big builds.
    P = _parse_build_ctx()
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
    _P0 = _sv_parse(blocks, io)
    _sv_check(_P0)
    # ponytail: serial fast path for small sweeps. A spawn pool costs
    # real wall before the first vector runs (process spawn, module
    # re-import, full build unpickle per worker); a tiny sweep never
    # amortizes it (measured: 4 vectors on a 144-block build took 0.26s
    # pooled vs 0.01s serial in-process, same box -- 26x). Threshold is
    # deliberately tight (<=8 vectors AND <=100k cell-vectors): small
    # fields converge in ticks, so serial cost is provably ~1s, while a
    # slow-vector build must still fan out no matter how few vectors it
    # has. Same _serial_shard the pool runs (latch fallback + fail-fast
    # intact), just without the pool. REDSTONE_SERIAL_CELLVEC=0 forces
    # the pool (A/B + escape); a plain count in it replaces both caps.
    _ser_cv = int(_os.environ.get("REDSTONE_SERIAL_CELLVEC", "100000"))
    if _ser_cv and len(combos) <= 8 \
            and len(combos) * len(_P0[0]) <= _ser_cv:
        _init_worker(blocks, io, gates, outputs, ins, tick_cap, stall)
        _W["stop"] = None
        _sbad, _sticks, _sfatal = _serial_shard(combos)
        if _sfatal and not _sfatal.startswith("aborted"):
            raise RuntimeError(_sfatal)
        return _sbad, _sticks
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
