# Spine-fed input distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every input as one bank-fed spine plus short tap branches so all builds verify green with one lever per input.

**Architecture:** Per input, the bank→farthest-load task routes first (the spine, booster-covered like any path); remaining loads tap bank-connected spine wire (astar multi-source). Spine cells become unrippable (`placed`); spines stay bridgeable; input tasks bridge-first. Gate nets byte-identical.

**Tech Stack:** Python 3, stdlib only. No new dependencies, no new repo files (probes live in gitignored `scratch/`).

## Global Constraints

- Modify only `D:\redstone-mini\layout.py`.
- `sim.py`, `export.py`, `serve.py`, `core.py`, `recipe.py`, `debug.py` stay untouched.
- No new dependencies, no new repo files. Test probes go in `scratch/` (gitignored, never merged).
- Unroutable spine/tap raises loudly like any gate net (no fallback paths).
- Seed-None runs are deterministic; per-seed variation uses separate RNG streams so the gate shuffle stream never changes.
- Dense builds (alu4/cpu4) run only as background jobs with log files + polling, never foreground. Kill rule: no log output for 600s → stop the job.
- One change per task: implement, measure, keep-or-revert. Never stack a new fix on a red baseline.

---

## File structure

All work happens in `D:\redstone-mini\layout.py` (one responsibility per region):

- `route()` (~line 244): single-task router. Task 2 adds bank-connected tap starts for input nets; Task 3 records input paths into `placed`.
- Task-order block (~lines 676-686): distance sort + shuffle + inputs-first. Task 1 replaces it with spine-first-per-input order.
- `try_bridge()` (~lines 700-743): last-resort hop. Task 4 allows `placed` victims + adds bridge-first call for input tasks in the pending loop (~line 751).
- Rip-up guards (~lines 762, 768, 782, 794: `c not in placed`): DO NOT TOUCH — they are what makes spines unrippable.
- Bridge sort key (~line 720, prefers non-placed victims): DO NOT TOUCH.
- Bridge cap (~line 704, `>= 24`): DO NOT TOUCH unless Task 5 measures cap exhaustion.

---

### Task 1: Spine-first task order

**Files:**
- Modify: `D:\redstone-mini\layout.py:676-686`
- Test: scratch probe (routing still star-shaped here; this task must not change outcomes, only order)

