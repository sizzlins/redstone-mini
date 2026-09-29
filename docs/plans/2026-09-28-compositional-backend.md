# Compositional backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic compositional generator (`compose.py`) beside the maze router, reusing hoisted tile builders, shared netspec/checkers/taps, and the unchanged sim gate, with compose-first/fallback-second ladder integration.

**Architecture:** Three phases, each independently committable: (A) extract shared tail, netspec, static checkers, and tile layer out of `layout()` with zero behavior change (hash-gated moves only); (B) new `compose.py` placing tiles on padded bands and wiring L-wire/bridge-over through the same guards; (C) `layout_retry` tries compose first, sim-gates it, falls back to the maze router untouched. The composer produces the exact `(out, (W,D), io)` triple `sim_verify` already consumes.

**Tech Stack:** Python 3 (repo standard, no new dependencies); in-module `__main__` canaries per repo convention (no `tests/` dir exists — follow `layout.py:2026` pattern, do not invent a test framework).

## Global Constraints

- The sim's vanilla contract is frozen: no changes to `sim.py` physics (`dust_lvl`, `_run_vec`, `sim_verify` semantics).
- Suite stays green after every task: `python recipe.py`, `python sim.py`, `python layout.py`, `python serve.py --check` (all from `D:\redstone-mini`).
- 4/4 small-build hashes (`example_and`, `example_2gates`, `latch_sr`, `example_xor`) stay byte-identical through Phase A (record before/after inside each task; compare counts, never absolute values).
- No `.txt` recipe changes, no `export.py` changes.
- Block count is reported, never optimized.
- `cpu4.txt` is FROZEN: never run it, never read its dumps, until the final validation task. Violation fails the task.
- The composer is deterministic: no `seed`, no `random`, no dict/set iteration anywhere in `compose.py`.
- Import direction (no cycles): `tiles` imports `core` only; `compose` imports `tiles`, `layout` (shared readers), `recipe`; `layout` imports `tiles`; `sim` imports `compose`, `layout`.

---

## File structure

- `layout.py` — loses its tail (`finish_assembly`, lines 1985-2023), its netspec builder (1346-1383), its static checkers (SHORT 1903-1925, OPEN 1926-1982), and its stamping layer (closures 712-759, 918-972 + per-op placers 1060-1338); keeps routing/search/cover/lamps-strategy/rip-up. Net deletion, only moves.
- `tiles.py` (new) — one responsibility: tile geometry + stamping on an explicit state object. Owns `Ctx`, `own`, `ring`, `stamp_wire`, `stamp_cobble`, `stamp_torch`, `stamp_and`, `place_or`, `place_and`, `place_not`, `place_latch`, `place_xor`, `footprint`, `tap_lamps`. Bodies byte-identical to today's closures except shared state via `ctx.`; placement-strategy helpers arrive via a `place` namespace (duck-type below), never maze internals.
- `compose.py` (new) — one responsibility: deterministic placement + wiring producing `(out, (W,D), io)`. Owns `lwire`, `_topo`, `_depths`, `_place_gate`, `compose`.
- `sim.py` — `layout_retry` gains compose-first/fallback-second (≈15 lines). No physics touched.

The `place` duck-type contract (both backends satisfy it; `tiles.place_*` only touch these):
`place.spot_free(op, ox, gz, i) -> bool`, `place.gridrows(ox, gz)` yields `(ox, gz)` candidates, `place.snap()` / `place.restore(s)` (composer passes no-ops: deterministic placement pre-checks occupancy, any stamp raise is a loud abort).

---

### Task 1: Extract `finish_assembly` tail

**Files:**
- Modify: `D:\redstone-mini\layout.py:1985-2023` (move to module level as `finish_assembly`, `layout()` calls it)

**Interfaces:**
- Consumes: nothing new.
- Produces: `finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos) -> (out, (W, D), io)` where `out` is a sorted list of `(x, y, z, bid)`, `(W, D)` ints, `io = {"levers": {(x,z): name}, "lamps": {(x,z): name}, "nets": {(x,y,z): net}}`. Tasks 6 consumes this exact signature.

- [ ] **Step 1: Record the before-hashes**

Run from `D:\redstone-mini`: `python -c "from layout import layout; from recipe import parse_recipe; [print(f, len(layout(parse_recipe(open(f).read()))[0])) for f in ['example_and.txt','example_2gates.txt','latch_sr.txt','example_xor.txt']]"`.
Expected: PASS, 4 block counts printed (write them down; comparison baseline for every Phase A task).

