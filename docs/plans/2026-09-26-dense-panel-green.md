# Dense Panel-Green Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** All 8 `.txt` recipes verify green with one lever per used input.

**Architecture:** Claim straight E-W bus lanes before tiles so tiles dodge them (reuse `spot_free`), stamp one trunk + repeaters per input (reuse `place_rep` spacing), stub loads via repeater-output taps only (sim-sound). `recipe.py` relay only if cpu4 proves need.

**Tech Stack:** Python 3, stdlib only. No new dependencies, no new repo files (probes in gitignored `scratch/`).

## Global Constraints

- `sim.py`, `export.py`, `serve.py`, `core.py`, `debug.py` stay untouched (sim is the selector).
- `layout.py` first; `recipe.py` only if Task 5 measures cpu4 fanout exhaustion.
- No new dependencies, no new repo files. Test probes go in `scratch/` (gitignored, never merged).
- Unroutable net raises loudly like any gate net (no fallback paths).
- Seed-None runs are deterministic; per-seed variation uses separate RNG streams so the gate shuffle stream never changes.
- Dense builds (alu4/cpu4/ctrl_decode) run only as background jobs with log files + polling, never foreground. Kill rule: no log output for 600s → stop the job.
- One change per task: implement, measure, keep-or-revert. Never stack a new fix on a red baseline.

---

## File structure

- `D:\redstone-mini\layout.py` — only file Tasks 1-4 touch:
  - lane claim block before `phase 1` tiles (`~line 303`, anchor `phase 1: place all tiles`).
  - `spot_free` (`~371-393`): one extra disjoint check against lanes.
  - bank block (`~262-292`, `_ax/_ord/_prev`): unchanged, trunk heads attach here.
  - trunk stamp after tiles, before `bus:` netspec (`~626-668`): dust + repeaters reusing `place_rep:830-845` spacing (`is_straight:822-828`, facing map).
  - input tasks (`~669-694` spine-first sort): replaced per-input by trunk-tap stubs (Task 3).
  - `route:244-260`, rip-up `pending:752-806`, `try_bridge:708-751` cap 24: untouched.
- `D:\redstone-mini\recipe.py` — Task 5 only if measured: lift `:102` input exclusion for `>=3`-load inputs, reuse `buf_of:179-191` chain.
- Tests: `scratch/probe_lanes.py`, `scratch/probe_trunk.py`, `scratch/probe_dense.py` (all gitignored); suite `python recipe.py && python sim.py && python serve.py --check && python layout.py`.

---

### Task 1: Bus lanes pre-claim + tile dodge

**Files:**
- Modify: `D:\redstone-mini\layout.py:303-310` (insert lane claim before phase-1 tiles), `D:\redstone-mini\layout.py:371-393` (`spot_free`)
- Test: `scratch/probe_lanes.py`

**Interfaces:**
- Consumes: `recipe["inputs"]`, `gates` (used-input detection), `W`, `D`, `footprint:351-360`
- Produces: `lanes` dict (`net -> set((x,z))`) in `layout()` scope for Tasks 2-3; `spot_free` dodges lanes

- [ ] **Step 1: Write the failing probe**

```python
# scratch/probe_lanes.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from layout import layout
r = parse_recipe(open(r"D:\redstone-mini\micro1.txt").read())
try:
    layout(r, seed=None, grow=0)
    print("routed (lanes keep room or xor persists, see Task 3)")
except RuntimeError as e:
    assert "no route for" in str(e), str(e)[:120]
    print("still red (expected after Task 1):", str(e)[:100])
```

- [ ] **Step 2: Run probe to record the red baseline**

Run: `python scratch/probe_lanes.py` from `D:\redstone-mini`
Expected: `still red (expected after Task 1): no route for T1: ...` (lanes alone route nothing; order/room only)

- [ ] **Step 3: Claim lanes + dodge in spot_free**

Insert before `# phase 1: place all tiles` (`~line 303`):

```python
    # ponytail: bus lanes pre-claim (spec 2026-09-26-dense-panel-green).
    # Straight E-W claims south of tiles; tiles dodge via spot_free.
    # Lanes saturate -> maze detours (no new search).
    used_ins = {a for g in gates for a in g["args"]} & set(recipe["inputs"])
    lanes = {}
    for idx, name in enumerate(recipe["inputs"]):
        if name not in used_ins:
            continue
        lz = (D - 4) - idx * 2
        lanes[name] = {(x, lz) for x in range(1, W - 1)}
```

In `spot_free`, after `fp.isdisjoint(others_reserved[i])` (`~line 391`), insert:

```python
        for cells in lanes.values():
            if not fp.isdisjoint(cells):
                return False
```