**Interfaces:**
- Consumes: `tasks` list of `(drv, cell, net)` triples built at lines 670-675; `recipe["inputs"]`; `seed`.
- Produces: `_ins` (set of input net names), `_dist` (Manhattan task-length lambda), `_far` (input net → its farthest task tuple), `_oi` (input net → group rank) — all in `layout()` scope for later tasks; reordered `tasks` (spine first per input group, then taps nearest-from-bank, then gates in today's relative order).

- [ ] **Step 1: Write the order probe**

```python
# scratch/probe_order.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from layout import layout
r = parse_recipe(open(r"D:\redstone-mini\micro1.txt").read())
try:
    layout(r, seed=None, grow=0)
    print("routed (unexpected at this stage)")
except RuntimeError as e:
    print("still red (expected):", str(e)[:100])
```

- [ ] **Step 2: Run probe to record the red baseline**

Run: `python scratch/probe_order.py` from `D:\redstone-mini`
Expected: `still red (expected): no route for ...` (star routing still seals; order alone fixes nothing)

- [ ] **Step 3: Replace the order block with spine-first order**

Replace `D:\redstone-mini\layout.py:676-686` (the distance sort, the shuffle, the `inputs ride FIRST` comment, `_ins`, and the `not in _ins` sort) with:

```python
    tasks.sort(key=lambda t: -(abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])))
    if seed is not None:
        random.Random(seed).shuffle(tasks)
    # ponytail: spine-first per input (spec 2026-09-26-spine-fed-input-
    # distribution-design). Bank->farthest load routes once (the spine);
    # remaining loads tap it nearest-first. Input groups shuffle per seed
    # on a separate stream so the gate shuffle above is byte-identical.
    # Gates share key (1,0,0,0): stable sort keeps today's relative order.
    _ins = set(recipe["inputs"])
    _dist = lambda t: abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1])
    _far = {}
    for _t in tasks:
        if _t[2] in _ins and (_t[2] not in _far or _dist(_t) > _dist(_far[_t[2]])):
            _far[_t[2]] = _t
    _names = [n for n in recipe["inputs"] if n in _ins]
    if seed is not None:
        random.Random(seed + 1).shuffle(_names)
    _oi = {n: i for i, n in enumerate(_names)}
    tasks.sort(key=lambda t: (0, _oi[t[2]], 0 if t == _far[t[2]] else 1, _dist(t)) if t[2] in _ins else (1, 0, 0, 0))
```

Notes for the implementer: `t == _far[t[2]]` is tuple equality. In the pathological case of two identical task tuples, both sort first — harmless (same route twice, second is a trivial tap). Single-load inputs: the lone task is the spine; behavior identical to today.

- [ ] **Step 4: Run probe + suite (must be unchanged-or-better)**

Run: `python scratch/probe_order.py` from `D:\redstone-mini`
Expected: still `still red (expected): no route for ...` (order alone is behavior-preserving for star routing)

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py` from `D:\redstone-mini`
Expected: all `ok` lines print (ports, or-lever, panel, bridge, tick, latch, crossover, comparator, serve). Any red = revert this task immediately.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "spine distribution: spine-first task order (behavior-preserving)"
```

---

### Task 2: Bank-connected tap starts in route()

**Files:**
- Modify: `D:\redstone-mini\layout.py:244-251` (`route()` starts + comment)
- Test: scratch probe asserting routing *completes* (checkers may still fire at this stage)

**Interfaces:**
- Consumes: Task 1's reordered `tasks`; `wires` (live net map); `DIRS` (module import, already used); `recipe["inputs"]`.
- Produces: multi-source `_starts` for input nets inside `route()`; gate nets untouched single-source.

- [ ] **Step 1: Write the routing-completion probe**

```python
# scratch/probe_taps.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from layout import layout
r = parse_recipe(open(r"D:\redstone-mini\micro1.txt").read())
try:
    b, s, io = layout(r, seed=None, grow=0)
    print("routed blocks=", len(b), "size=", s)
except RuntimeError as e:
    assert "no route for" not in str(e), str(e)[:120]
    print("checker-stage only (acceptable now):", str(e)[:100])
```

- [ ] **Step 2: Run probe to verify it fails on no-route**

Run: `python scratch/probe_taps.py` from `D:\redstone-mini`
Expected: FAIL with `AssertionError` whose message starts `no route for` (today every branch is a full star marathon and seals)

- [ ] **Step 3: Add connected tap starts for input nets**

Replace `D:\redstone-mini\layout.py:244-251` with:

```python
    def route(a, b, net):
        # input spines feed tap branches (spec 2026-09-26-spine-fed-input-
        # distribution-design): starts = bank feed + bank-connected same-net
        # wire (BFS at call time; spine calls degenerate to single-source
        # because only the feed exists yet). Gate nets stay single-source
        # (taps broke xor in 2026-09; sim guards this task).
        _starts = [(a[0], 1, a[1])]
        if net in recipe["inputs"]:
            _have = set(_starts)
            _stack = list(_starts)
            while _stack:
                _cc = _stack.pop()
                for _dx, _dz in DIRS:
                    _m = (_cc[0] + _dx, 1, _cc[2] + _dz)
                    if _m not in _have and wires.get(_m) == net:
                        _have.add(_m)
                        _stack.append(_m)
                        _starts.append(_m)
        seen = set()
        best = None
        for margin in (12, 40, None):
            path = astar(_starts, (b[0], 1, b[1]), net, W, D, solid, rings, wires, junctions, margin, blocked=seen, congest=congest, guard=guard)
```

Keep lines 252-260 (`if path and ...`, `stamp_wire(path, net)`, `paths.append`, `return`) exactly as they are. Do NOT include disconnected own wire: bare taps let a ripped trunk re-tap zero-length at goals doubling as starts (OPEN stubs, measured 2026-09-26).

- [ ] **Step 4: Run probe (routing must complete)**

Run: `python scratch/probe_taps.py` from `D:\redstone-mini`
Expected: PASS — either `routed blocks= ...` or `checker-stage only (...OPEN... / ...SHORT... / ...SIM...)`. Any `no route for` = this task failed, diagnose before continuing.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "spine distribution: bank-connected tap starts for input nets"
```

---

### Task 3: Spine cells become unrippable

**Files:**
- Modify: `D:\redstone-mini\layout.py:258-260` (`route()` tail: stamp + paths record)
- Test: panel self-check vector (the exact sim-dark decay catcher)

**Interfaces:**
- Consumes: Task 2's `route()`; `placed` (defined line ~687 as `set(wires)`, executed before any `route()` call — closure late binding, do not move it).
- Produces: input delivery paths protected from rip-up (rip guards at lines ~762/768/782/794 skip `placed` cells with zero code change).

- [ ] **Step 1: Write the decay-catcher probe**

```python
# scratch/probe_decay.py
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from recipe import parse_recipe
from sim import layout_retry
_r = parse_recipe("IN a, b, c\nOUT y\ny1 = a AND b\ny2 = a AND c\ny = y1 OR y2\n")
_, _, _io, _ = layout_retry(_r, verify=True)
from collections import Counter as _C
_c = _C(_io["levers"].values())
assert _c["a"] == 1 and len(_c) == 3, _c
print("decay-catcher green: shared input lights y on all vectors")
```

- [ ] **Step 2: Run probe (may already pass on small builds; micro1 is the real test — record outcome)**

Run: `python scratch/probe_decay.py` from `D:\redstone-mini`
Expected pre-task: PASS on this 4-gate build is acceptable; the task's value is proven on micro1 in Task 5. If it FAILS with `SIM MISMATCH`, that is the decay bug — proceed to Step 3, it is the fix.

- [ ] **Step 3: Record input paths into placed**

In `route()`, after `paths.append((path, net))` (line ~259), insert:

```python
        if net in recipe["inputs"]:
            placed.update(path)  # spine/branch cells are delivery: unrippable,
            # so gate rip-up can never orphan tap branches dark again.
```

Do NOT touch the rip guards (`c not in placed` at lines ~762/768/782/794) — skipping `placed` there is exactly the protection. Do NOT add gate paths to `placed` — gates stay rippable as today.

- [ ] **Step 4: Run probe + micro1 routing probe**

Run: `python scratch/probe_decay.py && python scratch/probe_taps.py` from `D:\redstone-mini`
Expected: decay-catcher green; taps probe still `routed` or `checker-stage only` (never `no route for`).

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "spine distribution: input delivery paths are unrippable"
```

---

### Task 4: Bridgeable spines + bridge-first for inputs

**Files:**
- Modify: `D:\redstone-mini\layout.py:707-718` (bridge-victim filters) and `~751` (pending-loop failure path)
- Test: micro1 full-verify probe (first end-to-end green candidate)

**Interfaces:**
- Consumes: Tasks 1-3 (ordered spine+taps, unrippable delivery); `try_bridge()`; `bridged` cap set; pending loop.
- Produces: gates bridge over spines when detour fails; input crossings hop before rip-up destroys routes.

- [ ] **Step 1: Write the micro1 end-to-end probe**

```python
# scratch/probe_spine.py (generic: python scratch/probe_spine.py micro1)
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from collections import Counter
from recipe import parse_recipe, expand_gates
from sim import layout_retry
name = sys.argv[1]
t0 = time.time()
r = parse_recipe(open(os.path.join(r"D:\redstone-mini", name + ".txt")).read())
b, s, io, st = layout_retry(r, verify=True)
gates = expand_gates(r["gates"], r["inputs"])
used = {a for g in gates for a in g["args"]} & set(r["inputs"])
c = Counter(io["levers"].values())
assert set(c) == used and all(v == 1 for v in c.values()), dict(c)
print(f"{name} OK blocks={len(b)} size={s} one-lever-everywhere t={time.time()-t0:.1f}s", flush=True)
```

- [ ] **Step 2: Run probe to verify it fails now**

Run: `python scratch/probe_spine.py micro1` from `D:\redstone-mini`
Expected: FAIL — `RuntimeError` (`no route for` / `OPEN` / `SHORT`) or sim mismatch. Record the message; it is the baseline this task must flip.

- [ ] **Step 3a: Allow placed wire as bridge victims**

At line ~708, replace `if c[1] == 1 and c not in placed:` with `if c[1] == 1:`.
At lines ~715-718, replace:

```python
                if c not in placed:
                    w = wires.get(c)
                    if w is not None and w != net:
                        cands.append((c[0], c[2]))
```

with:

```python
                w = wires.get(c)
                if w is not None and w != net:
                    cands.append((c[0], c[2]))
```

Do NOT touch the sort key at line ~720 (it still prefers non-placed victims — spines are hopped only when nothing better fits). Do NOT touch `bridge_free` — a bad hop still refuses on guard/solid footprints.

- [ ] **Step 3b: Bridge-first for input tasks**

In the pending loop, after the `except RuntimeError: pass` (~lines 750-751), insert before the `# targeted ripup` comment:

```python
            # ponytail: input spines bridge first (spec 2026-09-26-spine-fed-
            # input-distribution-design). Free corridor both sides, so the hop
            # fits; ripping first destroys good routes and ping-pongs loud.
            if net in recipe["inputs"] and try_bridge(s, t, net):
                continue
```

Gates keep rip-up-first (no gate behavior change).

- [ ] **Step 4: Run probe (micro1 must flip green)**

Run: `python scratch/probe_spine.py micro1` from `D:\redstone-mini`
Expected: `micro1 OK blocks=... size=... one-lever-everywhere t=...s`. If still red, diagnose with `python debug.py micro1.txt None 0` + dump inspection — do NOT proceed to Task 5 on red, and do NOT stack another fix: keep-or-revert this task first.

- [ ] **Step 5: Commit**

```bash
git add layout.py
git commit -m "spine distribution: bridgeable spines, bridge-first for inputs"
```

---

### Task 5: Scale to all builds + acceptance

**Files:**
- Modify: none unless the cap trigger fires (then `layout.py:704`, separate commit)
- Test: alu1 → suite → alu4/cpu4/ctrl_decode (background) → metrics → cap check

**Interfaces:**
- Consumes: Tasks 1-4 on green micro1.
- Produces: acceptance verdict (all builds green, one lever everywhere) or a diagnosed red with dumps.

- [ ] **Step 1: alu1 foreground probe**

Run: `python scratch/probe_spine.py alu1` from `D:\redstone-mini`
Expected: `alu1 OK ... one-lever-everywhere t=...s`. If red, stop: diagnose, do not scale.

- [ ] **Step 2: Full suite (small-build greens must hold)**

Run: `python recipe.py && python sim.py && python serve.py --check && python layout.py && python scratch/probe_panel.py` from `D:\redstone-mini`
Expected: every `ok` line prints (ports, or-lever, panel, bridge, tick, latch, crossover, comparator, serve demo, fanout shared-input + unused-leverless). Any red = stop and revert to the last green task.

- [ ] **Step 3: Dense builds as background jobs**

Run each launch from `D:\redstone-mini` (this machine's `Start-Process` lacks `-RedirectOutput`; the `cmd /c start /b` form detaches past shell exit):

```powershell
cmd /c "start /b python scratch/probe_spine.py alu4 > scratch/alu4_spine.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py cpu4 > scratch/cpu4_spine.log 2>&1"
cmd /c "start /b python scratch/probe_spine.py ctrl_decode > scratch/ctrl_spine.log 2>&1"
```

Poll (never block foreground on dense builds):

```powershell
Get-Content scratch/alu4_spine.log,scratch/cpu4_spine.log,scratch/ctrl_spine.log -ErrorAction SilentlyContinue
```

Expected: each log ends with `<name> OK blocks=... one-lever-everywhere t=...s`. Kill rule: no log output for 600s → confirm no other python work is running (`Get-Process python`), then stop the job and diagnose from the retry behavior.

- [ ] **Step 4: Bridge-cap check (measure, don't guess)**

For each dense build, count stamped bridges via a fresh dump (`python debug.py <recipe> <seed> 0` writes the planning frame even on failure) plus this exact query — bridge supports are the only headless cobble triples:

```python
python -c "import json; d=json.load(open(r'C:\Users\LOQ\AppData\Local\Temp\opencode\dbg_state.json')); s={(int(x),int(z)):v for k,v in d['solid'].items() for x,z in [tuple(map(int,k.split(',')))] if v[0]=='cobble'}; n=sum(1 for (x,z) in s if (x-1,z) in s and (x+1,z) in s) + sum(1 for (x,z) in s if (x,z-1) in s and (x,z+1) in s); print('support-triples~bridges:', n//3)"
```

Trigger (and only trigger) for a cap raise: a build routes everything except cap exhaustion. If and only if measured, replace `len(bridged) >= 24` with `len(bridged) >= 96` at `layout.py:704`, update the ponytail comment's ceiling line, re-run that build's probe, and commit separately:

```bash
git add layout.py
git commit -m "spine distribution: bridge cap 24->96 (measured exhaustion on <build>)"
```

- [ ] **Step 5: Record metrics + acceptance commit**

Append per-build results (blocks, size, wall time, bridges used) to `handoff.md`, extend `PONYTAIL-DEBT.md` with the two new real-ceiling rows (spine order + unrippable delivery, each with ceiling + upgrade), then:

```bash
git add handoff.md PONYTAIL-DEBT.md
git commit -m "spine distribution: acceptance metrics (<builds> green, one lever everywhere)"
```

Acceptance = Step 1-3 green + suite green + lever asserts green on all five builds. Anything else is red: no merge, diagnose with dumps.
