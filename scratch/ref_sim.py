"""FROZEN reference copy of sim.py's physics, extracted from git HEAD.
Do not edit: scratch/diff_engine.py compares the live engine against this
to prove an optimisation changed nothing but the speed.
"""
import heapq as _hq
import os as _os

from core import DIRS, base
from layout import dust_points

TICK_CAP = 20000
STEP_CAP = 2000000
STALL = 5000
BOUT_N = 8
BOUT_GRACE = 60
BOUT = {}


def _parse_build(blocks, io):
    """Placed blocks/io -> physics structures shared by sim_verify/sequence."""
    dust, torch, lampat, rep, rblk, cob = set(), {}, set(), {}, set(), set()
    comp = {}
    repdelay = {}
    leveratt = {}
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
            # no value anywhere â€” but slope-support, loop-flood and lid sets
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
            # The ATTACHMENT (wiki: a lever strongly powers only its
            # attachment block) does matter, so it is recorded: wall levers
            # attach to the faced-away side cell, floor below, ceiling above.
            # Bare bids (hand tests) record None = legacy all-side power.
            if "face=" in bid and "facing=" in bid:
                _face = bid.split("face=")[1].split(",")[0]
                _facing = bid.split("facing=")[1].split(",")[0]
                if _face == "wall":
                    _back = {"east": (-1, 0), "west": (1, 0),
                             "south": (0, -1), "north": (0, 1)}[_facing]
                    leveratt[c] = (c[0] + _back[0], c[1], c[2] + _back[1])
                elif _face == "floor":
                    leveratt[c] = (c[0], c[1] - 1, c[2])
                elif _face == "ceiling":
                    leveratt[c] = (c[0], c[1] + 1, c[2])
                else:
                    leveratt[c] = None
            else:
                leveratt[c] = None
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
    return dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, attach_rev, comp, leveratt