- [ ] **Step 2: Run suite green before the move**

Run from `D:\redstone-mini`: `python recipe.py`, `python sim.py`, `python layout.py`.
Expected: all PASS.

- [ ] **Step 3: Move the tail to module level**

Insert before `def layout(...)` (line 650) the body copied verbatim from lines 1985-2023, dedented one level, under `def finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos):`. Replace lines 1985-2023 inside `layout()` with `return finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)`. `_loop_rep` and `wire_bid` are already module-level (lines 262, 67) — no import changes.

- [ ] **Step 4: Verify byte-identical output**

Re-run the Step 1 command.
Expected: identical 4 counts. Then `python recipe.py`, `python sim.py`, `python layout.py`.
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "refactor: extract finish_assembly tail (no behavior change)"
```

---

### Task 2: Extract `build_netspec`

**Files:**
- Modify: `D:\redstone-mini\layout.py:1346-1383` (move to module level as `build_netspec`, `layout()` calls it)

**Interfaces:**
- Consumes: `recs` entries in the exact shapes `layout()` appends: `("AND", o, a, (pa, pb, po))`, `("NOT", o, a, (bx, bz))`, `("LATCH"|"XOR", o, a, (pa, pb, po))`, `("OR", o, a, (j, reps))` with `reps = [(r, b)]`, `("OUT", name, [name], fx)` — plus `pos` dict `{net: (x, z)}`.
- Produces: `build_netspec(recs, recipe, pos) -> netspec` where `netspec = {net: {'drv': (x, z) or None, 'loads': [(x, z)]}}`, `"0"` never driven, dead nets pruned, inputs defaulted — semantics byte-identical to lines 1346-1383. Task 6 consumes this exact signature.

- [ ] **Step 1: Verify green before the move**

Run from `D:\redstone-mini`: `python layout.py`.
Expected: PASS.

- [ ] **Step 2: Move lines 1340-1383 to module level**

Insert before `def layout(...)` exactly this (body verbatim from lines 1346-1383, `pos` and `recipe` become parameters, `_load` stays nested):

```python
def build_netspec(recs, recipe, pos):
    netspec = {}
    def _load(net, cell):
        if net == "0":
            return  # dark stubs read 0; nothing is stamped
        e = netspec.setdefault(net, {'drv': None, 'loads': []})
        e['loads'].append(cell)
    for op, o, a, cell in recs:
        if op == "AND":
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': []})
            _load(a[0], pa); _load(a[1], pb)
        elif op == "NOT":
            bx, bz = cell
            netspec.setdefault(o, {'drv': (bx + 2, bz), 'loads': []})
            _load(a[0], (bx - 2, bz))
        elif op in ("LATCH", "XOR"):
            pa, pb, po = cell
            netspec.setdefault(o, {'drv': po, 'loads': []})
            _load(a[0], pa); _load(a[1], pb)
            if op == "XOR":
                # REP1 back (ox,gz-2) is a routed load: pa = (ox+3,gz).
                _load(a[1], (pa[0] - 3, pa[1] - 2))
        elif op == "OR":
            j, reps = cell
            netspec.setdefault(o, {'drv': j, 'loads': []})
            for sig, (rr, bb) in zip(a, reps):
                _load(sig, bb)
        elif op == "OUT":
            pass  # lamp taps the driver wire; no stub
        else:
            raise RuntimeError(f"bus: unsupported {op}")
    for name in recipe["inputs"]:
        netspec.setdefault(name, {'drv': None, 'loads': []})
    if "1" in netspec:
        netspec["1"]['drv'] = pos["1"]
    for net in [n for n, s in netspec.items()
                if not s['loads'] and n not in recipe["outputs"]]:
        del netspec[net]
    return netspec
```

Replace lines 1340-1383 inside `layout()` with `netspec = build_netspec(recs, recipe, pos)`, keeping the `# bus:` comment above the call.

- [ ] **Step 3: Verify identical builds + placement still passes**

Run from `D:\redstone-mini`: `python layout.py`, `python sim.py`, `python recipe.py`.
Expected: all PASS. Then `REDSTONE_SEARCH_CAP=700 python -c "from layout import layout; from recipe import parse_recipe; layout(parse_recipe(open('alu1.txt').read()))"`.
Expected: `RuntimeError` mentioning `no route` (routing wall, NOT `blocked`/`out of bounds` — placement must still pass).

- [ ] **Step 4: Commit**

```bash
git add layout.py
git commit -m "refactor: extract build_netspec (no behavior change)"
```

