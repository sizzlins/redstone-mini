"""Simulation: redstone physics verifier plus generate-and-test retry."""

import heapq
import os as _os
import time as _time

import snapshot
from core import DIRS, base
from layout import layout, dust_points
from compose import compose
from recipe import eval_gate, eval_net

# ponytail: settling budget. A dense build is ~10x the cells of a small one and
# legitimately needs more ticks (a 40-cell boosted run alone costs 40), so the
# old fixed 500 ticks / 20000 steps expired mid-convergence and got reported as
# "sim not settling" — which reads as a router fault and is not one. Measured:
# micro1 converges at 5000/300000 in 0.4s; the 34k-block hier alu4 needs
# 20000 ticks for its slowest vectors (they RED at 5000 as "not settling"
# then settle in 1s at 20000 — slow convergence, no loop: empty loop list,
# huge max_gap). Ceilings only: greens settle long before them either way, and
# true oscillators never settle at any cap, so verdicts only gain true greens.
_TICK_CAP = int(_os.environ.get("REDSTONE_SIM_TICKS", "20000"))
_STEP_CAP = int(_os.environ.get("REDSTONE_SIM_STEPS", "2000000"))
# ponytail: stall window. Progress, not a bigger constant: stale queued events
# drain for hundreds of steps (measured max_gap 444-662 on a real oscillator),
# so "no value change for N steps" is a real, separate failure from "still
# converging" and from "oscillating forever". A stall now reports as a stall
# instead of masquerading as an oscillator, and fails fast.
_STALL = int(_os.environ.get("REDSTONE_SIM_STALL", "5000"))
# ponytail: whole-attempt wall clock, RB `budget.rs:20 BudgetGuard::new/check`
# translated to the one resource that is actually scarce here. RSS is not (a
# Python router's memory tracks its own allocations and nothing in the record
# shows an OOM), but wall time is: cpu4 is 402s/seed, so the default ladder is
# 12 tries x 3 grows = hours to learn nothing. 0 = off. Fails LOUD, because a
# silently shortened ladder reads as "verified".
# ceiling: checked at the SEED boundary only, so one seed always runs to
# completion -- grows layouts -- and a tries=1 call is never bounded at all.
# upgrade: layout() already polls a search cap mid-search; thread the same
# deadline through it and the guard becomes per-A*-call.
# trigger: revisit when one seed overruns the budget by more than the budget
# (measured: 80.6s for two cpu4 seeds at grow=0, cap 700).
_MAX_SECS = float(_os.environ.get("REDSTONE_MAX_SECS", "0") or 0)
_BOUT_N = int(_os.environ.get("REDSTONE_BURNOUT", "8"))
_BOUT = {}


def layout_retry(recipe, tries=12, verify=False, grows=3):
    """Randomized-restart maze routing: reshuffle net order until the field fits.
    Returns the FIRST verified build. ponytail: this used to sweep all `tries`
    at a grow and ship the cheapest by (ticks, blocks) -- on micro1 that spent
    48s AFTER the first green to find a candidate that was worse (ticks 45 vs
    42), and on a recipe that never goes green it is 12x the cost for nothing.
    Grows are interleaved per seed, not swept one field-size at a time: a field
    too small to fit ALWAYS fails, so exhausting all 12 seeds at grow=0 before
    trying grow=1 is 70s of guaranteed waste (measured, micro1: 0/12 at grow=0,
    2/12 at grow=1). Diversifying the field size first is both faster and
    cheaper. Cost of dropping best-of: a small build may come out a few blocks
    larger; a few ms either way, and the sim still gates correctness.
    Tap reservation runs only as a second round after a lamp-spot failure:
    always-on rings moved small builds into a slope short (measured twice),
    so green trajectories never see it."""
    eval_gate(recipe)  # reject a bad recipe in us, not after the router's budget
    t0, log = _time.monotonic(), []

    def tried(backend, seed, grow, res, err):
        # full message, not truncated: a SIM MISMATCH ends with the whole live
        # map, which IS the record (s7/s10 Q is 16/126 cells lit). Capping it
        # would keep the headline and drop the only part worth having.
        log.append({"backend": backend, "seed": seed, "grow": grow, "reserve": res,
                    "secs": round(_time.monotonic() - t0, 2), "error": str(err)})

    def done(out):
        snapshot.write(recipe, out[0], out[2], out[3],
                       {"status": "ok", "verify": verify, "attempts": log})
        return out

    last = None
    # ponytail: sim-gate the compose ladder when verifying (see
    # REDSTONE_SIM_GATE in compose()). Saved/restored so previews and probes
    # keep the fast ungated path; only layout_retry(verify=True) opts in.
    _sg = _os.environ.get("REDSTONE_SIM_GATE")
    if verify:
        _os.environ["REDSTONE_SIM_GATE"] = "1"
    try:
        try:
            out = compose(recipe)
        except RuntimeError as e:
            last = e
            tried("compose", None, 0, False, e)
        else:
            if not verify:
                return done(out + (None,))
            try:
                st, ticks = sim_verify(recipe, out[0], out[2], quiet=True, collect=True)
            except RuntimeError as e:
                e.blocks, e.size, e.io = out[:3]
                last = e
                tried("compose", None, 0, False, e)
            else:
                return done(out + (st,))
    finally:
        if _sg is None:
            _os.environ.pop("REDSTONE_SIM_GATE", None)
        else:
            _os.environ["REDSTONE_SIM_GATE"] = _sg
    for _res in (False, True):
        for t in range(tries):
            if _MAX_SECS and _time.monotonic() - t0 > _MAX_SECS:
                e = RuntimeError(
                    f"BUDGET: layout_retry hit REDSTONE_MAX_SECS={_MAX_SECS:g}s "
                    f"after {len(log)} attempts; last error: {last}")
                snapshot.write(recipe, getattr(last, "blocks", None),
                               getattr(last, "io", None), None,
                               {"status": "budget", "verify": verify,
                                "attempts": log, "error": str(e)})
                raise e
            seed = None if t == 0 else t
            for grow in range(grows or 1):
                try:
                    out = layout(recipe, seed=seed, grow=grow, reserve=_res)
                except RuntimeError as e:
                    last = e
                    tried("maze", seed, grow, _res, e)
                    continue
                if not verify:
                    return done(out + (None,))
                try:
                    st, ticks = sim_verify(recipe, out[0], out[2], quiet=True,
                                           collect=True)
                except RuntimeError as e:
                    e.blocks, e.size, e.io = out[:3]
                    last = e
                    tried("maze", seed, grow, _res, e)
                    continue
                return done(out + (st,))
        if not _res and last is not None and "lamp spot taken" in str(last):
            continue  # one reserve round, same tries x grows
        break
    snapshot.write(recipe, getattr(last, "blocks", None), getattr(last, "io", None),
                   None, {"status": "failed", "verify": verify, "attempts": log,
                          "error": str(last)})
    raise last



