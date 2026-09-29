# Input port corridors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ring a reserved approach ray for every input-fed port at placement time so delivery's last cells survive dense rows.

**Architecture:** After tile placement (recs complete), walk recs and ring an 8-long 3-wide ray per input-fed port (west for tile ports, east for XOR, outward for OR diode-backs), skipping OOB/solid/foreign-wire and breaking the ray there. The router is untouched — rings are already walls for foreign nets.

**Tech Stack:** Python 3, stdlib only. No new dependencies, no new repo files (probes live in gitignored `scratch/`).

## Global Constraints

- Modify only `D:\redstone-mini\layout.py`.
- `sim.py`, `export.py`, `serve.py`, `core.py`, `recipe.py`, `debug.py` stay untouched.
- Router policy stays untouched: no rip-up, bridge, task-order, or `route()` changes in this plan.
- No new dependencies, no new repo files. Test probes go in `scratch/` (gitignored, never merged).
- Unroutable nets raise loudly like today (no fallback paths).
- Seed-None runs are deterministic.
- Dense builds (alu4/cpu4) run only as background jobs with log files + polling, never foreground. Kill rule: no log output for 600s → confirm no other python work is running (`Get-Process python`), then stop the job.
- One change per task: implement, measure, keep-or-revert. Never stack a new fix on a red baseline.

---

## File structure

All work happens in `D:\redstone-mini\layout.py`, in exactly one place: a new corridor block inserted between the placement loop end (`raise RuntimeError(f"NOT blocked for {o}")`, ~line 624) and the `# bus: net spec` comment (~line 626). It consumes `recs` (port cells per op shape below), `recipe["inputs"]`, `solid`, `wires`, `ring`, `own`, `W`, `D` — all in scope there. It produces nothing but `rings` entries.

Port shapes in `recs` (verify against code before editing):
- `("AND"|"LATCH"|"XOR", out, args, (pa, pb, po))` — pa/pb are the two in-ports.
- `("NOT", out, args, (bx, bz))` — in-port is `(bx - 1, bz)` (matches `_load`).
- `("OR", out, args, (j, reps))` — `reps` is `[(r, b), ...]` per input signal; `b` is the diode-back load cell, `b - r` is the unit outward direction.
- `("OUT", ...)` — outputs, never corridor targets; skip.

---

### Task 1: Corridor stamp + unit probe

**Files:**
- Modify: `D:\redstone-mini\layout.py` (~lines 624-631: insert corridor block, refresh one stale fanout comment)
- Test: `scratch/probe_corridors.py` (new; dump-asserts rays)

**Interfaces:**
- Consumes: `recs`, `recipe["inputs"]`, `solid`, `wires`, `ring`, `own`, `W`, `D`.
- Produces: ringed approach rays for every input-fed port (Task 2-5 rely on delivery surviving them).

- [ ] **Step 1: Write the corridor probe**