---

### Task 3: Extract static checkers (SHORT + OPEN)

**Files:**
- Modify: `D:\redstone-mini\layout.py:1903-1982` (move to module level as `check_shorts` + `check_opens`, `layout()` calls both)

**Interfaces:**
- Consumes: `wires {(x,y,z): net}`, `junctions {(x,z): set}`, `blocks [(x,y,z,bid)]`, plus `repeaters`, `solid`, `pos` for the OPEN checker. Pure readers — no stamping, no state mutation.
- Produces: `check_shorts(wires, junctions, blocks)` raising `RuntimeError("SHORT..."/"SHORT3D...")` with today's exact strings (body verbatim lines 1903-1925, `cob3` computed inside from `blocks`); `check_opens(wires, junctions, repeaters, solid, pos, blocks)` raising `RuntimeError("OPEN ...")` (body verbatim 1926-1982, `cob` computed inside). Task 6 calls both after wiring, before `finish_assembly`.

- [ ] **Step 1: Verify green before the move**

Run from `D:\redstone-mini`: `python layout.py`.
Expected: PASS.

- [ ] **Step 2: Move both checkers to module level**

Insert before `def layout(...)`: `check_shorts` = lines 1903-1925 verbatim under the new signature (keep the three-line `cob3` computation and both `for` loops, dedented); `check_opens` = lines 1926-1982 verbatim under its signature (keep `seed_states`, flood, `dead` computation). Replace the originals inside `layout()` with:

```python
    check_shorts(wires, junctions, blocks)
    check_opens(wires, junctions, repeaters, solid, pos, blocks)
```

keeping the `# checker:` comments above the calls.

- [ ] **Step 3: Verify identical behavior including loud failures**

Run from `D:\redstone-mini`: `python layout.py`, `python sim.py`, `python recipe.py`.
Expected: all PASS. Then confirm the checkers still fire (they must remain loud, not advisory): `python -c "from layout import check_shorts; check_shorts({(0,1,0): 'a', (1,1,0): 'b'}, {}, [])"`.
Expected: `RuntimeError: SHORT: a touches b at (0, 1, 0)->(1, 1, 0)` (exact string proves the move preserved the guard, not just the green path).

- [ ] **Step 4: Commit**

```bash
git add layout.py
git commit -m "refactor: extract SHORT/OPEN checkers (no behavior change)"
```

---

### Task 4: Hoist tile layer to `tiles.py` (+ AND reserve tightening)

**Files:**
- Create: `D:\redstone-mini\tiles.py`
- Modify: `D:\redstone-mini\layout.py` (closures 712-759, 918-972 and per-op placers 1060-1338 delegate to `tiles.py`; lamp taps 1877-1901 move as `tap_lamps`)

**Interfaces:**
- Consumes: `core.DIRS`; caller-owned state (no new types beyond `types.SimpleNamespace`).
- Produces:
  - `new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs) -> Ctx` holding references to those same objects (mutations visible to caller, zero copy).
  - `own(*nets)`, `ring(ctx, x, z, nets)`, `stamp_wire(ctx, path, net, ends=())`, `stamp_cobble(ctx, x, z, o)`, `stamp_torch(ctx, x, z, o)`, `stamp_and(ctx, ox, gz, A, B, O) -> (pa, pb, po)` — bodies byte-identical to `layout.py:712-759, 918-972` with shared state via `ctx.`.
  - `place_or(ctx, place, g, ox, gz, pos, W, D)`, `place_and`, `place_not`, `place_latch`, `place_xor` — per-op bodies moved verbatim from `layout.py:1060-1338` (AND = the 1109-1138 candidate loop calling `stamp_and`; the rest keep their gridrows/spot_free/snap/restore calls, now via `place.*`). Each appends `recs` in today's exact shapes and sets `pos[o]` exactly as today.
  - `footprint(op, ox, gz)` verbatim from `layout.py:984-993`.
  - `tap_lamps(ctx, place_unused, recipe, pos, W, D)` — body verbatim `layout.py:1877-1901` (needs `stamp_wire`, `ring`, `own`, `DIRS` — all local to `tiles.py` after the hoist); appends `("OUT", ...)` recs exactly as today. Takes no `place` (fixed E/S/N/W try-order, no grid fallback).

- [ ] **Step 1: Record before-hashes and green suite**

Run from `D:\redstone-mini`: `python layout.py`, `python sim.py`, `python recipe.py`.
Expected: all PASS. Record the 4 small-build block counts with the Task 1 command.

