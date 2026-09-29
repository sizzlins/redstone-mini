# Deterministic input lanes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compile each input's delivery as stamped straight lanes (N-S trunk, E-W transit with deterministic bridges, deterministic repeaters) plus short routed stubs, so all builds verify green with one lever per input.

**Architecture:** After task ordering, a compiler block claims a free E-W lane per input, stamps N-S trunks and E-W transits straight (bridging trunk crossings deterministically), spaces repeaters deterministically, then swaps input star tasks for short stub tasks (gates route first, unchanged). Lanes join `placed` via snapshot order (unrippable); the only search left is short stubs.

**Tech Stack:** Python 3, stdlib only. No new dependencies, no new repo files (probes live in gitignored `scratch/`).

## Global Constraints

- Modify only `D:\redstone-mini\layout.py`.
- `sim.py`, `export.py`, `serve.py`, `core.py`, `recipe.py`, `debug.py` stay untouched.
- No new dependencies, no new repo files. Test probes go in `scratch/` (gitignored, never merged).
- Unroutable lanes/stubs raise loudly (no fallback paths, no search loops).
- Seed-None runs are deterministic; lane geometry is order-independent (identical field on every seed — only gate routing varies).
- Dense builds (alu4/cpu4) run only as background jobs with log files + polling, never foreground. Kill rule: no log output for 600s → confirm no other python work is running (`Get-Process python`), then stop the job.
- One change per task: implement, measure, keep-or-revert. Never stack a new fix on a red baseline.

---

## File structure

All work happens in `D:\redstone-mini\layout.py`:

- `is_straight` (~line 822) + `place_rep` (~line 830): moved verbatim to just before the compiler block (pure relocation; Task 1 suite proves null). Afterwards used by the compiler (deterministic boosters) and the booster pass (unchanged).
- Compiler block: inserted between the task-order sort (~line 694) and `placed = set(wires)` (~line 695). Order inside: claim lanes → stamp trunks + boost → stamp E-W + bridges + boost → swap stub tasks. Placing it before the `placed` snapshot is what makes lanes unrippable (rip guards keep their `c not in placed` checks — DO NOT TOUCH lines ~762/768/782/794).
- Bridge sort key (~line 720, prefers non-placed victims): DO NOT TOUCH. Bridge cap (~line 704, `>= 24`): DO NOT TOUCH unless Task 5 measures exhaustion.
- Task-1 order block (~lines 684-694, `_ins/_dist/_far/_names/_oi`): DO NOT TOUCH — the compiler consumes `_names` and gates keep their sorted order.

---

### Task 1: Lane claims + N-S trunks + deterministic boosters

**Files:**
- Modify: `D:\redstone-mini\layout.py` (move `is_straight`+`place_rep`; insert lane claim + trunk stamp + `_boost` before `placed = set(wires)`)
- Test: `scratch/probe_trunks.py` (new)

**Interfaces:**
- Consumes: `_names` (input group order), `pos` (bank feeds), `solid`, `wires`, `stamp_wire`, `ring`/`own` (unused here), `W`, `D`, `repeaters`, `random` (not needed — geometry is order-independent).
- Produces: `_laneZ` (input net → E-W lane row), stamped N-S trunk wire per input + `("repeater", net)` solids every ≤6 run-cells (Task 2 bridges over trunks; Task 3 stubs start from E-W wire).

- [ ] **Step 1: Write the trunk probe**

