# Input Fanout Chaining Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let input nets with wide fanout use the existing buffer-relay machinery, so no input needs a 300-cell marathon.

**Architecture:** Two one-line deletions/relaxations in `recipe.py:expand_gates` (relay path only; the replication path keeps its exclusion because it indexes a driving gate inputs don't have), plus validation. No new tiles, no new physics, no router changes.

**Tech Stack:** Python 3, this repo only (`recipe.py`, `layout.py`, `sim.py`, existing scratch probes). Test style is repo convention: `python <file>.py` assert scripts, not pytest.

## Global Constraints

- cpu4 is the frozen holdout: no tuning to it, no reading its dumps to steer, until Task 6. Touching it earlier voids the proof.
- The four small builds stay byte-identical (`flat_hash.py` 4/4 vs HEAD). Any move must be explained by a newly-chained input or the task stops.
- `panel-wire` must pass on every chained build (single-lever proof, enforced not argued).
- No suite canary may rebuild a pinned dense green (it would go red spuriously on router improvements; the manifest is the record).
- `REDSTONE_XCHECK=1` stays on for any `forb` touch. (No `forb` touch is planned; this constraint is N/A unless a task adds one.)
- Kill-switches (stop + revert, a revert is a result): a canary breaks outside an intended placement shift; holdout fails AND synthetics don't improve; buffers overflow the grid past what a field-grow clears.
- Long runs never pipe through `Out-String` (it buffers everything and looks hung). Redirect to `$env:TEMP\opencode\*.log` via `Start-Process` and poll the log. Dense work runs serialized, one build at a time.

---

## File Structure

- Modify `D:\redstone-mini\recipe.py:156` — delete `and a not in inputs` so input nets enter relay fanout. (Line 102 keeps its exclusion: it feeds the replication path, which does `gates[outidx[n]]` at line 124, and an input has no driving gate — deleting there crashes with `KeyError`.)
- Modify `D:\redstone-mini\recipe.py:170` — relax `if len(bands_) < 2:` to `if len(bands_) < 2 and n not in inputs:` so single-band inputs get one shared buffer from the banded body instead of being skipped. (alu1's A/B loads are all band 1; without this the two failing nets get nothing.)
- Modify `D:\redstone-mini\recipe.py:97-98` — update the stale comment ("Inputs never chain either: layout taps every input load with its own lever (zero-wire)...") which is false since zero-wire taps were deleted.
- Modify `D:\redstone-mini\recipe.py` `__main__` — permanent `input-fanout ok` canary after the existing `_r2` fanout block (anchored at the `print("fanout ok: 3-load net chained, equivalent on all vectors")` line).
- Create (temporary, gitignored scratch): `D:\redstone-mini\scratch\chain_check.py` — TDD failing check, deleted after its assertion lands in `__main__`.
- Create (temporary, gitignored scratch): `D:\redstone-mini\scratch\synth_mut.py` — deterministic synthetic-recipe mutator for Task 5.
- Create: `D:\redstone-mini\greens.json` — pinned manifest, schema `{"<recipe>": {"seed": int, "grow": int, "blocks": int, "ticks": int, "hash": str}}` where `hash` is `hashlib.sha256(repr((blocks, size, io)).encode()).hexdigest()[:16]`, exactly as `scratch/flat_hash.py` computes it.

---

### Task 1: Enable input relay

**Files:**
- Modify: `D:\redstone-mini\recipe.py:156`
- Modify: `D:\redstone-mini\recipe.py:170`
- Modify: `D:\redstone-mini\recipe.py:97-98`
- Modify: `D:\redstone-mini\recipe.py` `__main__` (after the `_r2` fanout block)
- Create: `D:\redstone-mini\scratch\chain_check.py` (temporary)
- Test: `python scratch/chain_check.py`, then `python recipe.py`

**Interfaces:**
- Consumes: `expand_gates(gates, inputs)` signature unchanged; `fan`/`big`/`buf_of` internals unchanged.
- Produces: expanded gate lists in which an input feeding 3+ gates owns buffer gates `{"out": <T("bf") name>, "op": "AND", "args": [prev, prev], "band": <load band>}`, with the chain head's `args == [input, input]` and each load's arg rewritten to its buffer.

- [ ] **Step 1: Write the failing check**

```python
import sys
sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe, expand_gates
r = parse_recipe(open(r"D:\redstone-mini\alu1.txt").read())
gates = expand_gates([dict(g) for g in r["gates"]], r["inputs"])
heads = [g for g in gates if g["op"] == "AND" and g["args"][0] == g["args"][1]
         and g["args"][0] in r["inputs"]]
print("input-rooted buffer heads:", len(heads))
assert heads, "FAIL: no input-fed buffer chain (inputs excluded from fanout)"
print("chain ok: inputs relay")
```

Save as `D:\redstone-mini\scratch\chain_check.py`.

- [ ] **Step 2: Run it to verify it fails**

Run: `python scratch/chain_check.py`
Expected: prints `input-rooted buffer heads: 0` then `AssertionError: FAIL: no input-fed buffer chain (inputs excluded from fanout)`

- [ ] **Step 3: Make the minimal implementation**

Change 1 — `D:\redstone-mini\recipe.py:156`, delete the input exclusion so inputs enter relay fanout:
```python
            if a not in ("0", "1"):
```
(replacing `if a not in ("0", "1") and a not in inputs:`; line 102 is deliberately untouched — see File Structure.)

Change 2 — `D:\redstone-mini\recipe.py:170`, let single-band inputs through the banded body (one shared buffer for the group) instead of skipping them:
```python
            if len(bands_) < 2 and n not in inputs:
                continue
```
(replacing `if len(bands_) < 2:`; multi-band inputs already flow through the banded body unchanged.)

Change 3 — `D:\redstone-mini\recipe.py:97-98`, replace the stale comment with:
```python
    # Inputs chain too: they ride the router at real cost now (single-lever
    # panel deleted the zero-wire taps), so their marathons end the same way.
```

- [ ] **Step 4: Run the check to verify it passes**

Run: `python scratch\chain_check.py`
Expected: prints `input-rooted buffer heads: 4` (A, B, OP1, OP0; CIN feeds 2 gates so it passes through by the existing threshold) then `chain ok: inputs relay`

- [ ] **Step 5: Fold the assertion into `__main__` as the permanent canary**

After the existing `_r2` fanout block (anchored at `print("fanout ok: 3-load net chained, equivalent on all vectors")`), add:
```python
    _rin = {"inputs": ["s", "x", "y", "z"], "outputs": ["o"],
            "gates": [{"out": "o1", "op": "AND", "args": ["s", "x"]},
                      {"out": "o2", "op": "AND", "args": ["s", "y"]},
                      {"out": "o3", "op": "AND", "args": ["s", "z"]},
                      {"out": "o", "op": "OR", "args": ["o1", "o2"]}]}
    _ring = expand_gates([dict(g) for g in _rin["gates"]], _rin["inputs"])
    assert any(g["op"] == "AND" and g["args"] == ["s", "s"] for g in _ring), \
        "input fanout must chain"
    print("input-fanout ok: 3-load input relays")
```
Delete `D:\redstone-mini\scratch\chain_check.py` (its assertion now lives in `__main__`).

Run: `python recipe.py`
Expected: ends with both `fanout ok: 3-load net chained, equivalent on all vectors` and `input-fanout ok: 3-load input relays`, exit 0.

- [ ] **Step 6: Commit**

Run:
```bash
git add recipe.py
git commit -m "recipe: let input fanout relay (single-band inputs share one buffer)"
```

---

### Task 2: Suite and small-build validation

**Files:**
- Test: `python recipe.py`, `python layout.py`, `python sim.py`, `python serve.py --check`, `python scratch/flat_hash.py`
- Modify: none (verification only; any product change here means Task 1 is wrong — revert it instead)

**Interfaces:**
- Consumes: Task 1's expanded recipes.
- Produces: go/no-go per gate. Small builds whose inputs feed fewer than 3 gates are untouched BY CONSTRUCTION (threshold unchanged); any hash move must be explained by a newly-chained input or the task stops.

- [ ] **Step 1: Run the full gate set**

Run: `python recipe.py 2>&1 | Select-Object -Last 2`
Expected: ends with `input-fanout ok: 3-load input relays`

Run: `python layout.py 2>&1 | Select-Object -Last 2`
Expected: ends with `booster-side ok: no repeater cuts its own net, on all 4 small builds`

Run: `python sim.py 2>&1 | Select-Object -Last 1`
Expected: ends with `torch-burnout ok: hunting torch dies dark, loud`

Run: `python serve.py --check 2>&1 | Select-Object -Last 1`
Expected: ends with `serve ok: compiles demo (... blocks), routes + bad-recipe 400 verified` (block count may differ from 288; record the number, do not assert it)

- [ ] **Step 2: Compare small-build hashes to HEAD**

Run: `python scratch/flat_hash.py > "$env:TEMP\opencode\h_chain.txt" 2>&1`
Then compare element-wise against the HEAD baseline (`fd9c0a49...` / `3fce63bc...` / `d9b741e5...` / `5aed1dce...` for `example_and` / `example_2gates` / `latch_sr` / `example_xor`).
Expected: 4/4 identical. Their inputs feed fewer than 3 gates each, so no buffer is created and nothing may move. If any hash moves, identify the newly-chained input from the expanded recipe; if there is none, Task 1 is wrong — revert it, do not proceed.

- [ ] **Step 3: Commit nothing**

This task produces evidence, not code. Record the gate outputs and hash comparison in the handoff later (Task 6). If all green, proceed; no commit here.

---

### Task 3: micro1 regression and panel proof

**Files:**
- Test: `python scratch/seed2.py 3 5`, `python layout.py` (panel-wire lines), `REDSTONE_XCHECK=1` run on any green build

**Interfaces:**
- Consumes: Task 1's chained expansion.
- Produces: micro1 still generates (green count, seeds may differ — buffers move placement, so same-seed identity is NOT required; green RATE is the criterion) plus `panel-wire ok` on chained builds.

- [ ] **Step 1: Check the known greens**

Run: `python scratch/seed2.py 3 5`
Expected: verdict lines for both seeds. Either GREEN is fine; a `no route` / `SIM-FAIL` here is not yet a failure — seeds move when placement moves. Record both verdicts verbatim.

- [ ] **Step 2: Measure the green rate**

Run the 12-seed ladder streaming to a log (never through `Out-String`):
```powershell
$env:LADDER_GROW="1"; $log="$env:TEMP\opencode\chain_micro.log"
Start-Process -FilePath python -ArgumentList "scratch/ladder2.py","3000","0","12","D:\redstone-mini\micro1.txt" -WorkingDirectory D:\redstone-mini -RedirectStandardOutput $log -NoNewWindow
```
Poll `$log` until all 12 seeds report. Baseline from the handoff: 2/12 green (s3, s5), 5 no-route, 2 SIM MISMATCH, 1 OPEN, 2 repeater-loop.
Expected: green count ≥ 2 with no new failure class. If green count is 0, or a new loud failure class appears that traces to buffer placement, Task 1 is wrong for micro1 — revert it, do not proceed.

- [ ] **Step 3: Confirm the panel proof held**

In the `python layout.py` output from Task 2, confirm the lines `panel-wire ok: no lever shorts a 2nd net, every load fed by its one lever` and `xor-lever ok: one lever per input, verify green` are present. These walk the real net graph including the new chains; their presence IS the single-lever proof. If either is absent or red, stop — the design's §2 has failed.

- [ ] **Step 4: Commit nothing**

Evidence only. Proceed to Task 4 if green count ≥ 2 and panel-wire passes.

---

### Task 4: Development-recipe ladders

**Files:**
- Test: `python scratch/ladder2.py` per recipe (streaming to logs, serialized — never two dense runs at once)

**Interfaces:**
- Consumes: Task 1's chained expansion.
- Produces: per-recipe green counts and failure classes vs handoff baselines. Kill-switch evaluation lives here.

- [ ] **Step 1: alu1 ladder**

Run grow=1, cap 3000, seeds 0–11 streaming to `$env:TEMP\opencode\chain_alu1.log` (same `Start-Process` pattern as Task 3). Baseline: 0/12, all `no route for A`/`B`.
Expected: any GREEN, or failure classes that name buffer-adjacent cells (evidence the chains engage). If 0/12 with the same input-marathon verdicts verbatim, chaining did not engage alu1's wall — record it and continue to alu4/ctrl_decode before judging (one recipe is not the verdict).

- [ ] **Step 2: alu4 and ctrl_decode ladders**

Same harness, one recipe at a time, grow=1, cap 3000, seeds 0–5 (6 seeds each is enough for a verdict; full 12 only if green is near). Baselines: alu4 shares alu1's wall post-placement-fix; ctrl_decode 0/4 on OP0/OP1 crossings.
Expected: same criterion as Step 1.

- [ ] **Step 3: Evaluate the kill-switch**

Revert Task 1 if ALL of these hold: zero greens across all three recipes, zero near-misses (no fully-routed-but-wrong build naming a buffer-adjacent defect), and any NEW loud failure class that traces to buffer placement. If any recipe greens or near-misses, proceed to Task 5. Record the verdict table in the handoff (Task 6 covers the commit).

---

### Task 5: Synthetic paired comparison

**Files:**
- Create: `D:\redstone-mini\scratch\synth_mut.py` (temporary measurement script)
- Test: `scratch/synth_before.csv` vs `scratch/synth_after.csv` (temporary logs)

**Interfaces:**
- Consumes: Task 1's code change (present for "after", stashed for "before").
- Produces: paired green-rate comparison per recipe family. Strict improvement required; a tie or regression fails the generality claim.

- [ ] **Step 1: Write the mutator**

```python
"""Deterministic synthetic recipes by small mutation. Usage:
python scratch/synth_mut.py <recipe> <count> <outdir>
Writes <outdir>/<recipe>_s<k>.txt. Mutations preserve BAND lines and validity:
op-swap one gate (AND<->OR), add one AND gate of two live nets in a random
existing band, or widen one input's fanout by one gate. Seeded, reproducible.
"""
import os
import random
import sys
sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe

def live_nets(gates, inputs):
    seen = list(inputs)
    for g in gates:
        seen.append(g["out"])
    return seen

def mutate(text, rng):
    lines = [l for l in text.splitlines() if l.strip()]
    hdr = [l for l in lines if l.startswith(("IN ", "OUT ", "BAND "))]
    body = [l for l in lines if "=" in l and not l.startswith(("IN ", "OUT ", "BAND "))]
    ins = [s.strip() for s in next(l for l in hdr if l.startswith("IN "))[3:].split(",")]
    outs = [s.strip() for s in next(l for l in hdr if l.startswith("OUT "))[4:].split(",")]
    gates = []
    for b in body:
        o, e = b.split("=", 1)
        op = "AND" if " AND " in e else ("OR" if " OR " in e else ("XOR" if " XOR " in e else "NOT"))
        args = [a.strip() for a in e.replace(" AND ", ",").replace(" OR ", ",").replace(" XOR ", ",").replace("NOT ", "").split(",") if a.strip()]
        gates.append({"out": o.strip(), "op": op, "args": args})
    k = rng.randrange(3)
    nets = live_nets(gates, ins)
    if k == 0:
        g = rng.choice([g for g in gates if g["op"] in ("AND", "OR")])
        g["op"] = "OR" if g["op"] == "AND" else "AND"
    elif k == 1:
        a, b = rng.sample(nets, 2)
        gates.append({"out": f"m{rng.randrange(100, 999)}", "op": "AND", "args": [a, b]})
    else:
        g = rng.choice(gates)
        g["args"].append(rng.choice(nets))
    blines, bi = [], 0
    for l in lines:
        if l.startswith("BAND "):
            bi += 1
            blines.append(l)
        elif "=" in l and not l.startswith(("IN ", "OUT ", "BAND ")):
            blines.append(l)
    out = [f"IN {', '.join(ins)}", f"OUT {', '.join(outs)}", "BAND 0"]
    for g in gates:
        out.append(f"{g['out']} = {' '.join([g['args'][0], g['op']] + g['args'][1:]) if len(g['args']) > 1 else f\"NOT {g['args'][0]}\"}")
    return "\n".join(out) + "\n"

if __name__ == "__main__":
    src, n, outdir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    os.makedirs(outdir, exist_ok=True)
    text = open(rf"D:\redstone-mini\{src}.txt").read()
    for k in range(n):
        open(os.path.join(outdir, f"{src}_s{k}.txt"), "w").write(
            mutate(text, random.Random(1000 + k)))
    print(f"wrote {n} synthetics for {src} -> {outdir}")
```

- [ ] **Step 2: Generate the fixture set (once, reused for both measurements)**

Run: `python scratch/synth_mut.py alu1 6 C:\Users\LOQ\AppData\Local\Temp\opencode\synth`
Expected: `wrote 6 synthetics for alu1 -> ...`. Repeat for `micro1` and `ctrl_decode` (6 each, 18 total). Verify one file parses: `python -c "import sys; sys.path.insert(0,r'D:\redstone-mini'); from recipe import parse_recipe; print(len(parse_recipe(open(r'C:\Users\LOQ\AppData\Local\Temp\opencode\synth\alu1_s0.txt').read())['gates']))"` — must print a gate count, not raise.

- [ ] **Step 3: Measure BEFORE (stashed) and AFTER (current)**

Run each synthetic through a bounded attempt and record green/red per file. Bound every attempt identically: `layout()` seed=0 grow=1, `REDSTONE_SEARCH_CAP=3000`, then `sim_verify` if routing succeeds; record GREEN only if both pass.
```powershell
git stash -q
python scratch/synth_run.py C:\Users\LOQ\AppData\Local\Temp\opencode\synth "$env:TEMP\opencode\synth_before.csv"
git stash pop -q
python scratch/synth_run.py C:\Users\LOQ\AppData\Local\Temp\opencode\synth "$env:TEMP\opencode\synth_after.csv"
```
`scratch/synth_run.py` (write it in this step, ~25 lines: loop files, try layout+verify with the bounds above, write `file,verdict` rows, flush per row). Both CSVs must cover the same 18 files.
Expected: `synth_after.csv` green count strictly exceeds `synth_before.csv` per parent family. A tie or regression fails the generality claim — revert Task 1.

- [ ] **Step 4: Commit nothing**

Evidence only. The CSVs stay gitignored in Temp. Proceed to Task 6 only on strict improvement.

---

### Task 6: Holdout, manifest, and final commit

**Files:**
- Test: cpu4 single `layout_retry` run (streaming log; frozen recipe, no cpu4-specific changes anywhere — enforced by code review of Tasks 1–5 touching only generic paths)
- Create: `D:\redstone-mini\greens.json`
- Modify: `D:\redstone-mini\handoff.md` (record results)

**Interfaces:**
- Consumes: all prior tasks green.
- Produces: cpu4 verdict, pinned manifest, pushed commits. Done means the spec's acceptance clause holds or the kill-switch fired.

- [ ] **Step 1: Run the holdout once**

Run cpu4 through the shipping entry point, streaming, in the background (it costs minutes per attempt; never in the foreground):
```powershell
$log="$env:TEMP\opencode\holdout.log"
Start-Process -FilePath python -ArgumentList "-c","import sys,time; sys.path.insert(0,r'D:\redstone-mini'); from recipe import parse_recipe; from sim import layout_retry; r=parse_recipe(open(r'D:\redstone-mini\cpu4.txt').read()); t0=time.time(); o=layout_retry(r,verify=True); print('cpu4 %d blocks ticks=%d %.0fs' % (len(o[0]),0,time.time()-t0))" -WorkingDirectory D:\redstone-mini -RedirectStandardOutput $log -NoNewWindow
```
Poll `$log` to completion. Expected: a verified build, with zero cpu4-specific code or probe changes in the tree (`git diff --stat` must show only `recipe.py` plus docs). If it fails, the generality claim fails — revert Task 1 per kill-switch (2), record the wall as measured.

- [ ] **Step 2: Write the manifest**

For every recipe that verified (development greens from Tasks 3–4 plus the holdout), record the winning configuration. The winner is the first GREEN line in each recipe's ladder log (seed from the log line, grow from the `LADDER_GROW` used). Rebuild byte-identity check per entry with the exact `flat_hash.py` computation:
```python
import hashlib
h = hashlib.sha256(repr((blocks, size, io)).encode()).hexdigest()[:16]
```
Write `D:\redstone-mini\greens.json`:
```json
{"micro1": {"seed": 3, "grow": 1, "blocks": 2452, "ticks": 42, "hash": "<measured>"},
 "alu1": {"seed": "<from log>", "grow": 1, "blocks": "<measured>", "ticks": "<measured>", "hash": "<measured>"}}
```
One entry per verified recipe; omit unverified ones (do not record reds as pins). Rebuild one entry by hand to prove the loop closes:
```python
import sys; sys.path.insert(0, r"D:\redstone-mini")
from recipe import parse_recipe
import layout as L
from sim import sim_verify
r = parse_recipe(open(r"D:\redstone-mini\micro1.txt").read())
out = L.layout(r, seed=3, grow=1)
st, ticks = sim_verify(r, out[0], out[2], quiet=True, collect=True)
print("rebuild ok:", len(out[0]), ticks)
```
Expected: same blocks and ticks as the manifest entry.

- [ ] **Step 3: Update the handoff and commit**

Record in `handoff.md` under Current state: per-recipe verdicts, the manifest path, synthetic before/after counts, holdout verdict, and any spec deviations taken during planning (line 102 keeps its exclusion — replication indexes a driving gate; single-band inputs take the banded body as one shared buffer — these refine §1's letter, not its intent).
```bash
git add recipe.py handoff.md greens.json
git commit -m "recipe: let input fanout relay (single-band inputs share one buffer)"
git push origin phase2-design
```

---

## Self-Review

**1. Spec coverage:** §1 chaining policy → Task 1 (with the two correctness refinements: line 102 untouched to avoid the `outidx` KeyError, single-band fallthrough via the banded body). §2 panel preservation → Task 3 Step 3 (`panel-wire ok` enforced, not argued). §3 validation: holdout → Task 6 Step 1; synthetics → Task 5 (paired, strict improvement); gates → Task 2. §4 scope: the plan touches only `recipe.py` plus docs/measurements; task order, bank, corridors, field shaping, Q-track, cpu4 tuning, and rate floors appear nowhere. Pinning (manifest only, no suite rebuilds) → Task 6 Step 2.

**2. Placeholder scan:** every code step shows complete code (mutator, canary, assertions, commands with expected outputs). No TBD/TODO/"appropriate handling" language. The one judgment call left to the implementer (which existing `_r2` line anchors the canary) names the exact anchor string to find.

**3. Type consistency:** gate dicts use `out`/`op`/`args`/`band` throughout, matching `recipe.py`; buffer shape `{"out", "op": "AND", "args": [prev, prev], "band"}` matches lines 190–191 verbatim; manifest hash matches `flat_hash.py`'s computation verbatim; `expand_gates(gates, inputs)` signature matches line 82.

Plan complete and saved to `docs/plans/2026-09-27-input-fanout-chaining.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
