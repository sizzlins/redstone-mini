# Single-Lever Input Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One lever per used input in a south-edge row; inputs route as ordinary maze nets.

**Architecture:** Replace the phase-0 OR-only batch levers and the per-load lever loop with a single south bank; delete the feed-skip so input fanout becomes normal `drv -> load` tasks through the existing router (rip-up, boosters, bridges, pop cap).

**Tech Stack:** Python 3, stdlib only. No new dependencies.

## Global Constraints

- Modify only `layout.py`.
- No new files, no new dependencies.
- `sim.py`, `export.py`, `serve.py`, `core.py`, `recipe.py`, `debug.py` stay untouched.
- Unroutable input raises loudly like any gate net (no fallback paths).
- Unused inputs stay lever-less.
- Full suite (`python recipe.py`, `python sim.py`, `python serve.py --check`, `python layout.py`) stays green.

---

### Task 1: South bank placement (replace OR-only batch block)

**Files:**
- Modify: `D:\redstone-mini\layout.py:262-290`
- Test: scratch probe via `python -c` (no new files)

**Interfaces:**
- Consumes: `recipe["inputs"]`, `gates` (for used-input detection), `W`, `D`, `solid`, `wires`, `blocks`, `DIRS`, `own`, `ring`, `stamp_wire`
- Produces: `pos[name] = (x + 1, bz)` bank feed per used input, `feeds` containing bank feed cells, `solid[(x, bz)] = ("lever", name)` per used input

- [ ] **Step 1: Write the failing probe**

```bash
python -u -c "from recipe import parse_recipe; from sim import layout_retry; from collections import Counter; r = parse_recipe('IN a, b, c
OUT y
t = a AND b
y = t OR c
'); b, s, io, st = layout_retry(r, verify=True); c = Counter(io['levers'].values()); assert list(c.values()) == [1] * len(c), dict(c); print('one-lever OK', dict(c))"
```

Run: `python -u -c "..."` (above) from `D:\redstone-mini`
Expected: FAIL with `AssertionError` (today each load gets its own lever only when an input fans out; extend the recipe so `a` feeds two gates: `y1 = a AND b`, `y2 = a AND c`, `y = y1 OR y2` — then `a` has 2 levers and the assert fails)

- [ ] **Step 2: Run probe to verify it fails**

Run: same command with the two-gate recipe
Expected: FAIL, `Counter({'a': 2, ...})`

- [ ] **Step 3: Replace the phase-0 block with the south bank**

Replace `D:\redstone-mini\layout.py:262-290` (the `firstuse`/`firstor`/`orfeed` gating and the `z=6` batch placement) with:

```python
    # maze: every used input gets one bank lever on the south edge; fanout
    # below rides the router (zero-wire taps deleted — see bus section).
    pos = {}
    feeds = set()  # bank feed wire cells, seeded for the open-check
    used = {a for g in gates for a in g["args"]} & set(recipe["inputs"])
    bz = D - 2
    for idx, name in enumerate(recipe["inputs"]):
        if name not in used:
            continue  # unused input: no lever
        x = 2 + idx * 3
        if not (x + 1 < W and bz - 1 >= 0):
            raise RuntimeError(f"bank lever out of bounds for {name}")
        if (x, bz) in solid or (x, bz) in wires or (x + 1, bz) in solid or (x + 1, 1, bz) in wires:
            raise RuntimeError(f"bank lever spot taken for {name} at {(x, bz)}")
        blocks.append((x, 1, bz, "minecraft:lever"))
        solid[(x, bz)] = ("lever", name)
        for dx, dz in DIRS:
            ring(x + dx, bz + dz, own(name))
        stamp_wire([(x + 1, bz)], name)
        feeds.add((x + 1, 1, bz))
        pos[name] = (x + 1, bz)
```

Delete `firstuse`, `firstor`, `orfeed` (now dead). Keep the `"0"`/`"1"` tie block that follows unchanged.

- [ ] **Step 4: Run probe to verify bank exists (routing still skipped at this point)**