```python
# scratch/probe_trunks.py
import os, sys, json
sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe
from layout import layout
name = sys.argv[1] if len(sys.argv) > 1 else "micro1"
r = parse_recipe(open(os.path.join(r"D:\redstone-mini", name + ".txt")).read())
path = r"C:\Users\LOQ\AppData\Local\Temp\opencode\lane_state.json"
os.environ["REDSTONE_DEBUG"] = path
try:
    layout(r, seed=None, grow=0)
    print("layout routed")
except RuntimeError as e:
    print("layout:", str(e)[:80])
doc = json.load(open(path))
solid = {tuple(map(int, k.split(","))): v for k, v in doc["solid"].items()}
wires = {}
for k, v in doc["wires"].items():
    x, y, z = map(int, k.split(","))
    wires[(x, y, z)] = v
nlev = sum(1 for (x, z), (kind, net) in solid.items() if kind == "lever" and net in r["inputs"])
n = 0
for (x, z), (kind, net) in sorted(solid.items()):
    if kind != "lever" or net not in r["inputs"]:
        continue
    tx, bz = x + 1, z
    assert wires.get((tx, 1, bz)) == net, (net, "feed missing")
    col, zz = [], bz - 1
    while wires.get((tx, 1, zz)) == net or solid.get((tx, zz)) == ("repeater", net):
        col.append(zz)
        zz -= 1
    reps = sorted((zz for zz in col if solid.get((tx, zz)) == ("repeater", net)), reverse=True)
    assert len(col) >= 10, (net, "trunk too short", len(col))
    assert len(reps) >= 1, (net, "no repeater on trunk")
    gaps = [bz - reps[0]] + [a - b for a, b in zip(reps, reps[1:])]
    assert all(g <= 14 for g in gaps), (net, "booster gap", gaps)
    n += 1
assert n == nlev, (n, nlev)
print(f"trunks ok: {n}/{nlev} inputs standing, boosted")
```

- [ ] **Step 2: Run probe to verify it fails (no trunks; red debris has no repeaters)**

Run: `python scratch/probe_trunks.py micro1` from `D:\redstone-mini`
Expected: FAIL — `AssertionError` (`trunk too short` on star debris, or `no repeater on trunk`: repeaters only stamp on success, and this layout reds). Record the message.

- [ ] **Step 3a: Move is_straight + place_rep above the compiler site (pure move)**

Cut `D:\redstone-mini\layout.py:822-845` exactly (from `def is_straight(path, i):` through `repeaters[(x1, z1)] = (net, facing)`, inclusive, including the blank line between the two defs) and paste it immediately before the `placed = set(wires)` line (~695), i.e. after the task-order sort. No other change to those 24 lines. (Why: the compiler calls `place_rep` but executes before the old def site — late binding fails. Moving shared defs earlier is behavior-null.)

- [ ] **Step 3b: Insert lane claims + trunk stamp + deterministic boost**

Insert between the moved defs and `placed = set(wires)`:

```python
    # ponytail: deterministic input lanes (spec 2026-09-26-deterministic-
    # input-lanes-design). Claim one free E-W lane per input, stamp N-S
    # trunks straight (no search) in free field, boost deterministically.
    # E-W + stubs follow in later tasks. Lanes land in `placed` via the
    # snapshot below (unrippable: gates detour tips or bridge dust).
    # Ceiling: lanes consume free field + bridge budget (Task 5 measures).
    def _boost(_cells, _net):
        # forward cover every 6 from the source end (bridge-dust spots
        # skipped: worst gap 11, endpoint level >= 4). Uniform spacing covers
        # like the booster pass on straight runs.
        for _i in range(6, len(_cells) - 1, 6):
            if _cells[_i][1] != 1:
                continue
            place_rep(_cells, _net, _i)
            solid[(_cells[_i][0], _cells[_i][2])] = ("repeater", _net)
    _laneZ, _usedZ = {}, set()
    for _net in _names:
        _lz = None
        for _z in range(D - 3, max(D - 43, -1), -1):
            if _z in _usedZ:
                continue
            if all((x, _z) not in solid and (x, 1, _z) not in wires for x in range(2, W - 2)):
                _lz = _z
                break
        if _lz is None:
            raise RuntimeError(f"no free lane for {_net} (field full, widen W)")
        _laneZ[_net] = _lz
        _usedZ.add(_lz)
    for _net in _names:
        _tx, _bz = pos[_net]
        _trunk = [(_tx, 1, _z) for _z in range(_bz - 1, _laneZ[_net] - 1, -1)]
        stamp_wire(_trunk, _net)
        _boost(_trunk, _net)
```