def _run_vec(vec, init, ctx, until=None):
    """Tick-settled physics for one input vector (shared by verify/sequence).
    init carries live/torch/repeater state across phases (memory!); None
    starts blank. until caps the run at a tick (for sim_pulse timelines).
    Returns (lamps, live, torches, ticks, repeaters)."""
    dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, attach_rev, comp = ctx
    # tick-accurate vanilla timing: dust/cobble settle instantly each tick,
    # torch outputs flip 1 tick after their block changes, repeaters flip
    # after their delay=1..4 stage. Levels still drain phantom latches.
    import heapq as _hq
    pw, pb, pbs = {}, {}, {}
    tl = {c: False for c in torch}
    ron = {c: False for c in rep}
    con = {c: 0 for c in comp}
    if init:
        for c, v in init.get("w", {}).items():
            if v:
                pw[c] = v
        for c, v in init.get("t", {}).items():
            tl[c] = bool(v)
        for c, v in init.get("r", {}).items():
            ron[c] = bool(v)
        for c, v in init.get("o", {}).items():
            con[c] = v
    pending, tsched, rsched, ksched, seq, ticks, steps = [], set(), set(), set(), [0], [0], [0]
    last_change, max_gap = [0], [0]

    def mark():
        g = steps[0] - last_change[0]
        if g > max_gap[0]:
            max_gap[0] = g
        last_change[0] = steps[0]

    flips = {}  # cell -> value changes; the churn set is the oscillator core
    _bout = {}  # torch -> recent flip ticks; burnout bookkeeping (vanilla)
    _trace = []  # REDSTONE_TRACE=1: first flips per kind (ignition sequence)
    _traced = [0]

    def sched(tick, kind, cell):
        seq[0] += 1
        _hq.heappush(pending, (tick, seq[0], kind, cell))

    def wake(now, c):
        # cell c changed output at tick now: re-eval everything it feeds.
        for dx, dz in DIRS:
            m = (c[0] + dx, c[1], c[2] + dz)
            if m in dust:
                sched(now, "d", m)
            elif m in cob:
                sched(now, "c", m)
            elif m in rep:
                d = rep[m]
                if (m[0] - d[0], m[1], m[2] - d[1]) == c:
                    sched(now, "r", m)
            elif m in comp:
                sched(now, "k", m)
        for vx, vy, vz in ((c[0], c[1] + 1, c[2]), (c[0], c[1] - 1, c[2])):
            if (vx, vy, vz) in dust:
                sched(now, "d", (vx, vy, vz))
            elif (vx, vy, vz) in cob:
                sched(now, "c", (vx, vy, vz))
        for dx, dz in DIRS:
            for vx, vy, vz in ((c[0] + dx, c[1] + 1, c[2] + dz), (c[0] + dx, c[1] - 1, c[2] + dz)):
                if (vx, vy, vz) in dust:
                    sched(now, "d", (vx, vy, vz))
        for t in attach_rev.get(c, []):
            sched(now, "t", t)

    def dust_lvl(c):
        lv = 0
        # ponytail: dust directly ABOVE a lit torch reads 15 (wiki; the code
        # comment at the standing-torch parser admitted this gap and asked
        # for it gated on a canary — the canary is below in __main__).
        # Never exercised by our tiles (nothing stacks on a torch) so zero
        # behavior change for every green build; verified by the fleet gate.
        _below = (c[0], c[1] - 1, c[2])
        if _below in torch and tl.get(_below, False):
            return 15
        # ponytail: dust on top of a strongly powered block reads 15 (wiki:
        # strong power covers dust on top and beneath, not just beside).
        # Same class as the torch-below term: support power the old model
        # could see (cob_state) but dust never read.
        if _below in cob and pbs.get(_below, False):
            return 15
        for dx, dz in DIRS:
            m = (c[0] + dx, c[1], c[2] + dz)
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
                if (m[0] + d[0], m[1], m[2] + d[1]) == c and ron.get(m, False):
                    return 15
            if m in comp:
                md = comp[m]
                if (m[0] - md["rear"][0], m[1], m[2] - md["rear"][1]) == c:
                    return con.get(m, 0)
            # ponytail: chip layers. Dust links ±1 level iff the upper dust
            # sits on a conductive block and no lid covers the lower wire.
            # Direct stacks never link (no support, no link).
            up = (c[0] + dx, c[1] + 1, c[2] + dz)
            if up in dust and (c[0] + dx, c[1], c[2] + dz) in cob \
                    and (c[0], c[1] + 1, c[2]) not in cob:
                lv = max(lv, pw.get(up, 0) - 1)
            dn = (c[0] + dx, c[1] - 1, c[2] + dz)
            if dn in dust and (c[0], c[1] - 1, c[2]) in cob \
                    and (c[0] + dx, c[1], c[2] + dz) not in cob:
                lv = max(lv, pw.get(dn, 0) - 1)
        return max(lv, 0)

    def cob_state(c):
        pwrd, strong = False, False
        for dx, dz in DIRS:
            m = (c[0] + dx, c[1], c[2] + dz)
            # ponytail: dust powers a side block only when POINTING at it
            # (dust_points, the one shared table) — a wire merely running past
            # does not. Dust on top still counts (below), no shape condition.
            # Direction is dust->block (negated neighbour offset); the old
            # sign mirrored corner/T sensing (symmetric shapes can't tell).
            if m in dust and pw.get(m, 0) >= 1 and (-dx, -dz) in dust_points(m, dust):
                pwrd = True
            if m in rblk:
                pwrd, strong = True, True
            # ponytail: a LEVER powers the block it is attached to (wiki:
            # levers and buttons strongly power their host). This was a model
            # gap, not a layout choice: every other strong source above is
            # here, levers were not, so a cobble under a wall lever read
            # dark and dust on top of it stayed unlit. It is the one
            # direction-agnostic, ZERO-WIRE source available: the dust is on
            # top of the pedestal, the lever is on its side, so the run that
            # feeds it can arrive from any direction without touching the
            # lever cell. Used for hier boundary stubs, where a lane-crossing
            # route is otherwise unroutable.
            # ponytail: REDSTONE_LEVER_POWER=0 restores the old gap (levers
            # never power their host) for differential diagnosis only: same
            # field, term on/off, diff the settled maps to name exactly which
            # cells the term lights. The term itself is wiki-correct (levers
            # strongly power a full-solid-opaque host); the knob exists to
            # attribute failures, not to ship old physics.
            if (m in lever and vec.get(lever[m], False)
                    and _os.environ.get("REDSTONE_LEVER_POWER", "1") == "1"):
                pwrd, strong = True, True
            # ponytail: a lit torch powers adjacent blocks — except the one
            # it is attached to (wiki; the same host exception the torch rule
            # itself uses, via torch[m] != c). Without this, dust sitting on
            # cobble whose only power is a neighboring torch reads lit (dust
            # above torch, done above) while its support reads dark — a split
            # model of one vanilla fact. Canary below in __main__.
            if m in torch and tl.get(m, False) and torch[m] != c:
                pwrd, strong = True, True
            if m in rep:
                d = rep[m]
                if (m[0] + d[0], m[1], m[2] + d[1]) == c and ron.get(m, False):
                    pwrd, strong = True, True
        up = (c[0], c[1] + 1, c[2])
        if up in dust and pw.get(up, 0) >= 1:
            pwrd = True
        return pwrd, strong

    def rep_on(c):
        d = rep[c]
        b = (c[0] - d[0], c[1], c[2] - d[1])
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
            if (b[0] + d2[0], b[1], b[2] + d2[1]) == c and ron.get(b, False):
                return True
        if b in comp:
            bd = comp[b]
            if (b[0] - bd["rear"][0], b[1], b[2] - bd["rear"][1]) == c and con.get(b, 0) >= 1:
                return True
        return False

    def comp_in(c):
        d = comp[c]
        rx, rz = d["rear"]
        rear = (c[0] + rx, c[1], c[2] + rz)
        if rear in dust:
            rl = pw.get(rear, 0)
        elif rear in lever and vec.get(lever[rear], False):
            rl = 15
        elif rear in rblk:
            rl = 15
        elif rear in torch and tl.get(rear, False):
            rl = 15
        elif rear in rep:
            rd = rep[rear]
            rl = 15 if (ron.get(rear, False) and (rear[0] + rd[0], rear[1], rear[2] + rd[1]) == c) else 0
        elif rear in comp:
            rd = comp[rear]
            rl = con.get(rear, 0) if (rear[0] - rd["rear"][0], rear[1], rear[2] - rd["rear"][1]) == c else 0
        else:
            rl = 0
        sl = 0
        for sx, sz in ((rz, rx), (-rz, -rx)):
            s = (c[0] + sx, c[1], c[2] + sz)
            if s in lever and vec.get(lever[s], False):
                sl = max(sl, 15)
            elif s in rblk:
                sl = max(sl, 15)
            elif s in rep:
                rd = rep[s]
                if ron.get(s, False) and (s[0] + rd[0], s[1], s[2] + rd[1]) == c:
                    sl = max(sl, 15)
            elif s in comp:
                sd = comp[s]
                if (s[0] - sd["rear"][0], s[1], s[2] - sd["rear"][1]) == c:
                    sl = max(sl, con.get(s, 0))
            elif s in dust and pw.get(s, 0) >= 1:
                sl = max(sl, pw.get(s, 0))
            elif s in cob and pbs.get(s, False):
                sl = max(sl, 15)
        return rl, sl

    def comp_out(c):
        rl, sl = comp_in(c)
        if comp[c]["mode"] == "subtract":
            return max(rl - sl, 0)
        return rl if sl <= rl else 0

    for c in dust:
        sched(0, "d", c)
    for c in cob:
        sched(0, "c", c)
    for c in torch:
        sched(0, "t", c)
    for c in rep:
        sched(0, "r", c)
    for c in comp:
        sched(0, "k", c)

    while pending and (until is None or pending[0][0] <= until):
        now, _, kind, c = _hq.heappop(pending)
        steps[0] += 1
        # ponytail: the stall cap scales with build size. It used to be a
        # flat 5000, which a 7000-block build trips during normal tick-0
        # startup (every cell evaluates once = 7000 steps with no change
        # yet). A wedged run processes cells over and over, so 3x the cell
        # count still catches it fast while letting big builds start up.
        _stall_cap = max(_STALL, 3 * (len(dust) + len(cob) + len(torch)
                                     + len(rep) + len(comp)))
        if steps[0] - last_change[0] > _stall_cap:
            raise RuntimeError(
                f"sim STALLED on {vec}: no value change for "
                f"{steps[0] - last_change[0]} steps at tick {now} "
                f"({steps[0]} steps run) — wedged, not oscillating")
        if now > _TICK_CAP or steps[0] > _STEP_CAP:
            # ponytail: name the OSCILLATOR, not the leftovers. `live` is
            # whatever happened to be lit at timeout — on a ring oscillator
            # that is an ordinary powered run (a monotone decay gradient),
            # which names nothing. `churn` is the cells that kept changing
            # after everything else settled, i.e. the loop's own members.
            live = {x: v for x, v in pw.items() if v}
            churn = sorted((c for c, k in flips.items() if k >= 3),
                           key=lambda c: (-flips[c], str(c)))
            if _os.environ.get("REDSTONE_CHURN"):
                # Full churn set for offline tracing. The message above only
                # carries the top few; a feedback edge cannot be named from a
                # sample. Keyed "x,y,z" so the file round-trips as JSON.
                import json as _json
                _ck = lambda c: f"{c[0]},{c[1]},{c[2]}"
                _json.dump({"vec": {str(k): bool(v) for k, v in vec.items()},
                            "steps": steps[0], "max_gap": max_gap[0],
                            "churn": {_ck(c): flips[c] for c in churn},
                            "live": {_ck(c): v for c, v in live.items()}},
                           open(_os.environ["REDSTONE_CHURN"], "w"))
            tloop = sorted(c for c in churn if c in torch)
            # The class question: a loop closed only by same-level edges is a
            # router topology fault; one that needs a y+-1 edge is riding the
            # chip/slope coupling rule. Count both, and the level histogram.
            cset = set(churn)
            lv = {}
            same = slope = 0
            for c in churn:
                lv[c[1]] = lv.get(c[1], 0) + 1
                for dx, dz in DIRS:
                    if (c[0] + dx, c[1], c[2] + dz) in cset:
                        same += 1
                    if (c[0] + dx, c[1] + 1, c[2] + dz) in cset:
                        slope += 1
            raise RuntimeError(
                f"sim not settling on {vec}. churn={len(churn)} levels={lv} "
                f"edges: same-level={same} slope={slope} "
                f"loop_torches: {tloop[:6]} max_gap={max_gap[0]} "
                f"top: {[(c, pw.get(c, 0), flips[c]) for c in churn[:6]]}")
        ticks[0] = max(ticks[0], now)
        if kind == "d":
            v = dust_lvl(c)
            if pw.get(c, 0) != v:
                pw[c] = v
                flips[c] = flips.get(c, 0) + 1
                if _os.environ.get("REDSTONE_TRACE") and _traced[0] < 400:
                    _traced[0] += 1
                    _trace.append((now, "d", c, v))
                mark(); wake(now, c)
        elif kind == "c":
            v, s = cob_state(c)
            if pb.get(c, False) != v or pbs.get(c, False) != s:
                pb[c], pbs[c] = v, s
                # ponytail: blocks count as churn too. A torch's attach block
                # IS a cobble, so without this the loop's block members were
                # structurally invisible to the churn set — the indicator could
                # not contain a real cycle, let alone name its edge.
                flips[c] = flips.get(c, 0) + 1
                mark(); wake(now, c)
        elif kind == "t":
            if (not pb.get(torch[c], False)) != tl.get(c, False) and c not in tsched:
                tsched.add(c)
                sched(now + 1, "T", c)
        elif kind == "T":
            tsched.discard(c)
            # a redstone block is permanently powered but is not a cobble, so
            # it never gets a `pb` entry -- without this a torch standing on one
            # reads its support as dark and stays lit (vanilla: it is off).
            v = not (pb.get(torch[c], False) or torch[c] in rblk)
            if tl.get(c, False) != v:
                # ponytail: vanilla burnout — a torch forced OFF more than
                # eight times in 60 game ticks (= 30 sim ticks: delay-4 settles
                # at tick 4, so 1 sim tick is 1 redstone tick) dies dark. OFF
                # transitions only: a healthy settle flips a few times total,
                # hunts alternate forever. Shipping gate fails loud, not hangs.
                if tl.get(c, False) and not v:
                    _bt = tuple(t for t in _bout.get(c, ()) if now - t < 30) + (now,)
                    _bout[c] = _bt
                    if len(_bt) > max(_BOUT.get(c, 0), 0):
                        _BOUT[c] = len(_bt)
                    if len(_bt) > _BOUT_N:
                        tl[c] = False
                        if _os.environ.get("REDSTONE_TRACE"):
                            import json as _json
                            _json.dump(
                                [(t, k, f"{cc[0]},{cc[1]},{cc[2]}", vv)
                                 for t, k, cc, vv in _trace],
                                open(_os.environ["REDSTONE_TRACE"], "w"))
                        raise RuntimeError(f"TORCH BURNOUT at {c} (shipping red)")
                tl[c] = v
                flips[c] = flips.get(c, 0) + 1
                if _os.environ.get("REDSTONE_TRACE") and _traced[0] < 400:
                    _traced[0] += 1
                    _trace.append((now, "T", c, v))
                mark(); wake(now, c)
        elif kind == "r":
            if rep_on(c) != ron.get(c, False) and c not in rsched:
                rsched.add(c)
                sched(now + repdelay.get(c, 1), "R", c)
        elif kind == "R":
            rsched.discard(c)
            v = rep_on(c)
            if ron.get(c, False) != v:
                ron[c] = v
                mark(); wake(now, c)
        elif kind == "k":
            if comp_out(c) != con.get(c, 0) and c not in ksched:
                ksched.add(c)
                sched(now + 1, "K", c)
        elif kind == "K":
            ksched.discard(c)
            v = comp_out(c)
            if con.get(c, 0) != v:
                con[c] = v
                mark(); wake(now, c)
    def _lit(cell):
        # ponytail: lamps need pointing-at dust (vanilla arms). End-of-line
        # dust aims at the lamp beyond its tip; a straight run passing
        # sideways does not light a side lamp. Isolated dust counts (cross
        # assumed; layouts never stamp dots). Dust on top, powered blocks,
        # lit torches (not attached here), rblk and levers also light (wiki).
        for dx, dz in DIRS:
            if pw.get((cell[0] + dx, cell[1], cell[2] + dz), 0) < 1:
                continue
            if all((cell[0] + dx + ex, cell[1], cell[2] + dz + ez) not in dust
                   for ex, ez in DIRS if (ex, ez) != (dx, dz)):
                return True
        if pw.get((cell[0], cell[1] + 1, cell[2]), 0) >= 1:
            return True
        for dx, dz in DIRS:
            m = (cell[0] + dx, cell[1], cell[2] + dz)
            if m in cob and pb.get(m, False):
                return True
            if m in torch and tl.get(m, False) and torch[m] != cell:
                return True
            if m in rblk:
                return True
            if m in lever and vec.get(lever[m], False):
                return True
        return False
    return ({net: _lit(cell) for cell, net in lampnet.items()},
            {c: v for c, v in pw.items() if v},
            {c: 1 if tl.get(c, False) else 0 for c in torch},
            ticks[0],
            {c: 1 if ron.get(c, False) else 0 for c in rep},
            {c: con.get(c, 0) for c in comp})