```python
# scratch/probe_corridors.py
import os, sys, json
sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe
from layout import layout
name = sys.argv[1] if len(sys.argv) > 1 else "micro1"
r = parse_recipe(open(os.path.join(r"D:\redstone-mini", name + ".txt")).read())
path = r"C:\Users\LOQ\AppData\Local\Temp\opencode\corr_state.json"
os.environ["REDSTONE_DEBUG"] = path
try:
    layout(r, seed=None, grow=0)
    print("layout routed")
except RuntimeError as e:
    print("layout:", str(e)[:80])
doc = json.load(open(path))
W, D = doc["W"], doc["D"]
solid = {tuple(map(int, k.split(","))) for k in doc["solid"]}
wires = {}
for k, v in doc["wires"].items():
    x, y, z = map(int, k.split(","))
    wires[(x, y, z)] = v
rings = {tuple(map(int, k.split(","))): v for k, v in doc["rings"].items()}
def ray(lx, lz, dx, dz, net):
    cells, maxk = [], -1
    for k in range(8):
        stop = False
        for s in (-1, 0, 1):
            x, z = lx + dx * k - dz * s, lz + dz * k + dx * s
            if not (0 <= x < W and 0 <= z < D):
                continue
            if (x, z) in solid:
                stop = True
                continue
            w = wires.get((x, 1, z))
            if w is not None and w != net:
                stop = True
                continue
            cells.append((x, z))
            maxk = max(maxk, k)
        if stop:
            break
    return cells, maxk
checked = pinned = 0
for net, spec in doc["netspec"].items():
    if net not in r["inputs"]:
        continue
    for lx, lz in spec["loads"]:
        checked += 1
        for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            cells, maxk = ray(lx, lz, dx, dz, net)
            # maxk >= 3 proves the ray exceeds tile-halo depth (ports +-1):
            # tile-fam rings alone can never satisfy this.
            if maxk >= 3 and all(net in rings.get(c, []) for c in cells):
                pinned += 1
                break
        else:
            print("unrayed load:", net, (lx, lz))
assert checked > 0 and pinned == checked, f"corridors missing: {pinned}/{checked} ports rayed"
print(f"corridors ok: {pinned}/{checked} input ports fully rayed")
```

- [ ] **Step 2: Run probe to verify it fails (no rays exist yet)**

Run: `python scratch/probe_corridors.py micro1` from `D:\redstone-mini`
Expected: FAIL — `AssertionError: corridors missing: 0/N ports rayed` (tile-fam halos never reach depth 3). Any `0/N` with N > 0 is the correct red baseline.

- [ ] **Step 3: Insert the corridor block**

Insert between `raise RuntimeError(f"NOT blocked for {o}")` (NOT placement end) and the `# bus: net spec from tile ports` comment:

```python
    # ponytail: input approach corridors (spec 2026-09-26-input-port-
    # corridors-design). For every input-fed port, ring an 8-long 3-wide
    # ray for that input (west for tile ports, east for XOR, outward for OR
    # diode-backs): delivery's last cells stay routable by construction.
    # Skip OOB/solid/foreign-wire (never seal others); break the ray there
    # (beyond is unreachable). Router untouched: rings already wall foreign
    # nets. Ceiling: truncated rays degrade to today; upgrade: longer rays.
    for _op, _o, _a, _cell in recs:
        _ports = []
        if _op in ("AND", "LATCH"):
            _pa, _pb, _po = _cell
            if _a[0] in recipe["inputs"]:
                _ports.append((_pa, (-1, 0), _a[0]))
            if _a[1] in recipe["inputs"]:
                _ports.append((_pb, (-1, 0), _a[1]))
        elif _op == "XOR":
            _pa, _pb, _po = _cell
            if _a[0] in recipe["inputs"]:
                _ports.append((_pa, (1, 0), _a[0]))
            if _a[1] in recipe["inputs"]:
                _ports.append((_pb, (1, 0), _a[1]))
        elif _op == "NOT":
            _bx, _bz = _cell
            if _a[0] in recipe["inputs"]:
                _ports.append(((_bx - 1, _bz), (-1, 0), _a[0]))
        elif _op == "OR":
            _j, _reps = _cell
            for _sig, (_rr, _bb) in zip(_a, _reps):
                if _sig in recipe["inputs"]:
                    _ports.append((_bb, (_bb[0] - _rr[0], _bb[1] - _rr[1]), _sig))
        for (_px, _pz), (_dx, _dz), _net in _ports:
            for _k in range(8):
                _stop = False
                for _s in (-1, 0, 1):
                    _cx = _px + _dx * _k - _dz * _s
                    _cz = _pz + _dz * _k + _dx * _s
                    if not (0 <= _cx < W and 0 <= _cz < D):
                        continue
                    if (_cx, _cz) in solid:
                        _stop = True
                        continue
                    _w = wires.get((_cx, 1, _cz))
                    if _w is not None and _w != _net:
                        _stop = True
                        continue
                    ring(_cx, _cz, own(_net))
                if _stop:
                    break
```