- [ ] **Step 2: Create `tiles.py` with the stamping layer**

```python
"""Tiles: pure stamping builders on an explicit state object (hoisted from layout())."""
from types import SimpleNamespace
from core import DIRS


def new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs):
    return SimpleNamespace(blocks=blocks, solid=solid, rings=rings, wires=wires,
                           junctions=junctions, repeaters=repeaters, pos=pos, recs=recs)


def own(*nets):
    return set(nets)


def ring(ctx, x, z, nets):
    ctx.rings.setdefault((x, z), set()).update(nets)


def stamp_wire(ctx, path, net, ends=()):
    # body byte-identical to layout.py:718-759 with ctx. prefixes
    ...
```

Copy each body verbatim from the cited lines, prefixing shared state with `ctx.`. Do NOT change logic, comments, or error strings.

- [ ] **Step 3: Delegate from `layout()`**

After the state-dict init (today line 707) add `import tiles as _tiles` (module top is cleaner: put `from tiles import ...` beside other imports — either, one choice, keep it) and `ctx = _tiles.new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs)`. Replace each closure definition with a same-named delegation (e.g. `def stamp_wire(path, net, ends=()): return _tiles.stamp_wire(ctx, path, net, ends)`). Keep all call sites untouched. Replace the per-op inline bodies with `place_*` calls, binding a maze `place` namespace from locals: `place = SimpleNamespace(spot_free=spot_free, gridrows=gridrows, snap=_snap, restore=_restore)`.

- [ ] **Step 4: Verify byte-identical builds**

Re-run the Task 1 block-count command.
Expected: identical 4 counts. Then `python layout.py`, `python sim.py`, `python recipe.py`, `python serve.py --check`.
Expected: all PASS.

- [ ] **Step 5: Tighten the AND reserve (approach 1 rides along)**

In `tiles.footprint`, change only the AND box from `range(ox - 2, ox + 9) × range(gz - 1, gz + 8)` (11×9) to `range(ox - 2, ox + 7) × range(gz, gz + 7)` (9×7: the extents `spot_free` already enforces at `layout.py:1008-1009` plus the stamped cells at `stamp_and`, which max out at `ox+6`/`gz+4` plus funnels). Safety reasoning (why hashes must hold): tightening only flips `spot_free` False→True, candidates are tried in fixed order, so any previously accepted slot is still accepted first — placement can only stay identical or succeed where it failed. Verify: re-run the block-count command (expect identical) and full suite (expect PASS). If any hash moves: revert ONLY this step (restore the 11×9 line), keep the hoist, record in handoff — kill-switch (a) covers the hoist, this step has its own revert.

- [ ] **Step 6: Commit**

```bash
git add tiles.py layout.py
git commit -m "refactor: hoist tile layer to tiles.py; tighten AND reserve 11x9->9x7"
```

(If Step 5 reverted: message `refactor: hoist tile layer to tiles.py (reserve tightening reverted, see handoff)`.)

---

### Task 5: Composer wiring primitive `lwire`

**Files:**
- Create: `D:\redstone-mini\compose.py` (with `lwire` + `__main__` canary)
- Test: in-module `__main__` canary per repo convention — no new test framework.

**Interfaces:**
- Consumes: `tiles.new_ctx`, `tiles.stamp_wire`, `layout._support` (pillar-legality oracle, `layout.py:81-104`), `core.DIRS`.
- Produces: `lwire(ctx, sup, guard, a, b, net)` where `a`, `b` are `(x, z)` flat cells, `sup`/`guard` are composer-owned `{}`/`set()`. Stamps a Z-then-X path at y=1; bridges OVER sealing cells through `_support`-validated cobble pillars; plants repeaters on straight flat triples every 14 cells (the `_cover_triples` collinearity rule — twisty/climbing stretches stay unboosted and fail sim loudly if too long). Raises `RuntimeError(f"compose: no ground for {net}: {a} -> {b}")` on infeasible pillars. Deterministic: fixed axis order, no search, no randomness.

- [ ] **Step 1: Write the failing canary**

Create `compose.py` with the imports plus:

```python
if __name__ == "__main__":
    from tiles import new_ctx, stamp_wire
    _blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs = [], {}, {}, {}, {}, {}, {}, []
    _ctx = new_ctx(_blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs)
    _sup, _guard = {}, set()
    # two nets must cross: A runs east, B must bridge over it.
    stamp_wire(_ctx, [(10, 1, 20), (11, 1, 20), (12, 1, 20), (13, 1, 20)], "A")
    lwire(_ctx, _sup, _guard, (11, 18), (11, 22), "B")
    assert _wires.get((11, 1, 20)) == "A", _wires
    assert any(y >= 2 for (x, y, z), n in _wires.items() if n == "B"), "B never left the ground"
    print("lwire ok: bridge-over crosses without touching")
```