Do NOT touch `gridpos:350`, `reserved:362`, bounds checks, or bank block.

- [ ] **Step 4: Run probe + suite (must be unchanged-or-better)**

Run: `python scratch/probe_lanes.py` from `D:\redstone-mini`
Expected: same `still red` line (room reserved, no delivery yet — Task 3 delivers)

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: all `ok` lines print (ports, or-lever, panel, bridge, tick, pulse, latch, crossover, comparator, serve demo 246). Any red = revert this task immediately.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "dense green: bus lanes pre-claim, tiles dodge"
```

---

### Task 2: Trunk stamp + repeater stations

**Files:**
- Modify: `D:\redstone-mini\layout.py:626-668` (insert trunk stamp after tiles, before `bus:` netspec)
- Test: `scratch/probe_trunk.py`

**Interfaces:**
- Consumes: Task 1 `lanes`, bank `pos:262-292`, `stamp_wire:226-242`, `ring:224-225`, `own:220-221`, `DIRS` from `core`
- Produces: trunk wires + `repeaters:{(x,z):(net,facing)}` stations per input; `trunk_rep` dict (`net -> [repeater-output cells]`) for Task 3 taps

- [ ] **Step 1: Write the trunk probe**

```python
# scratch/probe_trunk.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from layout import layout
r = parse_recipe(open(r"D:\redstone-mini\micro1.txt").read())
try:
    b, s, io = layout(r, seed=None, grow=0)
    print("routed blocks=", len(b), "size=", s)
except RuntimeError as e:
    assert "no route for" not in str(e) or "T1" in str(e), str(e)[:120]
    print("gate-stage only (acceptable now):", str(e)[:100])
```

- [ ] **Step 2: Run probe (fails on input marathons today)**

Run: `python scratch/probe_trunk.py` from `D:\redstone-mini`
Expected: `still red`-style `no route for <input>` or gate `T1` fail (trunks not stamped yet; stubs still marathon)

- [ ] **Step 3: Stamp trunks with repeater stations**

Insert after tiles, before `# bus: net spec` (`~line 626`):

```python
    # ponytail: input trunks (spec 2026-09-26-dense-panel-green). One dust
    # run per lane, repeaters every <=14 reusing place_rep spacing (bus
    # stations only, never on tile dust). Trunk cells join placed so rip-up
    # never orphans them (rip guards skip placed: ~762/768/782/794).
    trunk_rep = {}
    for name, cells in lanes.items():
        lz = next(iter(cells))[1]
        xs = sorted(x for x, z in cells)
        seg = [(x, lz) for x in xs]
        stamp_wire(seg, name)
        placed.update((x, 1, lz) for x, z in seg)
        outs = []
        # repeater stations west->east every <=14 on straight cells
        x0 = xs[0]
        while x0 + 14 < xs[-1]:
            xj = x0 + 14
            # face east: repeater at xj reading xj-1, driving xj+1
            if (xj, lz) in solid or (wires.get((xj, 1, lz)) not in (None, name)):
                raise RuntimeError(f"trunk station blocked for {name} at {(xj, lz)}")
            if wires.get((xj, 1, lz)) == name:
                del wires[(xj, 1, lz)]
            repeaters[(xj, lz)] = (name, "east")
            outs.append((xj + 1, lz))
            x0 = xj
        outs.append((xs[-1], lz))
        trunk_rep[name] = outs
```

Keep `repeaters` shape `{(x,z):(net,facing)}` identical to `place_rep:830-845`. Do NOT touch rip guards.

- [ ] **Step 4: Run probe + suite**