def _parse_build(blocks, io):
    """Placed blocks/io -> physics structures shared by sim_verify/sequence."""
    dust, torch, lampat, rep, rblk, cob = set(), {}, set(), {}, set(), set()
    comp = {}
    repdelay = {}
    for x, y, z, bid in blocks:
        b, c = base(bid), (x, y, z)
        if b == "minecraft:redstone_wire":
            dust.add(c)
        elif b == "minecraft:redstone_wall_torch":
            face = bid.split("facing=")[1].rstrip("]") if "facing=" in bid else "east"
            back = {"east": (-1, 0), "west": (1, 0), "south": (0, -1), "north": (0, 1)}[face]
            torch[c] = (c[0] + back[0], c[1], c[2] + back[1])
        elif b == "minecraft:redstone_torch":
            # ponytail: STANDING torch, added so other people's builds can be
            # checked by this sim (RDL emits 70 of them in alu1 and nothing
            # modelled them, so its output was never physics-testable here).
            # Attaches to the block BELOW, which is what makes it a different
            # case: a wall torch is triggered by a block on its own level, a
            # standing one by the block under its feet, so `attach_rev` and
            # the "t" rule (v = not powered(attach)) both work unchanged.
            # Wiki: a torch powers every adjacent block EXCEPT the one it is
            # attached to, and is itself powered by that block. So torch[c]
            # pointing down gives the four side dust 15 and leaves the block
            # beneath dark -- which is what dust_lvl's side-only scan already
            # does. Ceiling (pre-existing, both torch types): a cell directly
            # ABOVE a torch is also powered in vanilla and this model does not
            # do it. Never exercised by our tiles (nothing is stacked on a
            # torch); it can matter for a foreign build. upgrade: add the +y
            # neighbour to dust_lvl's torch term, gated on a canary.
            torch[c] = (c[0], c[1] - 1, c[2])
        elif b == "minecraft:redstone_lamp":
            lampat.add(c)
        elif b == "minecraft:repeater":
            face = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            rep[c] = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}[face]
            dly = bid.split("delay=")[1].split(",")[0].rstrip("]") if "delay=" in bid else "1"
            repdelay[c] = max(1, min(4, int(dly)))
        elif b == "minecraft:comparator":
            face = bid.split("facing=")[1].split(",")[0] if "facing=" in bid else "east"
            mode = bid.split("mode=")[1].split(",")[0].rstrip("]") if "mode=" in bid else "compare"
            # wiki: facing points output->input, so the rear input sits at facing dir.
            r = {"east": (1, 0), "west": (-1, 0), "south": (0, 1), "north": (0, -1)}[face]
            comp[c] = {"rear": r, "mode": mode}
        elif b == "minecraft:redstone_block":
            rblk.add(c)
        elif b in ("minecraft:cobblestone", "minecraft:stone"):
            # ponytail: stone pads (finish_assembly, y=0 under every y=1
            # component) join cob. Pads are unpowered lumps, so this changes
            # no value anywhere — but slope-support, loop-flood and lid sets
            # all derive cob from blocks, and leaving pads out meant the sim
            # disagreed with vanilla about what is support. Deliberately NOT
            # extended to _loop_rep/flood cobble (those assume powered when
            # crossing; pads tiling the field would join everything).
            cob.add(c)
        elif b == "minecraft:lever":
            # ponytail: levers are electrical identity, not geometry: which
            # net a lever drives comes from io["levers"], never from its
            # block (face/facing state is irrelevant to power). Explicitly
            # ignored here so the fail-loud below does not fire on them.
            pass
        else:
            # ponytail: fail loud on unknown bids. _parse_build used to drop
            # anything it did not recognize (piston/glass/slab/stair hybrids
            # from a foreign build read as air), so a build could verify
            # green while vanilla conducted/cut through the ignored blocks.
            # Zero behavior change for every bid above.
            raise ValueError(f"sim: unsupported block {bid!r} at {c}")
    def _y(k):
        return (k[0], 1, k[1]) if len(k) == 2 else k
    lever = {_y(k): n for k, n in io["levers"].items()}
    lampnet = {_y(k): n for k, n in io["lamps"].items()}
    attach_rev = {}
    for t, a in torch.items():
        attach_rev.setdefault(a, []).append(t)
    return dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, attach_rev, comp