Run: `python compose.py` from `D:\redstone-mini`.
Expected: FAIL with `NameError: name 'lwire' is not defined`.

- [ ] **Step 2: Implement `lwire` minimally**

```python
"""Compose: deterministic placement + wiring (no search, no seeds)."""
from core import DIRS
from tiles import stamp_wire
from layout import _support

_VEC = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def lwire(ctx, sup, guard, a, b, net):
    """Z-then-X path at y=1; bridge OVER sealing cells; repeaters every 14."""
    cells = []
    x, z = a
    while z != b[1]:
        z += 1 if b[1] > z else -1
        cells.append((x, 1, z))
    while x != b[0]:
        x += 1 if b[0] > x else -1
        cells.append((x, 1, z))
    done = []
    for (cx, cy, cz) in cells:
        try:
            stamp_wire(ctx, [(cx, cz)], net)
            done.append((cx, cy, cz))
        except RuntimeError:
            r = _support((cx, 2, cz), net, ctx.solid, ctx.wires, sup,
                         ctx.repeaters, guard)
            if r is False:
                raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
            # r is None (reusable cobble) or a fresh pillar cell: either way the
            # wire rides at y=2. finish_assembly emits wire bids from wires dict
            # alone, so routed cells append NOTHING to blocks here.
            if isinstance(r, tuple):
                sup[r] = net
                ctx.blocks.append((r[0], r[1], r[2], "minecraft:cobblestone"))
                ctx.solid[(r[0], r[2])] = ("cobble", net)
            ctx.wires[(cx, 2, cz)] = net
            done.append((cx, 2, cz))
    _plant_repeaters(ctx, done, net)
    return done


def _plant_repeaters(ctx, cells, net):
    for k in range(13, len(cells) - 1, 14):
        (px, py, pz), (cx, cy, cz), (nx, ny, nz) = cells[k - 1], cells[k], cells[k + 1]
        dx, dz = cx - px, cz - pz
        if (dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC and py == cy == ny == 1:
            del ctx.wires[(cx, cy, cz)]
            ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(dx, dz)])
```

Notes the implementer must honor: `stamp_wire` per single cell reuses the SHORT/adacency guards for free (a same-net continue is harmless — `wires.setdefault` keeps the label). `_support` may return `None` only when the pillar cell is reusable cobble of the same net or open ground at y=1 — but here the y=1 cell just raised (foreign wire/solid), so `None` with a foreign y=1 cell underneath means infeasible: treat `r is None and (cx, 1, cz) in ctx.wires and ctx.wires[(cx, 1, cz)] != net` as `raise RuntimeError(...)` (same message). Pillar cobble goes into `solid` so later composer tiles route around it, mirroring tile-cobble treatment. The canary's `guard` is empty (no torches yet at wire time in the canary); `compose` (Task 6) builds `guard` from stamped torches exactly like `layout.py:1419-1425` before wiring.

- [ ] **Step 3: Run canary to verify it passes**

Run: `python compose.py` from `D:\redstone-mini`.
Expected: PASS, prints `lwire ok: bridge-over crosses without touching`.

- [ ] **Step 4: Run full suite (no regressions — compose.py is additive)**

Run: `python recipe.py`, `python sim.py`, `python layout.py`.
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add compose.py
git commit -m "feat: compose lwire primitive (L-path, bridge-over, repeater every 14)"
```

---

### Task 6: `compose(recipe)` end to end

**Files:**
- Modify: `D:\redstone-mini\compose.py` (add `_topo`, `_depths`, `_place_gate`, `compose` + extend `__main__` canary)

**Interfaces:**
- Consumes: `expand_gates` from `recipe`; `tiles` builders + `tap_lamps` (Task 4); `build_netspec`, `check_shorts`, `check_opens`, `finish_assembly` from `layout` (Tasks 1-3); `lwire` (Task 5).
- Produces: `compose(recipe) -> (out, (W, D), io)` — the exact triple shape from Task 1. Raises `RuntimeError` loudly on any infeasible placement/wire (never partial builds).

- [ ] **Step 1: Extend the canary with a full-build check (fails first)**

Append to `compose.py.__main__` (after the lwire asserts):

```python
    from recipe import parse_recipe
    from sim import sim_verify
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    _out, _size, _io = compose(_r)
    sim_verify(_r, _out, _io, quiet=True)
    print("compose ok: AND verifies through the sim gate")