Run: `python -u -c "from recipe import parse_recipe; from layout import layout; r = parse_recipe(open('example_and.txt').read()); b, s, io = layout(r); zs = {z for (x, z) in io['levers']}; assert len(io['levers']) == 2 and len(zs) == 1, io['levers']; print('bank OK', sorted(io['levers'].items()))"` from `D:\redstone-mini`
Expected: PASS — one lever per input, all sharing one z (single row; coordinates are post-shrink-wrap so assert row-ness, not an absolute z)

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "single-lever panel: south bank placement"
```

### Task 2: Route inputs as ordinary nets (delete per-load loop + feed skip)

**Files:**
- Modify: `D:\redstone-mini\layout.py:667-703` (per-load lever loop lines 667-688, feed-skip lines 698-702; line numbers pre-Task-1, re-anchor with `Select-String -Pattern "bus lever blocked|already touch their own lever" -Path layout.py` before editing)
- Test: scratch probe via `python -c` (no new files)

**Interfaces:**
- Consumes: Task 1's `pos[name]` bank feeds, `netspec`, `orbbs`, `feeds` (now bank-only)
- Produces: `tasks` including `(bank_pos, load_cell, input_net)` entries; `io["levers"]` with exactly one entry per used input

- [ ] **Step 1: Write the failing probe**

```bash
python -u -c "from recipe import parse_recipe; from sim import layout_retry; from collections import Counter; r = parse_recipe('IN a, b, c
OUT y
y1 = a AND b
y2 = a AND c
y = y1 OR y2
'); b, s, io, st = layout_retry(r, verify=True); c = Counter(io['levers'].values()); assert c['a'] == 1, dict(c); print('one-lever routed OK', dict(c))"
```

Run: from `D:\redstone-mini`
Expected: FAIL — after Task 1 the bank exists but input loads still skip routing via `feeds`, so `a` keeps per-load tap levers from Task 1's leftover loop (or routes nothing and sim fails OPEN)

- [ ] **Step 2: Run probe to verify it fails**

Run: same command
Expected: FAIL (`c['a'] != 1` or `OPEN`/`SIM MISMATCH` RuntimeError)

- [ ] **Step 3: Delete the per-load loop, keep the OR diode-back skip**

Delete the loop body that stamps port dust plus an adjacent lever per load (the `for (lx, lz) in spec['loads']:` block ending with the `bus lever blocked` raise and the wired-OR comment). Keep this skip verbatim:

```python
            if (lx, lz) in orbbs:
                continue  # OR diode-back: batch-1 lever feeds it via the junction
```

Then delete the feed-skip in task building (the `if net in ins and (...)` continue), so every input load appends `(drv, cell, net)` with `drv` resolving to the bank `pos[name]` via the existing `pos.get(net)` fallback. Update the stale `ponytail:` comment above it (input loads no longer touch their own feed) — replace with:

```python
    # ponytail: inputs ride the router like gate nets (single-lever panel);
    # fanout cost is real routing now. Loud fail if a dense input seals.
```

- [ ] **Step 4: Run probe to verify it passes**

Run: same Step-1 command
Expected: PASS — `one-lever routed OK {'a': 1, 'b': 1, 'c': 1}`, sim verified

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "single-lever panel: route inputs as ordinary nets"
```

### Task 3: Self-check extension + full suite green

**Files:**
- Modify: `D:\redstone-mini\layout.py` `__main__` block (after the `or-lever ok` print, anchor with `Select-String -Pattern "or-lever ok" -Path layout.py`)
- Test: `python layout.py`, `python recipe.py`, `python sim.py`, `python serve.py --check` from `D:\redstone-mini`

**Interfaces:**
- Consumes: Tasks 1-2 behavior, `layout_retry`, `parse_recipe`
- Produces: `bridge ok`-style pinned check: `panel ok: ...` print line

- [ ] **Step 1: Append the fanout self-check after the or-lever check**

```python
    # ponytail: ONE panel check — shared input builds green with exactly
    # one lever per input (verify=True proves the routed fanout fires).
    from collections import Counter as _Ctr
    _r = parse_recipe("IN a, b, c\nOUT y\ny1 = a AND b\ny2 = a AND c\ny = y1 OR y2\n")
    _, _, _io, _ = layout_retry(_r, verify=True)
    _c = _Ctr(_io["levers"].values())
    assert _c["a"] == 1 and len(_c) == 3, _c
    print("panel ok: shared input on one bank lever, verify green")
```

- [ ] **Step 2: Run the layout self-check**

Run: `python layout.py` from `D:\redstone-mini`
Expected: PASS — ends with `panel ok: shared input on one bank lever, verify green`

- [ ] **Step 3: Run the full suite and pin counts**

Run: `python recipe.py && python sim.py && python serve.py --check` from `D:\redstone-mini`
Expected: PASS — all existing `ok` lines print; then run `python -u -c "from recipe import parse_recipe; from sim import layout_retry; r = parse_recipe(open('micro1.txt').read()); b, s, io, st = layout_retry(r, verify=True); print('micro1', len(b))"` and record the block count in the commit message (informational; green is the bar, counts may rise on fanout-heavy builds)

- [ ] **Step 4: Commit**

```bash
git add layout.py
git commit -m "single-lever panel: fanout self-check (micro1 NNNN blocks)"
```

(replace NNNN with the count from Step 3)