def sim_verify(recipe, blocks, io, seed=7, quiet=False, collect=False):
    """Independent redstone simulation of the PLACED build (ignores layout nets).
    Plays input vectors through tick-stepped torch/dust physics, compares
    lamps against eval_net. Catches opens/shorts the static guards can't see.
    # ponytail: flat builds plus chip-layer verticals (dust slopes, lid rule);
    # vanilla tick delays (torch +1, repeater +its delay stage).
    """
    import random as _r
    P = _parse_build(blocks, io)

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
    maxticks = 0
    latchouts = {g["out"] for g in recipe["gates"] if g["op"] == "LATCH"}
    latchargs = {a for g in recipe["gates"] if g["op"] == "LATCH" for a in g["args"]}
    states = None
    if collect and len(combos) <= 16:
        states = {"inputs": list(ins),
                  "levers": {f"{x},1,{z}": n for (x, z), n in io["levers"].items()},
                  "lamps": {f"{x},1,{z}": n for (x, z), n in io["lamps"].items()},
                  "vectors": {}}
    for vec in combos:
        exp = eval_net(recipe, vec)
        if latchouts and not any(exp.get(a, False) for a in latchargs):
            continue  # undefined power-on: hold needs history (real hardware
            # too — reset first). The sequence proof covers hold properly.
        got, live, tlive, nticks, rlive, _conc = _run_vec(vec, None, P)
        maxticks = max(maxticks, nticks)
        for net in recipe["outputs"]:
            if net not in latchouts and bool(got.get(net, False)) != bool(exp[net]):
                bad.append((vec, net, got.get(net), bool(exp[net])))
                lastlive = live
        if states is not None:
            vkey = "".join(str(vec[n]) for n in ins)
            states["vectors"][vkey] = {
                "w": {f"{x},{y},{z}": v for (x, y, z), v in live.items()},
                "t": {f"{x},{y},{z}": v for (x, y, z), v in tlive.items()},
                "lamps": {f"{x},1,{z}": 1 if got.get(net, False) else 0
                          for (x, z), net in io["lamps"].items()},
                "ticks": nticks,
                "r": {f"{x},{y},{z}": v for (x, y, z), v in rlive.items()},
                "o": {f"{x},{y},{z}": v for (x, y, z), v in _conc.items()}}
    if bad:
        raise RuntimeError(f"SIM MISMATCH x{len(bad)}: {bad[:4]} live: {sorted(lastlive.items())}")
    if not quiet:
        print(f"sim ok: {len(combos)} vectors, lamps match logic")
    return states, maxticks