```

Run: `python compose.py` from `D:\redstone-mini`.
Expected: FAIL with `NameError: name 'compose' is not defined`.

- [ ] **Step 2: Implement `compose` minimally**

```python
from recipe import expand_gates
from tiles import new_ctx, footprint, tap_lamps
from layout import build_netspec, check_shorts, check_opens, finish_assembly


def _topo(gates):
    by_out, order = {}, []
    for i, g in enumerate(gates):
        by_out.setdefault(g["out"], i)
    deps = {i: {by_out[a] for a in g["args"] if a in by_out and by_out[a] != i}
            for i, g in enumerate(gates)}
    ready = sorted(i for i, d in deps.items() if not d)
    while ready:
        i = ready.pop(0)
        order.append(i)
        for j, d in deps.items():
            if i in d:
                d.discard(i)
                if not d and j not in order and j not in ready:
                    ready.append(j)
        ready.sort()
    if len(order) != len(gates):
        raise RuntimeError("compose: gate cycle")
    return [gates[i] for i in order]


def _depths(gates, inputs):
    ins, depth = set(inputs), {}
    for g in _topo(gates):
        if all(a in ins or a in ("0", "1") for a in g["args"]):
            depth[g["out"]] = 2
        else:
            depth[g["out"]] = 1 + max(depth[a] for a in g["args"] if a not in ins and a not in ("0", "1"))
    return depth