def _run_vec(vec, init, ctx, until=None):
    """Tick-settled physics for one input vector (shared by verify/sequence).
    init carries live/torch/repeater state across phases (memory!); None
    starts blank. until caps the run at a tick (for sim_pulse timelines).
    Returns (lamps, live, torches, ticks, repeaters)."""
    dust, torch, lampat, rep, rblk, cob, repdelay, lever, lampnet, attach_rev, comp, leveratt = ctx
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
        # for it gated on a canary â€” the canary is below in __main__).
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
            # ponytail: chip layers. Dust links Â±1 level iff the upper dust
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
            # (dust_points, the one shared table) â€” a wire merely running past
            # does not. Dust on top still counts (below), no shape condition.
            # Direction is dust->block (negated neighbour offset); the old
            # sign mirrored corner/T sensing (symmetric shapes can't tell).
            if m in dust and pw.get(m, 0) >= 1 and (-dx, -dz) in dust_points(m, dust):
                pwrd = True
            if m in rblk:
                pwrd, strong = True, True
            # ponytail: a LEVER powers its ATTACHMENT block only (wiki:
            # levers strongly power their attachment block; adjacent dust is
            # powered directly, see dust_lvl). Floor levers attach below,
            # wall to the faced-away side, ceiling above. The old term
            # powered EVERY side block, so a floor input lever lit adjacent
            # foreign cobble â€” measured: D3's floor lever at (1012,34) drove
            # R0Q0's stitch dust at (1011,33) to 15 through (1012,33). Bare
            # bids (hand tests) keep legacy all-side power (attach None).
            if (m in lever and vec.get(lever[m], False)
                    and _os.environ.get("REDSTONE_LEVER_POWER", "1") == "1"
                    and (leveratt.get(m) is None or leveratt.get(m) == c)):
                pwrd, strong = True, True
            # ponytail: a lit torch powers adjacent blocks â€” except the one
            # it is attached to (wiki; the same host exception the torch rule
            # itself uses, via torch[m] != c). Without this, dust sitting on
            # cobble whose only power is a neighboring torch reads lit (dust
            # above torch, done above) while its support reads dark â€” a split
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

    if init and init.get("_solve"):
        # ponytail: glitch-free power-on. Every gate output torch starts OFF,
        # so at tick 1 each fires once before its inputs arrive â€” a 1-2 tick
        # pulse on EVERY combinational output. Harmless for DAG logic (it
        # settles), but a boosted S/R run delivers that pulse to an idle
        # latch at T~9 (measured: R1_S1 spikes to 10, the seeded hold-0
        # breaks into a permanent symmetric hunt, whole-ALU churn=15016).
        # The pre-roll iterates the WHOLE field to its tick-0 fixpoint
        # (dust/blocks/repeaters/comparators/torches; hold-0 ~qb torches pinned
        # ON), so tick 0 starts per truth with zero pulses and only genuine
        # arrivals move. Undriven dust still decays, driven S|R still force, so
        # opens/shorts stay loud. Latch-free builds never set _solve (untouched
        # path).
        # ponytail: repeaters belong IN the fixpoint. They used to be frozen
        # OFF on the theory that their delay is a real transient the loop must
        # play out â€” but a frozen booster makes every cell BEYOND it read dark
        # at tick 0, so the fixpoint was not the quiescent state, it was a
        # half-powered one. Every downstream gate then emitted a phantom pulse
        # as the boosters came up (measured on cpu4: OPC1 read 96/903 at tick 0
        # instead of 903/903, NOT OPC1 fired, and C_n2 AND C_n1 drove a 40-tick
        # REGW glitch at T~28 that reached R0_S1 at T~120 and latched R0Q1/R0Q3
        # to 1 on a no-write vector). The delay is real, but a booster's
        # SETTLED value is a function of its input, so iterating it converges to
        # exactly what the circuit settles to â€” which is the whole point.
        _pins = set(init.get("t", {}))

        def _presolve(with_rep):
            for c in rep:
                ron[c] = False
            for c in comp:
                con[c] = 0
            for _ in range(20000):
                _ch = False
                for c in dust:
                    v = dust_lvl(c)
                    if pw.get(c, 0) != v:
                        pw[c] = v
                        _ch = True
                for c in cob:
                    v, s = cob_state(c)
                    if pb.get(c, False) != v or pbs.get(c, False) != s:
                        pb[c], pbs[c] = v, s
                        _ch = True
                if with_rep:
                    for c in rep:
                        v = rep_on(c)
                        if ron.get(c, False) != v:
                            ron[c] = v
                            _ch = True
                    for c in comp:
                        v = comp_out(c)
                        if con.get(c, 0) != v:
                            con[c] = v
                            _ch = True
                for c in torch:
                    if c in _pins:
                        continue
                    v = not (pb.get(torch[c], False) or torch[c] in rblk)
                    if tl.get(c, False) != v:
                        tl[c] = v
                        _ch = True
                if not _ch:
                    return True
            return False

        if not _presolve(True):
            # ponytail: no fixpoint WITH boosters means a real oscillator (or a
            # net that only settles by ringing). Fall back to the booster-free
            # pre-solve so the tick loop still runs and reports the CHURN SET,
            # which names the loop â€” a bare "did not converge" here would throw
            # that diagnosis away.
            _presolve(False)

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
        _stall_cap = max(STALL, 3 * (len(dust) + len(cob) + len(torch)
                                     + len(rep) + len(comp)))
        if steps[0] - last_change[0] > _stall_cap:
            raise RuntimeError(
                f"sim STALLED on {vec}: no value change for "
                f"{steps[0] - last_change[0]} steps at tick {now} "
                f"({steps[0]} steps run) â€” wedged, not oscillating")
        if now > TICK_CAP or steps[0] > STEP_CAP:
            # ponytail: name the OSCILLATOR, not the leftovers. `live` is
            # whatever happened to be lit at timeout â€” on a ring oscillator
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
                # structurally invisible to the churn set â€” the indicator could
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
                # ponytail: vanilla burnout â€” a torch forced OFF more than
                # eight times in 60 game ticks (= 30 sim ticks: delay-4 settles
                # at tick 4, so 1 sim tick is 1 redstone tick) dies dark. OFF
                # transitions only: a healthy settle flips a few times total,
                # hunts alternate forever. Shipping gate fails loud, not hangs.
                if tl.get(c, False) and not v:
                    _bt = tuple(t for t in _bout.get(c, ()) if now - t < 30) + (now,)
                    _bout[c] = _bt
                    if len(_bt) > max(BOUT.get(c, 0), 0):
                        BOUT[c] = len(_bt)
                    # ponytail: power-on grace (REDSTONE_BURNOUT_GRACE ticks,
                    # default 60). Latches with stitched enables ring during
                    # the power-on transient (enable arrives ~20-30 ticks in
                    # on a 200-cell boosted stitch; the symmetric ring flips
                    # every ~2 ticks and burns at ~16, before the enable can
                    # force it). The grace delays the verdict, never flips
                    # it: a true oscillator flaps forever (burns after grace
                    # all the same); a transient settles (green either way).
                    # Verdict-preserving by construction; greens that settle
                    # early never notice it.
                    if len(_bt) > BOUT_N and now >= BOUT_GRACE:
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