def sim_sequence(recipe, blocks, io, phases):
    """Drive input phases with state carried across (memory!). phases is a
    list of (vec, expected-lamps); tick counters reset per phase, only lamps
    are asserted. Raises RuntimeError on mismatch."""
    P = _parse_build(blocks, io)
    carry = None
    for vec, exp in phases:
        got, live, tlive, _, rlive, _conc = _run_vec(vec, carry, P)
        for net, want in exp.items():
            if bool(got.get(net, False)) != bool(want):
                raise RuntimeError(f"SEQ MISMATCH on {vec}: {net} got {got.get(net)} want {want}")
        carry = {"w": live, "t": tlive, "r": rlive, "o": _conc}


def sim_pulse(recipe, blocks, io, schedule):
    """Drive a timed input schedule with state carried across segments.
    schedule is [(vec, dwell_ticks)]; dwell >= 1 (loud otherwise). A button
    press is just [({B: 1}, 20), ({B: 0}, n)]. Returns [(lamps, elapsed)]
    per segment. Lamp trailing edge stays unmodeled (2-tick-off gap)."""
    P = _parse_build(blocks, io)
    carry, out = None, []
    for vec, dwell in schedule:
        if dwell < 1:
            raise ValueError(f"bad dwell {dwell} (use >= 1 tick)")
        got, live, tlive, _, rlive, _conc = _run_vec(vec, carry, P, until=dwell)
        out.append((got, dwell))
        carry = {"w": live, "t": tlive, "r": rlive, "o": _conc}
    return out