Run: `python scratch/probe_trunk.py` from `D:\redstone-mini`
Expected: `gate-stage only` or `routed` (trunks exist; input marathons still star — Task 3 converts them to taps)

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: all `ok` lines print. Any red = revert this task.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "dense green: input trunks with repeater stations"
```

---

### Task 3: Repeater-output taps (micro1 green)

**Files:**
- Modify: `D:\redstone-mini\layout.py:669-694` (input task building: star `drv->load` becomes tap stubs)
- Test: `scratch/probe_dense.py`

**Interfaces:**
- Consumes: Tasks 1-2 (`lanes`, `trunk_rep`, bank `pos`), `route:244-260`, `pos` ports from tiles
- Produces: input `tasks` as short stubs (`repeater-out -> load`); gate tasks byte-identical

- [ ] **Step 1: Write the micro1 end-to-end probe**

```python
# scratch/probe_dense.py
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import Counter
from recipe import parse_recipe, expand_gates
from sim import layout_retry
name = sys.argv[1] if len(sys.argv) > 1 else "micro1"
t0 = time.time()
r = parse_recipe(open(os.path.join(r"D:\redstone-mini", name + ".txt")).read())
b, s, io, st = layout_retry(r, verify=True)
gates = expand_gates(r["gates"], r["inputs"])
used = {a for g in gates for a in g["args"]} & set(r["inputs"])
c = Counter(io["levers"].values())
assert set(c) == used and all(v == 1 for v in c.values()), dict(c)
print(f"{name} OK blocks={len(b)} size={s} one-lever t={time.time()-t0:.1f}s", flush=True)
```

- [ ] **Step 2: Run probe (red baseline)**

Run: `python scratch/probe_dense.py micro1` from `D:\redstone-mini`
Expected: FAIL `RuntimeError: no route for ...` (star marathons still seal; taps not wired yet)

- [ ] **Step 3: Tap stubs at repeater outputs**

In task building (`~669-675`, after `tasks.append((drv, cell, net))` loop), insert after the loop, before `tasks.sort`:

```python
    # ponytail: repeater-output taps (spec 2026-09-26-dense-panel-green).
    # Input loads stub from nearest trunk repeater-out (full 15, sim-sound
    # per sim.py:112-113 decay); gates byte-identical. Star marathons deleted.
    _ins = set(recipe["inputs"])
    _kept = [t for t in tasks if t[2] not in _ins]
    for net in _ins:
        outs = trunk_rep.get(net, [])
        for (drv, cell, n) in [t for t in tasks if t[2] == net]:
            outs_sorted = sorted(outs, key=lambda o: abs(o[0] - cell[0]) + abs(o[1] - cell[1]))
            tap = outs_sorted[0] if outs_sorted else drv
            _kept.append((tap, cell, n))
    tasks = _kept
```

Keep spine-first sort below (`:679-694`) unchanged — it now orders short stubs. Do NOT touch gate tasks.

- [ ] **Step 4: Run probe (micro1 must flip green) + suite**

Run: `python scratch/probe_dense.py micro1` from `D:\redstone-mini`
Expected: `micro1 OK blocks=... one-lever t=...s`. If still red, diagnose with `python debug.py micro1.txt None 0` + dump inspection — do NOT proceed to Task 4 on red, keep-or-revert first.

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: every `ok` line prints. Any red = stop and revert.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "dense green: repeater-output taps, micro1 one-lever green"
```

---

### Task 4: OR-wall tile-local fix (alu1 green)

**Files:**
- Modify: `D:\redstone-mini\layout.py:420-467` (OR diode parking)
- Test: `python scratch/probe_dense.py alu1`

**Interfaces:**
- Consumes: Task 1 lanes/spot_free; OR `junctions:462`, `reps:433-456`
- Produces: `t1`-class diode-backs land outside own OR cluster

- [ ] **Step 1: Run probe (red baseline with cause)**

Run: `python scratch/probe_dense.py alu1` from `D:\redstone-mini`
Expected: FAIL — record message. Known wall: `t1` diode-back buried 1 cell inside own OR diode/exit cluster (dump-proven `seed=1: t1->(78,14)` per `handoff.md`).

- [ ] **Step 2: Diagnose with dump (no guessing)**

Run: `$env:REDSTONE_DEBUG="C:\Users\LOQ\AppData\Local\Temp\opencode\dbg_alu1.json"; python scratch/probe_dense.py alu1` from `D:\redstone-mini`
Expected: FAIL + `True` (dump written). Then query `t1` goal neighbours for `wire!=t1/solid/ring` (same query family as Task 3). Do NOT edit until dump names the sealer.

- [ ] **Step 3: Dodge own cluster when parking diodes**

In OR placement (`~434-456`, inside `for sig in a:` diode search), extend the collision skip from `r in solid or wire or b ... or r/b in seen` to also skip cells whose 4-neighbourhood holds this OR's own `junction j` or already-parked `reps` of the same gate:

```python
                                if r in solid or (r[0], 1, r[1]) in wires or b in solid or (b[0], 1, b[1]) in wires \
                                   or r in seen or b in seen:
                                    continue
```

becomes:

```python
                                if r in solid or (r[0], 1, r[1]) in wires or b in solid or (b[0], 1, b[1]) in wires \
                                   or r in seen or b in seen:
                                    continue
                                # ponytail: own-cluster dodge (alu1 t1 wall).
                                # Diode-backs buried in their own OR exit are
                                # unroutable by construction; next step over.
                                if max(abs(r[0] - j[0]), abs(r[1] - j[1])) <= 2 and len(seen) > 1:
                                    continue
```

Keep search order, facings, `junctions[j]={o}` untouched. If dump shows a different sealer, replace this dodge with the dump-named cells (one guard, same location).