Notes for the implementer: `_names` holds only used inputs (built from `recipe["inputs"] filtered by `_ins`), so `pos[_net]` always exists (bank stamps every used input — KeyError here is loud-by-design, never guard it). `stamp_wire` raises on solid/foreign-wire/rings (lateral collision → loud, exactly right). `_boost` places repeaters south→north travel order, so facings point at the loads. The `_boost` solid entries make compiler repeaters visible to the dump probe, the router (walls for later tasks), and the lamp placer (dodges solid) — mirroring the OR-diode solid pattern, not the post-routing boosters (nothing routes after those).

- [ ] **Step 4: Run probe + suite (move must be null, trunks must stand)**

Run: `python scratch/probe_trunks.py micro1` from `D:\redstone-mini`
Expected: `trunks ok: 4/4 inputs standing, boosted` (the first `layout: ...` line may still report red routing — Task 3 flips routing; this task only proves trunks stand with boosters).

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: all `ok` lines (the def move + trunk stamps must not disturb small builds; wire counts may shift — green is the bar).
DEVIATION (measured 2026-09-26): suite reds here by design until Task 3 — unrippable trunks block the not-yet-removed star tasks on small builds too (4-gate `b` fails). The geometry probe above is this task's binding gate; suite-green moves to Task 3 (stub swap removes the star tasks). Do not chase suite reds in this task.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "input lanes: free-lane claims + boosted N-S trunks"
```

---

### Task 2: E-W transits + deterministic bridges

**Files:**
- Modify: `D:\redstone-mini\layout.py` (append E-W assembly after the trunk loop, same compiler block)
- Test: `scratch/probe_ew.py` (new)

**Interfaces:**
- Consumes: Task 1 (`_laneZ`, stamped trunks, `_boost`, `bridged` set, `bridge_free`, `bridge_stamp`, `bridge_plan`, `netspec`, `pos`).
- Produces: per-input E-W wire spanning trunk→farthest load-x with deterministic hops over foreign trunks; counted bridges (Task 5 watches the cap).

- [ ] **Step 1: Write the E-W probe**

```python
# scratch/probe_ew.py
import os, sys, json
sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe
from layout import layout
name = sys.argv[1] if len(sys.argv) > 1 else "micro1"
r = parse_recipe(open(os.path.join(r"D:\redstone-mini", name + ".txt")).read())
path = r"C:\Users\LOQ\AppData\Local\Temp\opencode\lane_state.json"
os.environ["REDSTONE_DEBUG"] = path
try:
    layout(r, seed=None, grow=0)
    print("layout routed")
except RuntimeError as e:
    print("layout:", str(e)[:80])
doc = json.load(open(path))
solid = {tuple(map(int, k.split(","))): v for k, v in doc["solid"].items()}
wires = {}
for k, v in doc["wires"].items():
    x, y, z = map(int, k.split(","))
    wires[(x, y, z)] = v
tx_of = {}
for (x, z), (kind, net) in solid.items():
    if kind == "lever" and net in r["inputs"]:
        tx_of[net] = x + 1
nload = 0
expect = 0
span_of, cross_of = {}, {}
for net, spec in doc["netspec"].items():
    if net not in r["inputs"] or not spec["loads"]:
        continue
    tx = tx_of[net]
    xs = sorted([lx for lx, lz in spec["loads"]] + [tx])
    # E-W wire must span the full [min, max] interval on some lane row,
    # except at deterministic hop victims (foreign trunk wire stays).
    cross = {cx for cx in tx_of.values() if cx != tx and xs[0] < cx < xs[-1]}
    cross_of[net] = cross
    expect += len(cross)
    for z in range(doc["D"]):
        run = [x for x in range(xs[0], xs[-1] + 1) if x not in cross
               and (wires.get((x, 1, z)) == net or solid.get((x, z)) == ("repeater", net))]
        if len(run) == (xs[-1] - xs[0] + 1) - len(cross):
            nload += len(spec["loads"])
            span_of[net] = z
            break
# E-W hops only: support pairs flanking exactly an expected victim column
# (last-resort bridges elsewhere are invisible to this count by construction).
bridges = sum(1 for net, z in span_of.items() for cx in cross_of[net]
              if solid.get((cx - 1, z)) == ("cobble", net) and solid.get((cx + 1, z)) == ("cobble", net))
nwant = sum(len(spec["loads"]) for net, spec in doc["netspec"].items() if net in r["inputs"] and spec["loads"])
assert nload == nwant, (nload, nwant)
assert bridges == expect, (bridges, expect)
print(f"ew ok: {nload}/{nwant} load columns spanned, {bridges} deterministic hops")
```

- [ ] **Step 2: Run probe to verify it fails (no E-W spans yet)**

Run: `python scratch/probe_ew.py micro1` from `D:\redstone-mini`
Expected: FAIL — `AssertionError` with `(0, 8)`-style counts (star debris never spans full intervals on one row).

- [ ] **Step 3a: Move guard + bridged earlier (null move)**

Move the guard + bridge-budget construction earlier (pure move — the compiler calls `bridge_free`, which needs `guard`, but executes before the old def site). Cut exactly:

```python
    guard = set()  # torch cells + their attach blocks: the only solids a
    for x, y, z, bid in blocks:  # routed wire must never hug (oscillators).
        if "wall_torch" in bid:  # lever/lamp coupling settles merely wrong
            guard.add((x, z))  # (no loop possible); sim catches it instead.
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, z + dz))
```

plus `bridged = set()  # (fx, fz, axis) already hopped; never retry`, and paste both immediately before the compiler block (after the task-order sort). Leave `fails = {}` and `def try_bridge` where they are.

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: all green (null-move proof).

- [ ] **Step 3b: Append E-W assembly + deterministic bridges + boost**

Append the E-W assembly after the trunk loop (same compiler block, before `placed = set(wires)`). Handle each side independently (west loads span `[min, tx]`, east loads `[tx, max]`; loads exactly at `tx` need no transit, their stub drives from the trunk cell). Per side, stops ordered travel-outward from trunk:

```python
    _tx_of = {n: pos[n][0] for n in _names}
    for _net in _names:
        _tx, _bz = pos[_net]
        _lz = _laneZ[_net]
        _west = sorted([_lx for _lx, _ly in netspec[_net]["loads"] if _lx < _tx], reverse=True)
        _east = sorted([_lx for _lx, _ly in netspec[_net]["loads"] if _lx > _tx])
        for _stops in ([_tx] + _west, [_tx] + _east):
            if len(_stops) < 2:
                continue
            _run = [(_tx, 1, _lz)]
            _x = _tx
            _end = _stops[-1]
            _step = 1 if _end > _tx else -1
            _cross = sorted([_cx for _nx, _cx in _tx_of.items() if _nx != _net and min(_x, _end) < _cx < max(_x, _end)], reverse=(_step < 0))
            for _cx in _cross:
                if (_cx, _lz, "ew") not in bridged:
                    if len(bridged) >= 24:
                        raise RuntimeError(f"bridge budget exhausted on {_net} (raise cap, see Task 5)")
                    if not bridge_free(wires, solid, repeaters, guard, W, D, _cx, _lz, "ew", _net):
                        raise RuntimeError(f"no hop for {_net} over trunk {_cx} (lane blocked)")
                    bridge_stamp(blocks, solid, wires, rings, placed, _net, _cx, _lz, "ew")
                    bridged.add((_cx, _lz, "ew"))
                _feet = bridge_plan(_cx, _lz, "ew")[0]
                _fa, _fb = sorted(_feet, key=lambda _f: abs(_f[0] - _x))
                _seg = [(_xx, 1, _lz) for _xx in range(_x, _fa[0], _step)] + [(_fa[0], 1, _fa[2])]
                stamp_wire(_seg, _net)
                _dusts = sorted(bridge_plan(_cx, _lz, "ew")[2], key=lambda _c: _step * _c[0])
                _run = _run + _seg[1:] + _dusts
                _x = _fb[0]
            # Feet can overshoot the span end (victim within 2 of the farthest
            # load): extend past the cursor so the tail joint is always wired
            # (an unwired single-cell tail would orphan the stub driver).
            _lim = _end
            if _step * (_x - _end) > 0:
                _lim = _x + 3 * _step
            elif any(abs(_cx - _end) <= 2 for _cx in _cross):
                _lim = _end + 3 * _step
            if not (0 <= _lim < W):
                raise RuntimeError(f"transit overruns field for {_net}")
            _tail = [(_xx, 1, _lz) for _xx in range(_x, _lim, _step)] + [(_lim, 1, _lz)]
            stamp_wire(_tail, _net)
            _run = _run + _tail[1:] if _run[-1] == _tail[0] else _run + _tail
            _boost(_run, _net)
```

Contract notes: `_feet` = `bridge_plan(...)[0]`, `_fa` = nearer foot. Segments include both endpoints (stamp verifies each cell — loud on foreign solid/wire/rings). Dusts travel-ordered by `_step`. Runs concatenate without duplicating joints. `_boost` covers the run (y≠1 dust spots skipped inside). `guard` is the moved-real one from Step 3a (no weakening).

- [ ] **Step 4: Run probe + suite**

Run: `python scratch/probe_ew.py micro1` from `D:\redstone-mini`
Expected: `ew ok: 8/8 load columns spanned, N deterministic hops` (N = computed crossings; the first `layout: ...` line may still report red — stubs land in Task 3).

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` — expect red until Task 3 (same star-vs-trunk coexistence as Task 1; suite-green binds at Task 3, not here — do not chase it).

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "input lanes: E-W transits with deterministic trunk hops"
```

---

### Task 3: Stub swap (gates route first) + micro1 green

**Files:**
- Modify: `D:\redstone-mini\layout.py` (filter input star tasks, append stub tasks after compiler)
- Test: `scratch/probe_spine.py` (exists: verify + one-lever assert + metrics)

**Interfaces:**
- Consumes: Tasks 1-2 (`_laneZ`, stamped lanes+bridges+repeaters, `_ins`); `tasks` (sorted, star tasks for inputs still present).
- Produces: `tasks` = gates (sorted order kept) + stub tasks `(drop, load, net)` with drop = `(loadx, laneZ)` holding net wire (guarded loud).

- [ ] **Step 1: Run probe to record the red baseline**

Run: `python scratch/probe_spine.py micro1` from `D:\redstone-mini`
Expected: FAIL — `RuntimeError` (star tasks still route: lanes stand unused beside sealing marathons). Record the message.

- [ ] **Step 2: Swap star tasks for stub tasks**

After the E-W assembly (still inside the compiler block, before `placed = set(wires)`), append:

```python
    _stubs = []
    for _net in _names:
        _lz = _laneZ[_net]
        for _lx, _ly in netspec[_net]["loads"]:
            if wires.get((_lx, 1, _lz)) != _net:
                raise RuntimeError(f"transit never arrived for {_net} at {(_lx, _lz)}")
            _stubs.append(((_lx, _lz), (_lx, _ly), _net))
    tasks = [t for t in tasks if t[2] not in _ins] + _stubs
```

(Gates keep their Task-1 sorted order; stubs route after gates. Contingency, only if stubs seal on micro1 with gates packed: swap to `_stubs + [t for t in ...]` so drops claim row cells first — one-line change, separate commit, measured.)

- [ ] **Step 3: Run probe (micro1 must flip green)**

Run: `python scratch/probe_spine.py micro1` from `D:\redstone-mini`
Expected: `micro1 OK blocks=... size=... one-lever-everywhere t=...s`. (Probe name is spine-era; it asserts verify + exactly-one-lever-per-used-input — exactly this spec's bar. Do not rename it.) On red: classify via `python scratch/probe_trunks.py micro1` + `python scratch/probe_ew.py micro1` (lanes intact?) then dump window on the failing stub — stop, report, no stacking.

- [ ] **Step 4: Commit**

```bash
git add layout.py
git commit -m "input lanes: stub tasks replace star tasks (gates first)"
```

---

### Task 4: alu1 + suite re-green

**Files:**
- Modify: none (verification only)
- Test: generic probe + full suite + corridor... (no corridors in this design — lane probes)

**Interfaces:**
- Consumes: Task 3's micro1 green.
- Produces: banded-build proof (alu1 stacks 10 gates in band 2 — lane + tail stress) + suite confirmation.

- [ ] **Step 1: Run alu1 (foreground — small file, fails fast)**

Run: `python scratch/probe_spine.py alu1` from `D:\redstone-mini`
Expected: `alu1 OK ... one-lever-everywhere t=...s`. On red: trunk probe + ew probe first (lane geometry?), then dump window — stop on transit reds.

- [ ] **Step 2: Re-run everything small**

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py && python scratch/probe_panel.py && python scratch/probe_trunks.py micro1 && python scratch/probe_ew.py micro1` from `D:\redstone-mini`
Expected: all green (lanes hold under the full field; record serve demo + fanout counts — green is the bar).

- [ ] **Step 3: Commit the numbers**

```bash
git add handoff.md
git commit -m "input lanes: alu1 green (NNN blocks), suite holds"
```

(Replace NNN with the measured alu1 block count.)

---

### Task 5: Dense acceptance (alu4/cpu4/ctrl_decode)

**Files:**
- Modify: none unless the cap trigger fires (then `layout.py:704`, separate commit)
- Test: background jobs + dump queries + metrics

**Interfaces:**
- Consumes: Tasks 1-4 (green micro1/alu1/suite).
- Produces: acceptance verdict or a classified, dump-proven red.

- [ ] **Step 1: Launch dense builds as background jobs**

From `D:\redstone-mini` (this machine's `Start-Process` lacks `-RedirectOutput`; the `cmd /c start /b` form detaches past shell exit):

```powershell
cmd /c "start /b python scratch/probe_spine.py alu4 > scratch/alu4_lane.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py cpu4 > scratch/cpu4_lane.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py ctrl_decode > scratch/ctrl_lane.log 2>&1"
```

Poll (never block foreground on dense builds):

```powershell
Get-Content scratch/alu4_lane.log,scratch/cpu4_lane.log,scratch/ctrl_lane.log -ErrorAction SilentlyContinue
```

Expected: each log ends with `<name> OK blocks=... one-lever-everywhere t=...s`.

- [ ] **Step 2 (only on red): classify lane vs stub vs cap**

Run trunk + ew probes for the failing build (`python scratch/probe_trunks.py <build>`, `python scratch/probe_ew.py <build>`):
- Lanes broken (no free lane / trunk blocked / hop refused): placement reality in this field — report net + dump window, stop, no patch.
- Lanes intact, stub unroutable: existing search failed on a short hop — dump window, stop, no stacking.
- Everything stamped, bridges at cap: save this exact helper as `scratch/probe_bridges.py` (it counts E-W hop pairs per net — support flanks with a wired victim middle — plus N-S triples, so last-resort and deterministic hops are both visible), run it against a fresh dump (`python debug.py <build>.txt <seed> 0` writes the planning frame even on failure):

```python
# scratch/probe_bridges.py — argv: dump path (default: lane_state.json dump)
import sys, json
from collections import Counter
path = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\LOQ\AppData\Local\Temp\opencode\lane_state.json"
doc = json.load(open(path))
solid = {tuple(map(int, k.split(","))): v for k, v in doc["solid"].items()}
wires = {}
for k, v in doc["wires"].items():
    x, y, z = map(int, k.split(","))
    wires[(x, y, z)] = v
per, total = Counter(), 0
for (x, z), (kind, net) in sorted(solid.items()):
    if kind != "cobble":
        continue
    # E-W hop: cobble flanks two apart with foreign wire between (the victim).
    if solid.get((x + 2, z)) == ("cobble", net):
        w = wires.get((x + 1, 1, z))
        if w is not None and w != net:
            per[(net, "ew")] += 1
            total += 1
    # N-S hop heuristic: three consecutive cobbles (matches stamped rows).
    if (x, z - 1) in solid and (x, z + 1) in solid and solid[(x, z - 1)][0] == "cobble" and solid[(x, z + 1)][0] == "cobble":
        per[(net, "ns")] += 1
        total += 1
print(dict(per), "total~", total)
```

Trigger (and only trigger): the failing build's total sits at 24 with everything else stamped → replace `len(bridged) >= 24` with `len(bridged) >= 96`, update that ponytail comment's ceiling line, re-run that build, commit separately:

```bash
git add layout.py
git commit -m "input lanes: bridge cap 24->96 (measured exhaustion on <build>)"
```

- [ ] **Step 3: Record metrics + acceptance commit**

Append per-build results (blocks, size, wall time, bridges used) to `handoff.md`, extend `PONYTAIL-DEBT.md` with the lane-compiler marker row (ceiling + upgrade, matching existing rows), then:

```bash
git add handoff.md PONYTAIL-DEBT.md
git commit -m "input lanes: acceptance metrics (<builds> green, one lever everywhere)"
```

Acceptance = micro1, alu1, alu4, cpu4, ctrl_decode verify green + suite green + lever asserts green. Anything else is red: no merge, diagnose with dumps.