def compose(recipe):
    from types import SimpleNamespace
    from tiles import place_or, place_and, place_not, place_latch, place_xor, own, ring, stamp_wire
    gates = expand_gates(recipe["gates"], recipe["inputs"])
    blocks, solid, rings, wires, junctions, repeaters, pos, recs = [], {}, {}, {}, {}, {}, {}, []
    ctx = new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs)
    sup, guard = {}, set()
    ordered = _topo(gates)
    depth = _depths(gates, recipe["inputs"])
    # placement: topo bands in Z, padding from subtree depth; 4 X-lanes stride 30.
    gz_of, z = {}, 12
    for g in ordered:
        gz_of[g["out"]] = z
        z += 4 + depth[g["out"]] + 6
    used_fp = []
    def c_spot_free(op, ox, gz, i):
        fp = footprint(op, ox, gz)
        if any(not fp.isdisjoint(u) for u in used_fp):
            return False
        return all((x, z) not in solid and (x, 1, z) not in wires for x, z in fp)
    def c_gridrows(ox, gz):
        while True:
            yield ox, gz
            gz += 14
    c_place = SimpleNamespace(spot_free=c_spot_free, gridrows=c_gridrows,
                              snap=lambda: None, restore=lambda s: None)
    for i, g in enumerate(ordered):
        ox, gz = 6 + (i % 4) * 30, gz_of[g["out"]]
        for ox2, gz2 in c_gridrows(ox, gz):
            if not c_spot_free(g["op"], ox2, gz2, i):
                continue
            if g["op"] == "OR":
                place_or(ctx, c_place, g, ox2, gz2, pos, 10**6, 10**6)
            elif g["op"] == "AND":
                place_and(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "NOT":
                place_not(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "LATCH":
                place_latch(ctx, c_place, g, i, ox2, gz2, pos)
            elif g["op"] == "XOR":
                place_xor(ctx, c_place, g, i, ox2, gz2, pos)
            else:
                raise RuntimeError(f"compose: bad primitive {g['op']}")
            used_fp.append(footprint(g["op"], ox2, gz2))
            break
        else:
            raise RuntimeError(f"compose blocked for {g['out']}")
    # ties: exact layout.py:895-903 convention at fixed west sites (tiles live z>=12).
    if any(a in ("0", "1") for g in gates for a in g["args"]):
        stamp_wire(ctx, [(0, 3)], "0")
        pos["0"] = (0, 3)
        blocks.append((2, 1, 3, "minecraft:redstone_block"))
        solid[(2, 3)] = ("block", "1")
        for dx, dz in DIRS:
            ring(ctx, 2 + dx, 3 + dz, own("1"))
        stamp_wire(ctx, [(1, 3)], "1")
        pos["1"] = (1, 3)
    # inputs: one edge bus per input at pitch 5 on the west edge.
    for k, name in enumerate(recipe["inputs"]):
        lz = z + 6 + k * 5
        blocks.append((4, 1, lz, "minecraft:lever"))
        solid[(4, lz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(ctx, 4 + dx, lz + dz, own(name))
        stamp_wire(ctx, [(5, lz)], name)
        pos[name] = (5, lz)
    # guard from stamped torches, exactly like layout.py:1419-1425.
    for x, y, zz, bid in blocks:
        if "wall_torch" in bid:
            guard.add((x, zz))
            face = bid.split("facing=")[1].rstrip("]")
            dx, dz = TORCH_BACK[face]
            guard.add((x + dx, zz + dz))
    # lamps via the shared tap routine (same E/S/N/W order, same loud failure).
    tap_lamps(ctx, None, recipe, pos, 10**6, 10**6)
    netspec = build_netspec(recs, recipe, pos)
    for net in sorted(netspec):
        if net in ("0", "1"):
            continue
        drv = netspec[net]['drv'] or pos.get(net)
        for cell in sorted(netspec[net]['loads']):
            lwire(ctx, sup, guard, drv, cell, net)
    check_shorts(wires, junctions, blocks)
    check_opens(wires, junctions, repeaters, solid, pos, blocks)
    return finish_assembly(blocks, solid, wires, rings, junctions, repeaters, pos)
```

Notes the implementer must honor (binding constraints, not suggestions):
  - `DIRS` and `TORCH_BACK` come from `core` (`from core import DIRS, TORCH_BACK` at compose top).
  - `W, D = 10**6` for placers means "effectively unbounded, emptiness decides" — bounds checks inside `place_*`/`tap_lamps` stay live but never fire; `finish_assembly` shrink-wraps to content, so no size is baked in.
  - X-lane stride 30 clears the widest tile (LATCH spans ox-6..ox+7 = 14) plus wire pitch; Z street 6 + pad `4+depth` clears stacked footprints (tallest reserve 11). `used_fp` + `c_spot_free` make disjointness structural; emptiness covers pillars/ties/buses stamped earlier.
  - `sorted(netspec)` / `sorted(loads)` is the determinism lock — never iterate the raw dicts.
  - `tap_lamps` signature is `(ctx, place_unused, recipe, pos, W, D)` — if Task 4 defined it differently, reconcile Task 4's signature to this call (one definition, no adapters).
  - `_place_gate` was folded inline as the dispatch loop above (single call site — YAGNI says no separate function).

- [ ] **Step 3: Run canary to verify it passes**

Run: `python compose.py` from `D:\redstone-mini`.
Expected: PASS, prints `lwire ok...` and `compose ok: AND verifies through the sim gate`.

- [ ] **Step 4: Verify all four small builds through the composer**

Write `scratch/compose_check.py` (gitignored scratch, never committed):

```python
from compose import compose
from recipe import parse_recipe
from sim import sim_verify
for f in ['example_and.txt', 'example_2gates.txt', 'latch_sr.txt', 'example_xor.txt']:
    r = parse_recipe(open(f).read())
    out, size, io = compose(r)
    sim_verify(r, out, io, quiet=True)
    print(f, 'green', len(out), 'blocks')
```

Run: `python scratch/compose_check.py` from `D:\redstone-mini`.
Expected: all 4 print `green` (including `latch_sr` — the sequential proof upstream cannot match).

- [ ] **Step 5: Commit**

```bash
git add compose.py
git commit -m "feat: compose() end to end (bands, edge buses, lwire, sim-gated)"
```

---

### Task 7: Ladder integration (compose-first, maze fallback)

**Files:**
- Modify: `D:\redstone-mini\sim.py:layout_retry` (lines 26-64)

**Interfaces:**
- Consumes: `compose.compose` (Task 6), `sim_verify` (unchanged), `layout` (unchanged).
- Produces: same `layout_retry(recipe, tries, verify, grows)` signature and return shape; tries composer once per call before the existing sweep.

- [ ] **Step 1: Lock the integrated shape with a canary**

Find the existing `sim.py.__main__` block; append in its assert style:

```python
    _r = parse_recipe("IN a, b\nOUT y\ny = a AND b\n")
    _b, _, _, _st = layout_retry(_r, verify=True)
    assert _st is not None and len(_b) > 0
    print("ladder ok: compose-first returns a verified build")
```

(`parse_recipe` is already imported in `sim.py` — verify before duplicating the import.)
Run: `python sim.py` from `D:\redstone-mini`.
Expected: PASS (maze path greens it today; this locks shape, Step 3 proves preference).

- [ ] **Step 2: Integrate compose-first**

Add `from compose import compose` beside `from layout import layout, dust_points` at the top of `sim.py`. Replace lines 42-43 (`last = None` + `for _res in ...`) with:

```python
    last = None
    try:
        out = compose(recipe)
    except RuntimeError as e:
        last = e
    else:
        if not verify:
            return out + (None,)
        try:
            st, ticks = sim_verify(recipe, out[0], out[2], quiet=True, collect=True)
        except RuntimeError as e:
            e.blocks, e.size, e.io = out[:3]
            last = e
        else:
            return out + (st,)
    for _res in (False, True):
        ...  # existing sweep untouched below
```

Rules: composer raise OR sim refusal both fall through with `last` set — the maze sweep below is byte-untouched; no seed/grow reaches `compose`.

- [ ] **Step 3: Verify preference + fallback + suite**

Run from `D:\redstone-mini`:
  a. `python -c "import time; from sim import layout_retry; from recipe import parse_recipe; t=time.time(); layout_retry(parse_recipe(open('example_and.txt').read()), verify=True); print(f'{time.time()-t:.1f}s')"`.
  Expected: green fast (composer path hit first — compare against the pre-change ladder time informally; direction matters, exact seconds don't).
  b. Forced fallback: `python -c "import sim; sim.compose = lambda r: (_ for _ in ()).throw(RuntimeError('forced')); from sim import layout_retry; from recipe import parse_recipe; print(len(layout_retry(parse_recipe(open('example_and.txt').read()), verify=True)[0]), 'blocks via fallback')"`.
  Expected: prints a block count (maze path still greens — no-regression-by-construction proven, not asserted).
  c. Full suite: `python recipe.py`, `python sim.py`, `python layout.py`, `python serve.py --check`.
  Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add sim.py
git commit -m "feat: layout_retry tries composer first, maze fallback untouched"
```

---

### Task 8: Dense validation (holdout-respecting)

**Files:**
- None (measurement only; `handoff.md` record update at the end). Scratch probes go in `scratch/` (gitignored, never committed).

**Interfaces:**
- Consumes: full pipeline. Produces: measurement table in `handoff.md` (the evidence record — update it, create no new docs).

- [ ] **Step 1: Run the three combinational dense recipes (NOT cpu4, NOT micro1 yet)**

For each of `alu1.txt`, `ctrl_decode.txt`, `alu4.txt`: run `python redstone_mini.py <recipe>` from `D:\redstone-mini` with output redirected to a log file (never pipe through `Out-String`; poll the log — per handoff environment notes). Record per recipe: wall time, winning backend (composer vs maze seed), block count, ticks, vectors.
Expected: green builds (upstream precedent: all three compiled in ≤0.2s there; ours carry heavier tiles + sim gate, so allow minutes — the bar is green-by-mechanism, not a time target).

- [ ] **Step 2: Run micro1 (sequential composer proof)**

Same harness, `micro1.txt`.
Expected: green (the result upstream cannot produce — latch tile under composition). Record same columns.

- [ ] **Step 3: Synthetic paired floor (generality proof, same standard as the chaining spec)**

Per family (alu1, ctrl_decode, alu4, micro1): create 3 small mutations in `scratch/` (never committed) — one op swap, one added gate, one fanout-width change. For each mutant, run the default ladder twice: maze-only (force fallback exactly like Task 7 Step 3b) vs full (composer-first). Record green/not per mutant, pre vs post.
Expected: post green rate strictly exceeds pre per family (no absolute floor — base rates are near zero). A family that fails this is recorded as failing, not retried.

- [ ] **Step 4: Kill-switch check**

If Steps 1-3 yield zero sim-green composer builds: revert the Task 7 integration only (`git revert` the sim.py commit), keep Phase A (it paid for approach 1 regardless). Record the revert + composer failure modes in `handoff.md`. Do not touch the maze router.

- [ ] **Step 5: Holdout validation (cpu4) — ONLY after Steps 1-3 are green**

One run, `cpu4.txt`, same log-file harness. No tuning, no dump-reading to steer, no retries beyond the default ladder. Record the verdict in `handoff.md` verbatim (green or red with refusal class).
Expected: unknown — that is the point of a holdout. NEVER re-run to iterate; a red holdout means the composer needs its own spec, not another attempt.

- [ ] **Step 6: Commit the handoff record**

```bash
git add handoff.md
git commit -m "handoff: compositional backend dense verdicts (holdout included)"
```