- [ ] **Step 4: Run probe + suite (alu1 must flip, micro1 must hold)**

Run: `python scratch/probe_dense.py alu1 && python scratch/probe_dense.py micro1` from `D:\redstone-mini`
Expected: both `OK ... one-lever`. Then suite `python recipe.py && python sim.py && python serve.py --check && python layout.py` all `ok`.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "dense green: OR own-cluster dodge, alu1 one-lever green"
```

---

### Task 5: Relay iff measured + all-build acceptance

**Files:**
- Modify: `D:\redstone-mini\recipe.py:97-105` ONLY if this task measures exhaustion (else no code, probes only)
- Test: `scratch/probe_dense.py` for `alu4`, `cpu4`, `ctrl_decode` as background jobs; foreground `example_*`, `latch_sr`

**Interfaces:**
- Consumes: Tasks 1-4 green micro1/alu1; `expand_gates:82`, `fan:99-104`, `buf_of:179-191`
- Produces: acceptance verdict (8/8 green, one lever everywhere) or diagnosed red with dumps

- [ ] **Step 1: Foreground small builds (must already hold)**

Run: `python scratch/probe_dense.py example_and; python scratch/probe_dense.py example_2gates; python scratch/probe_dense.py example_xor; python scratch/probe_dense.py latch_sr` from `D:\redstone-mini`
Expected: each `OK ... one-lever` (or `unused-leverless` where applicable). Any red = stop, do not scale.

- [ ] **Step 2: Launch dense builds as background jobs**

Run each launch from `D:\redstone-mini` (this machine's `Start-Process` lacks `-RedirectOutput`; the `cmd /c start /b` form detaches past shell exit):

```powershell
cmd /c "start /b python scratch/probe_dense.py alu4 > scratch/alu4_dense.log 2>&1"
cmd /c "start /b python scratch/probe_dense.py cpu4 > scratch/cpu4_dense.log 2>&1"
cmd /c "start /b python scratch/probe_dense.py ctrl_decode > scratch/ctrl_dense.log 2>&1"
```

Poll (never block foreground on dense builds):

```powershell
Get-Content scratch/alu4_dense.log,scratch/cpu4_dense.log,scratch/ctrl_dense.log -ErrorAction SilentlyContinue
```

Expected: each log ends with `<name> OK blocks=... one-lever t=...s`. Kill rule: no log output for 600s → confirm no other python work is running (`Get-Process python`), then stop the job and diagnose from the retry behavior.

- [ ] **Step 3: Relay trigger (measure, don't guess)**

Trigger (and only trigger) for editing `recipe.py`: a dense input with `>=3` loads still seals after Tasks 1-4 (dump shows trunk ok, stubs seal at ports). If and only if measured, delete `and a not in inputs` from both census lines (`:102` and `:156`) so inputs chain via existing `buf_of:179-191`, re-run that build's probe, and commit separately:

```bash
git add recipe.py
git commit -m "dense green: input relay via existing chain (measured exhaustion on <build>)"
```

If no exhaustion, skip code — record `relay not needed` in the acceptance commit.

- [ ] **Step 4: Bridge-cap check (measure, don't guess)**

For each dense build, count stamped bridges via a fresh dump (`python debug.py <recipe> <seed> 0` writes the planning frame even on failure) plus this exact query — bridge supports are the only headless cobble triples:

```python
python -c "import json; d=json.load(open(r'C:\Users\LOQ\AppData\Local\Temp\opencode\dbg_state.json')); s={(int(x),int(z)):v for k,v in d['solid'].items() for x,z in [tuple(map(int,k.split(',')))] if v[0]=='cobble'}; n=sum(1 for (x,z) in s if (x-1,z) in s and (x+1,z) in s) + sum(1 for (x,z) in s if (x,z-1) in s and (x,z+1) in s); print('support-triples~bridges:', n//3)"
```

Trigger (and only trigger) for a cap raise: a build routes everything except cap exhaustion (`len(bridged) >= 24` at `layout.py:712`). If and only if measured, raise to 96, update the ponytail ceiling line, re-run, commit separately.

- [ ] **Step 5: Acceptance commit (metrics, no code)**

Append per-build results (blocks, size, wall time, bridges used, relay needed/not) to `handoff.md`, extend `PONYTAIL-DEBT.md` with the new real-ceiling rows (bus lanes + trunk taps, each with ceiling + upgrade), then:

```bash
git add handoff.md PONYTAIL-DEBT.md
git commit -m "dense green: acceptance metrics (8/8 green, one lever everywhere)"
```

Acceptance = 8/8 `layout_retry(verify=True)` green + `Counter(levers)==1` per used input + suite green. Anything else is red: no merge, diagnose with dumps.