if __name__ == "__main__":
    # ponytail: one runnable check — delay-4 chain must settle at exactly tick 4.
    _blocks = [(1, 1, 0, "minecraft:repeater[facing=east,delay=4]"),
               (2, 1, 0, "minecraft:redstone_wire"),
               (3, 1, 0, "minecraft:redstone_lamp")]
    _io = {"levers": {(0, 0): "a"}, "lamps": {(3, 0): "y"}, "nets": {}}
    _recipe = {"inputs": ["a"], "outputs": ["y"],
               "gates": [{"out": "y", "op": "OR", "args": ["a", "a"]}]}
    _st, _ = sim_verify(_recipe, _blocks, _io, quiet=True, collect=True)
    assert _st["vectors"]["1"]["lamps"] == {"3,1,0": 1}, _st["vectors"]["1"]
    assert _st["vectors"]["1"]["ticks"] == 4, _st["vectors"]["1"]["ticks"]
    _st2, _tk = sim_verify(_recipe, _blocks, _io, quiet=True, collect=True)
    assert _tk == 4, _tk
    assert _st["vectors"]["0"]["lamps"] == {"3,1,0": 0}, _st["vectors"]["0"]
    print("tick ok: delay-4 settles at tick 4")
    # ponytail: timed-press proof — stone-20 press lights through delay-4,
    # release holds 1 tick (repeater delay) then drops dark with the dust.
    _pb = [(0, 1, 0, "minecraft:lever")] + _blocks
    _pio = {"levers": {(0, 0): "a"}, "lamps": {(3, 0): "y"}, "nets": {}}
    _pr = {"inputs": ["a"], "outputs": ["y"],
           "gates": [{"out": "y", "op": "OR", "args": ["a", "a"]}]}
    _pt = sim_pulse(_pr, _pb, _pio, [({"a": 1}, 20), ({"a": 0}, 1), ({"a": 0}, 4)])
    assert _pt[0][0].get("y", False) is True, _pt[0]
    assert _pt[1][0].get("y", False) is True, _pt[1]
    assert _pt[2][0].get("y", True) is False, _pt[2]
    try:
        sim_pulse(_pr, _pb, _pio, [({"a": 1}, 0)])
        assert False, "dwell 0 should raise"
    except ValueError:
        pass
    print("pulse ok: press-20 lights, holds 1, drops by 5; dwell guarded")
    from export import export_html
    _blocks = [(0, 1, 0, "minecraft:lever"),
               (1, 1, 0, "minecraft:repeater[facing=east,delay=4]"),
               (2, 1, 0, "minecraft:redstone_wire"),
               (3, 1, 0, "minecraft:redstone_wall_torch[facing=east]"),
               (4, 1, 0, "minecraft:redstone_lamp")]
    _io = {"levers": {(0, 0): "a"}, "lamps": {(4, 0): "y"}, "nets": {}}
    _st = {"inputs": ["a"], "levers": {"0,1,0": "a"}, "lamps": {"4,1,0": "y"},
           "vectors": {"0": {"w": {}, "t": {"3,1,0": 0}, "lamps": {"4,1,0": 0},
                             "ticks": 0, "r": {"1,1,0": 0}}}}
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
    from recipe import parse_recipe
    _lr = parse_recipe("IN S, R\nOUT Q\nQ = LATCH S R\n")
    _lb, _lsz, _lio, _ = layout_retry(_lr, verify=True)
    sim_sequence(_lr, _lb, _lio, [({"S": 1, "R": 0}, {"Q": 1}),
                                  ({"S": 0, "R": 0}, {"Q": 1}),
                                  ({"S": 0, "R": 1}, {"Q": 0}),
                                  ({"S": 0, "R": 0}, {"Q": 0})])
    print("latch ok: set/hold/reset/hold")
    # ponytail: gate-fed latch, EVERY seed — a lever-fed latch proves the tile,
    # gate-fed proves arrival level too. Killed two classes: dust+repeater
    # double-stamped on the S-row cell (seeds 4/5 held set across hold) and a
    # route through the repeater cell (seed 1 never fed the load). One layout
    # hides this whole class, so all seven ship.
    _dr = parse_recipe("IN D, W\nOUT Q\nnD = NOT D\nS = D AND W\nR = nD AND W\nQ = LATCH S R\n")
    _dph = [({"D": 1, "W": 1}, {"Q": 1}), ({"D": 0, "W": 1}, {"Q": 0}),
            ({"D": 0, "W": 0}, {"Q": 0}), ({"D": 1, "W": 0}, {"Q": 0}),
            ({"D": 1, "W": 1}, {"Q": 1})]
    for _seed in (None, 0, 1, 2, 3, 4, 5):
        _db, _, _dio = layout(_dr, seed=_seed, grow=0)
        _seen, _dups = {}, set()
        for _x, _y, _z, _b in _db:  # one pass; only dust-involved dups matter
            _k, _bb = (_x, _y, _z), _b.split("[")[0]
            if _k in _seen and (_seen[_k] == "minecraft:redstone_wire"
                                or _bb == "minecraft:redstone_wire"):
                _dups.add(_k)
            _seen[_k] = _bb
        assert not _dups, (_seed, _dups)
        sim_sequence(_dr, _db, _dio, _dph)
    print("dlatch ok: gate-fed latch green on all 7 seeds, no dust double-stamped")
    def _hand(blocks, levers, lamps):
        io = {"levers": levers, "lamps": lamps, "nets": {}}
        return _parse_build(blocks, io), io
    W_ = "minecraft:redstone_wire"
    # case1: stacked dust-block-dust has NO link
    _b1 = [(0, 1, 0, "minecraft:lever"), (0, 1, 1, W_),
           (0, 2, 1, "minecraft:cobblestone"), (0, 3, 1, W_), (1, 3, 1, "minecraft:redstone_lamp")]
    _p1, _io1 = _hand(_b1, {(0, 0): "A"}, {(1, 3, 1): "B"})
    _g1, _, _, _, _, _ = _run_vec({"A": 1}, None, _p1)
    assert _g1.get("B", False) is False, _g1
    # case2: step-up links
    _b2 = [(0, 1, -1, "minecraft:lever"), (0, 1, 0, W_),
           (1, 1, 0, "minecraft:cobblestone"), (1, 2, 0, W_), (2, 2, 0, "minecraft:redstone_lamp")]
    _p2, _io2 = _hand(_b2, {(0, -1): "A"}, {(2, 2, 0): "B"})
    _g2, _, _, _, _, _ = _run_vec({"A": 1}, None, _p2)
    assert _g2.get("B", False) is True, _g2
    # case3: lid on the lower wire blocks the up-link
    _b3 = _b2 + [(0, 2, 0, "minecraft:cobblestone")]
    _p3, _io3 = _hand(_b3, {(0, -1): "A"}, {(2, 2): "B"})
    _g3, _, _, _, _, _ = _run_vec({"A": 1}, None, _p3)
    assert _g3.get("B", False) is False, _g3
    print("vertical units ok: stacked dark, step-up lit, lid blocks")
    # pointing: end-of-line dust lights the lamp beyond its tip...
    _b4 = [(0, 1, 0, "minecraft:lever"), (1, 1, 0, W_), (2, 1, 0, W_), (3, 1, 0, "minecraft:redstone_lamp")]
    _p4, _io4 = _hand(_b4, {(0, 0): "A"}, {(3, 1, 0): "B"})
    _g4, _, _, _, _, _ = _run_vec({"A": 1}, None, _p4)
    assert _g4.get("B", False) is True, _g4
    # ...but a straight run passing sideways does not light a side lamp.
    _b5 = [(0, 1, 0, "minecraft:lever"), (1, 1, 0, W_), (2, 1, 0, W_), (3, 1, 0, W_), (1, 1, 1, "minecraft:redstone_lamp")]
    _p5, _io5 = _hand(_b5, {(0, 0): "A"}, {(1, 1, 1): "B"})
    _g5, _, _, _, _, _ = _run_vec({"A": 1}, None, _p5)
    assert _g5.get("B", False) is False, _g5
    print("lamp pointing ok: tip lights, passerby dark")
    CB = "minecraft:cobblestone"
    _xb = [(2, 1, 5, "minecraft:lever")] + [(x, 1, 5, W_) for x in range(3, 10)] + [(10, 1, 5, "minecraft:redstone_lamp")]
    _xb += [(7, 1, 1, "minecraft:lever"), (7, 1, 2, W_), (7, 1, 3, W_)]
    _xb += [(7, 1, 4, CB), (7, 1, 6, CB), (7, 2, 5, CB)]
    _xb += [(7, 2, 4, W_), (7, 3, 5, W_), (7, 2, 6, W_)]
    _xb += [(7, 1, 7, W_), (7, 1, 8, W_), (7, 1, 9, "minecraft:redstone_lamp")]
    _xp, _xio = _hand(_xb, {(2, 5): "A", (7, 1): "B"}, {(10, 5): "Aout", (7, 9): "Bout"})
    _xr = {"inputs": ["A", "B"], "outputs": ["Aout", "Bout"],
           "gates": [{"out": "Aout", "op": "AND", "args": ["A", "A"]},
                     {"out": "Bout", "op": "AND", "args": ["B", "B"]}]}
    sim_sequence(_xr, _xb, _xio, [({"A": 1, "B": 0}, {"Aout": 1, "Bout": 0}),
                                  ({"A": 0, "B": 1}, {"Aout": 0, "Bout": 1}),
                                  ({"A": 1, "B": 1}, {"Aout": 1, "Bout": 1}),
                                  ({"A": 0, "B": 0}, {"Aout": 0, "Bout": 0})])
    print("crossover ok: wires cross overhead, independent both ways")
    from export import export_html
    export_html(_xb, (14, 14), r"C:\Users\LOQ\AppData\Local\Temp\opencode\xcross.html", "x", None)
    import json as _json2
    _h2 = open(r"C:\Users\LOQ\AppData\Local\Temp\opencode\xcross.html").read()
    _d2 = _json2.loads(_h2[_h2.find("const B=") + len("const B="):_h2.find(";const s=", _h2.find("const B="))])
    assert any(d["p"] == [7, 3, 5] and d["b"] == "minecraft:redstone_wire" for d in _d2), "no elevated dust rendered"
    # facing=west puts the rear input west, so the rendered arrow points east
    export_html([(0, 1, 0, "minecraft:comparator[facing=west,mode=compare]")], (4, 4), r"C:\Users\LOQ\AppData\Local\Temp\opencode\cmp.html", "c", None)
    _hc = open(r"C:\Users\LOQ\AppData\Local\Temp\opencode\cmp.html").read()
    _dc = _json2.loads(_hc[_hc.find("const B=") + len("const B="):_hc.find(";const s=", _hc.find("const B="))])
    assert any(d["b"] == "minecraft:comparator" and d.get("f") == [1, 0] for d in _dc), _dc
    CMP = "minecraft:comparator"
    # compare passthrough: rear 15, no sides -> 15
    _cb = [(2, 1, 0, "minecraft:lever"), (1, 1, 0, "minecraft:redstone_wire"),
           (0, 1, 0, CMP + "[facing=east,mode=compare]"),
           (-1, 1, 0, "minecraft:redstone_wire"), (-2, 1, 0, "minecraft:redstone_lamp")]
    _cp, _cio = _hand(_cb, {(2, 0): "A"}, {(-2, 0): "Y"})
    _cg, _, _, _, _, _ = _run_vec({"A": 1}, None, _cp)
    assert _cg.get("Y", False) is True, _cg
    # compare blocked: repeater-fed side (15) exceeds attenuated rear (14)
    _cb2 = [(3, 1, 0, "minecraft:lever"), (2, 1, 0, "minecraft:redstone_wire"),
            (1, 1, 0, "minecraft:redstone_wire"),
            (0, 1, 0, CMP + "[facing=east,mode=compare]"),
            (-1, 1, 0, "minecraft:redstone_wire"), (-2, 1, 0, "minecraft:redstone_lamp"),
            (0, 1, 1, "minecraft:repeater[facing=north,delay=1]"), (0, 1, 2, "minecraft:lever")]
    _cp2, _cio2 = _hand(_cb2, {(3, 0): "A", (0, 2): "S"}, {(-2, 0): "Y"})
    _cg2, _, _, _, _, _ = _run_vec({"A": 1, "S": 1}, None, _cp2)
    assert _cg2.get("Y", False) is False, _cg2
    # dust side-feed does NOT suppress (researched rule)
    _cb3 = _cb + [(0, 1, 1, "minecraft:redstone_wire"), (-1, 1, 1, "minecraft:lever")]
    _cp3, _io3 = _hand(_cb3, {(2, 0): "A", (-1, 1): "S"}, {(-2, 0): "Y"})
    _cg3, _, _, _, _, _ = _run_vec({"A": 1, "S": 1}, None, _cp3)
    assert _cg3.get("Y", False) is True, _cg3
    # subtract: rear 15, repeater side 15 -> 0; rear alone -> 15
    _cb4 = [(2, 1, 0, "minecraft:lever"), (1, 1, 0, "minecraft:redstone_wire"),
            (0, 1, 0, CMP + "[facing=east,mode=subtract]"),
            (-1, 1, 0, "minecraft:redstone_wire"), (-2, 1, 0, "minecraft:redstone_lamp"),
            (0, 1, 1, "minecraft:repeater[facing=north,delay=1]"), (0, 1, 2, "minecraft:lever")]
    _cp4, _io4 = _hand(_cb4, {(2, 0): "A", (0, 2): "S"}, {(-2, 0): "Y"})
    assert _run_vec({"A": 1, "S": 1}, None, _cp4)[0].get("Y", True) is False
    assert _run_vec({"A": 1, "S": 0}, None, _cp4)[0].get("Y", False) is True
    print("comparator ok: compare/subtract/strong-side rule")
    # ponytail: corner pointing is directional (wiki: a corner powers where it
    # points, not the mirror side). cob_state once read (dx,dz) block->dust
    # instead of dust->block, which symmetric shapes (line/end/cross) cannot
    # tell apart — the whole suite stayed green around the bug. Corner N+E
    # with a block south: block dark, torch on it stays ON.
    _mb = [(1, 1, 0, W_), (1, 1, -1, W_), (2, 1, 0, W_),
           (1, 1, 1, "minecraft:cobblestone"),
           (2, 1, 1, "minecraft:redstone_wall_torch[facing=west]")]
    _mp, _mio = _hand(_mb, {}, {})
    _, _, _mtl, _, _, _ = _run_vec({}, None, _mp)
    assert _mtl.get((2, 1, 1), 0) == 1, _mtl
    print("pointing-mirror ok: corner leaves its unconnected side dark")
    # ponytail: standing torch (minecraft:redstone_torch). Two cases, one per
    # direction, so a sign error cannot pass. Built at y=0/1 because
    # _parse_build's lever/lamp io keys are (x,z) and _y pins them to y=1.
    # "Does not power the block below" is not asserted: it is structural
    # (dust_lvl scans only the 4 HORIZONTAL neighbours for a torch, and
    # cob_state's `up` term only counts dust) and the two cases below bracket
    # it -- lit on an unpowered support, dark on a powered one.
    _st = [(1, 0, 0, CB), (1, 1, 0, "minecraft:redstone_torch"),
           (2, 1, 0, W_), (3, 1, 0, "minecraft:redstone_lamp")]
    _pst, _iost = _hand(_st, {}, {(3, 0): "side"})
    assert _run_vec({}, None, _pst)[0].get("side", False) is True, "torch must power its side"
    # powered from below -> the torch inverts and the side lamp goes out
    _st3 = [(1, 0, 0, "minecraft:redstone_block"),
            (1, 1, 0, "minecraft:redstone_torch"),
            (2, 1, 0, W_), (3, 1, 0, "minecraft:redstone_lamp")]
    _pst3, _iost3 = _hand(_st3, {}, {(3, 0): "side"})
    assert _run_vec({}, None, _pst3)[0].get("side", False) is False, "lit torch kills its side"
    print("standing-torch ok: powers its side, inverts its support below")
    # ponytail: lamp/comparator/burnout oracle checks (wiki + cmc engine).
    # Dust on top lights; powered block beside lights; lit torch (not
    # attached here) lights. Comparator side dust counts (subtract kills).
    # A hunting torch burns out dark instead of hanging the run.
    _lb = [(0, 2, 1, "minecraft:redstone_wall_torch"), (1, 2, 1, W_),
           (1, 1, 1, "minecraft:redstone_lamp")]
    _lp2, _ = _hand(_lb, {}, {(1, 1): "y"})
    assert _run_vec({}, None, _lp2)[0].get("y", False) is True, "dust-on-top must light"
    _bb = [(0, 1, 0, "minecraft:lever"), (1, 1, 0, W_), (1, 1, 1, CB),
           (2, 1, 1, "minecraft:redstone_lamp")]
    _bp, _ = _hand(_bb, {(0, 0): "a"}, {(2, 1): "y"})
    assert _run_vec({"a": 1}, None, _bp)[0].get("y", False) is True, "powered block must light"
    _tb = [(0, 1, 1, "minecraft:redstone_wall_torch[facing=east]"),
           (0, 1, 0, CB), (1, 1, 1, "minecraft:redstone_lamp")]
    _tp, _ = _hand(_tb, {}, {(1, 1): "y"})
    assert _run_vec({}, None, _tp)[0].get("y", False) is True, "lit torch must light"
    # ponytail: lever -> host block -> dust on top, with the lever on the
    # SIDE and the feeding run arriving from the far side (wiki: a lever
    # strongly powers the block it is attached to). This is the zero-wire,
    # direction-agnostic source the hier boundary stubs need; assert both
    # directions so a future "levers are weak-power only" edit fails here.
    _lv = [(0, 1, 0, "minecraft:lever[face=wall,facing=east,powered=false]"),
           (0, 1, 1, CB), (0, 2, 1, W_),
           (-1, 1, 1, W_), (-2, 1, 1, CB), (-3, 1, 1, W_)]
    _lp3, _ = _hand(_lv, {(0, 0): "a"}, {(0, 2): "y"})
    assert _run_vec({"a": 1}, None, _lp3)[0].get("y", False) is True, \
        "lever must power its host block and the dust on top"
    assert _run_vec({"a": 0}, None, _lp3)[0].get("y", False) is False, \
        "unpowered lever must not light the pedestal"
    # ponytail: dust directly above a torch (wiki: powered in vanilla; the
    # parser comment asked for this term gated on a canary — this is it).
    # Standing torch on dark cobble (lit) lights dust above; powered support
    # (torch off) leaves it dark. Asserted on dust levels directly (a lamp
    # beside would add pointing-shape noise to a physics canary).
    _tb2 = [(0, 1, 0, CB), (0, 2, 0, "minecraft:redstone_torch"),
            (0, 3, 0, W_)]
    _tp2, _ = _hand(_tb2, {}, {})
    assert _run_vec({}, None, _tp2)[1].get((0, 3, 0), 0) == 15, \
        "dust above a lit torch must light"
    # ponytail: torch powers neighboring blocks except its host. Wall torch
    # beside (not on) a cobble lights dust on top of that cobble; the same
    # torch does NOT power the block it is attached to (host exception).
    _tb3 = [(0, 1, 0, CB), (1, 1, 0, "minecraft:redstone_wall_torch[facing=west]"),
            (0, 2, 0, W_)]
    _tp3, _ = _hand(_tb3, {}, {})
    assert _run_vec({}, None, _tp3)[1].get((0, 2, 0), 0) == 15, \
        "torch beside cobble must power it (dust on top lights)"
    # ponytail: host exception — a wall torch does NOT power the block it is
    # attached to. Torch at (1,1,0) facing west attaches east to (2,1,0):
    # dust on top of the host stays dark, while dust on top of the western
    # neighbour cobble (0,1,0) lights.
    _tb4 = [(2, 1, 0, CB), (1, 1, 0, "minecraft:redstone_wall_torch[facing=west]"),
            (2, 2, 0, W_), (0, 1, 0, CB), (0, 2, 0, W_)]
    _tp4, _ = _hand(_tb4, {}, {})
    _pw4 = _run_vec({}, None, _tp4)[1]
    assert _pw4.get((2, 2, 0), 0) == 0, "host block of a torch stays dark"
    assert _pw4.get((0, 2, 0), 0) == 15, "neighbour block of a torch lights"
    print("lamp-sources ok: top dust, powered block, free torch, lever-pedestal")
    _sb = [(2, 1, 0, "minecraft:lever"), (1, 1, 0, W_),
           (0, 1, 0, CMP + "[facing=east,mode=subtract]"),
           (0, 1, 1, W_), (0, 1, 2, "minecraft:lever"),
           (-1, 1, 0, W_), (-2, 1, 0, "minecraft:redstone_lamp")]
    _sp, _sio = _hand(_sb, {(2, 0): "r", (0, 2): "s"}, {(-2, 0): "y"})
    _sg, _, _, _, _, _sc = _run_vec({"r": 1, "s": 1}, None, _sp)
    assert _sc.get((0, 1, 0), 99) == 0 and _sg.get("y", True) is False, "side dust must suppress"
    print("comp-side-dust ok: subtract kills on hot side dust")
    _ob = [(0, 1, 0, CB), (1, 1, 0, "minecraft:redstone_wall_torch[facing=east]"),
           (2, 1, 0, W_), (2, 1, 1, W_), (2, 1, 2, W_), (1, 1, 2, W_),
           (0, 1, 2, W_), (0, 1, 1, W_)]
    _op, _ = _hand(_ob, {}, {})
    try:
        _run_vec({}, None, _op)
        assert False, "burnout clock should burn, not settle"
    except RuntimeError as _e:
        assert "BURNOUT" in str(_e), str(_e)[:80]
    print("torch-burnout ok: hunting torch dies dark, loud")
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    _b, _, _, _st = layout_retry(_r, verify=True)
    assert _st is not None and len(_b) > 0
    print("ladder ok: compose-first returns a verified build")
    # ponytail: Phase-C infra. Budget guard fires LOUD (a silent short ladder
    # reads as "verified"); snapshot round-trips a green build through the sim
    # gate; fail-only mode records nothing for a good build.
    import pathlib
    import tempfile
    import snapshot as _snap
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    # The canary must not depend on any recipe staying red: this check used
    # alu1 on the belief that compose refuses it, and it went stale the moment
    # alu1 went green (layout_retry returned a verified build, assert fired).
    # Force the precondition instead — a composer that always fails — so the
    # seed-loop budget guard is what is actually under test, in microseconds.
    _dense = parse_recipe(open("recipes/alu1.txt").read())
    _save, _MAX_SECS = _MAX_SECS, 1e-9
    _real = compose
    try:
        # ponytail: patch THIS module's from-import binding (layout_retry
        # reads the sim-module global, not compose.compose — patching the
        # attribute on the compose module is a silent no-op, measured).
        def _nope(_r):
            raise RuntimeError("compose: no ground for canary: (0,0)->(1,1)")
        globals()["compose"] = _nope
        layout_retry(_dense, tries=3, verify=True, grows=1)
        assert False, "REDSTONE_MAX_SECS should have fired"
    except RuntimeError as _e:
        assert "BUDGET" in str(_e), str(_e)[:200]
    finally:
        globals()["compose"] = _real
        _MAX_SECS = _save
    _os.environ["REDSTONE_SNAPSHOT_DIR"] = str(
        pathlib.Path(tempfile.gettempdir()) / "rs-snap-canary")
    _os.environ["REDSTONE_SNAPSHOT"] = "all"
    for _old in _snap.target().glob("*.json"):
        _old.unlink()  # hermetic canary: stale temp snapshots fail the count below
    try:
        _b, _, _i, _st = layout_retry(_r, verify=True)
        _files = sorted(_snap.target().glob("*.json"))
        assert len(_files) == 1, _files
        _rb, _ri, _rst, _tk = _snap.replay(_files[0])
        assert _tk and _rst["vectors"], (_tk, _rst)
        assert _rb == _b, "replay must rebuild the same build"
        _os.environ["REDSTONE_SNAPSHOT"] = "fail"
        _b2, _, _, _ = layout_retry(_r, verify=True)
        assert len(sorted(_snap.target().glob("*.json"))) == 1, "fail mode wrote a good build"
    finally:
        del _os.environ["REDSTONE_SNAPSHOT"]
        del _os.environ["REDSTONE_SNAPSHOT_DIR"]
    print("budget+snapshot ok: guard loud, build recorded, replayed, fail-mode clean")