In the same edit, refresh the stale fanout comment two lines below (it still claims zero-wire per-load levers, deleted by the panel). Replace:

```python
    # Inputs fan out via one lever per load below (zero-wire); every other
```

with:

```python
    # Inputs fan out from the single bank lever (approach corridors above
    # keep each input-fed port reachable); every other
```

Leave the rest of that comment block byte-identical.

- [ ] **Step 4: Run probe (rays must appear)**

Run: `python scratch/probe_corridors.py micro1` from `D:\redstone-mini`
Expected: `corridors ok: N/N input ports fully rayed` (the `layout routed` / `layout: ...` first line may still report red routing — routing flips green in Task 3; this task only proves the stamp). If any `unrayed load` lines print, inspect that port in the dump before continuing (truncated ray = placement reality, not probe bug — but understand which).

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "port corridors: ringed input approaches at placement"
```

---

### Task 2: Small-build greens hold

**Files:**
- Modify: none (verification only)
- Test: existing suite + fanout probe

**Interfaces:**
- Consumes: Task 1's corridor rings.
- Produces: proof that reservation doesn't seal small builds (Task 3+ rely on it).

- [ ] **Step 1: Run the panel self-check build**

Run: `python layout.py` from `D:\redstone-mini`
Expected: all four lines print — `ports ok`, `or-lever ok`, `panel ok`, `bridge ok`. Any red = corridors sealed a small build: diagnose via dump (which corridor blocks which lane?) before continuing; do not proceed on red.

- [ ] **Step 2: Run the full small suite**

Run: `python recipe.py && python sim.py && python serve.py --check && python scratch/probe_panel.py` from `D:\redstone-mini`
Expected: every `ok` line prints (xor, fanout, latch, tick, stages, latch-hold, verticals, crossover, comparator, serve demo + 400, shared-input one-lever, unused-leverless). Record the serve demo block count (was 246) — corridors may add wire; green is the bar, counts are data.

- [ ] **Step 3: Commit the numbers (docs only, no code)**

```bash
git add handoff.md
git commit -m "port corridors: small-build greens hold (demo NNN blocks)"
```

(Replace NNN with the measured serve demo count: in `handoff.md`, update the panel section's `(demo 270→246 blocks)` fragment to `(demo NNN blocks, corridors stamp clean)` — one fragment, nothing else.)

---

### Task 3: micro1 flips green

**Files:**
- Modify: none (verification only — corridors + existing rip/bridge do the work)
- Test: `scratch/probe_spine.py` (exists from the spine plan: verify + one-lever assert + metrics)

**Interfaces:**
- Consumes: Tasks 1-2 (stamped corridors, green small builds).
- Produces: first dense green, or a classified red (transit vs truncated-corridor).

- [ ] **Step 1: Run the micro1 end-to-end probe**

Run: `python scratch/probe_spine.py micro1` from `D:\redstone-mini`
Expected: `micro1 OK blocks=... size=... one-lever-everywhere t=...s`. (Probe name is spine-era; it asserts verify + exactly-one-lever-per-used-input, which is exactly this spec's bar — do not rename it, do not write a second probe.)

- [ ] **Step 2 (only on red): classify before touching anything**

Run: `python scratch/probe_corridors.py micro1` from `D:\redstone-mini`
- Corridors still `N/N`: the red is in TRANSIT (router arbitration) — per spec §2 this is the only router-change trigger; stop, report the failing net + dump window, do not patch.
- Corridors regressed (`unrayed load` lines): placement bug in Task 1 — fix the ray (never the router), re-run Task 1 Step 4 + Task 2, then this step.

- [ ] **Step 3: Commit the green**

```bash
git add handoff.md
git commit -m "port corridors: micro1 green, one lever per input (NNN blocks)"
```

(Replace NNN with the measured block count.)

---

### Task 4: alu1 + suite re-green

**Files:**
- Modify: none (verification only)
- Test: generic probe + full suite

**Interfaces:**
- Consumes: Task 3's micro1 green.
- Produces: banded-build proof (alu1 stacks 10 gates in band 2 — the corridor-collision stress case) + suite confirmation.

- [ ] **Step 1: Run alu1 (foreground — small file, fails fast)**

Run: `python scratch/probe_spine.py alu1` from `D:\redstone-mini`
Expected: `alu1 OK ... one-lever-everywhere t=...s`. On red: classify exactly as Task 3 Step 2 (corridors probe first), stop on transit reds.

- [ ] **Step 2: Re-run everything small**

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py && python scratch/probe_panel.py && python scratch/probe_corridors.py micro1` from `D:\redstone-mini`
Expected: all green, corridors still N/N (corridors must survive everything else passing — reservation holds under the full field).

- [ ] **Step 3: Commit**

```bash
git add handoff.md
git commit -m "port corridors: alu1 green (NNN blocks), suite holds"
```

---

### Task 5: Dense acceptance (alu4/cpu4/ctrl_decode)

**Files:**
- Modify: none unless a spec §2 trigger fires (then `layout.py`, separate commit per trigger)
- Test: background jobs + dump queries + metrics

**Interfaces:**
- Consumes: Tasks 1-4 (green micro1/alu1/suite).
- Produces: acceptance verdict (all builds green, one lever everywhere) or a classified, dump-proven red.

- [ ] **Step 1: Launch dense builds as background jobs**

From `D:\redstone-mini` (this machine's `Start-Process` lacks `-RedirectOutput`; the `cmd /c start /b` form detaches past shell exit):

```powershell
cmd /c "start /b python scratch/probe_spine.py alu4 > scratch/alu4_corr.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py cpu4 > scratch/cpu4_corr.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py ctrl_decode > scratch/ctrl_corr.log 2>&1"
```

Poll (never block foreground on dense builds):

```powershell
Get-Content scratch/alu4_corr.log,scratch/cpu4_corr.log,scratch/ctrl_corr.log -ErrorAction SilentlyContinue
```

Expected: each log ends with `<name> OK blocks=... one-lever-everywhere t=...s`.

- [ ] **Step 2 (only on red): classify transit vs corridor**

Run `python scratch/probe_corridors.py <build>` for the failing build:
- Corridors N/N → TRANSIT red. Count stamped bridges with a fresh dump (`python debug.py <build>.txt <seed> 0`, dump writes even on failure) plus this exact query — bridge supports are the only headless cobble triples:

```python
python -c "import json; d=json.load(open(r'C:\Users\LOQ\AppData\Local\Temp\opencode\dbg_state.json')); s={(int(x),int(z)):v for k,v in d['solid'].items() for x,z in [tuple(map(int,k.split(',')))] if v[0]=='cobble'}; n=sum(1 for (x,z) in s if (x-1,z) in s and (x+1,z) in s) + sum(1 for (x,z) in s if (x,z-1) in s and (x,z+1) in s); print('support-triples~bridges:', n//3)"
```

Spec §2 triggers only: bridges exhausted at 24 with everything else routed → bridge-first for inputs returns as its own commit; failure inside a full corridor → placement fix, never router. Anything else → stop, report net + dump window, no patch.
- Corridors regressed → Task 1 placement bug: fix the ray, re-run Tasks 1-4 in order. No router changes.

- [ ] **Step 3: Record metrics + acceptance commit**

Append per-build results (blocks, size, wall time, bridges used) to `handoff.md`, extend `PONYTAIL-DEBT.md` with the corridor marker row (ceiling + upgrade, matching existing rows), then:

```bash
git add handoff.md PONYTAIL-DEBT.md
git commit -m "port corridors: acceptance metrics (<builds> green, one lever everywhere)"
```

Acceptance = micro1, alu1, alu4, cpu4, ctrl_decode verify green + suite green + lever asserts green. Anything else is red: no merge, diagnose with dumps.
