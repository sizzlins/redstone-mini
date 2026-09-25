# Phase 1 Tiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lock the Phase 1 port grid (spec table + east-first lamps + drift asserts) with zero tile respins.

**Architecture:** Two one-spot edits in `layout.py` (lamp direction order; new `__main__` self-check), verified by the repo's existing assert-and-print harness convention (`python <file>` prints ok). No new files, no physics changes.

**Tech Stack:** Python 3, stdlib only. No dependencies added.

## Global Constraints

- No tile respins: stamp geometry (`stamp_and`, NOT/NOR/LATCH/XOR branches) is byte-untouched.
- Spec source of truth: `docs/phase1-standard-tiles.md` (port table + pitches).
- Test style: assert-based `__main__` blocks run via `python <file>`, matching `recipe.py`/`sim.py`/`serve.py`.
- Minecraft target: Java Edition 1.20–1.21 (min 1.13 for `setblock` state syntax).

---

### Task 1: East-first lamp placement

**Files:**
- Modify: `D:\redstone-mini\layout.py` (output lamp loop, `for dx, dz in ((1, 0), (0, 1), (-1, 0), (0, -1)):`)
- Test: `D:\redstone-mini\layout.py` (`__main__`, added in Task 2; interim check below)

**Interfaces:**
- Consumes: nothing new (existing `pos`, `solid`, `wires`, `rings` locals).
- Produces: lamp cells preferring east; `io["lamps"]` unchanged in shape (`{(x, z): net}`).

- [ ] **Step 1: Record current lamp cells (characterization lock)**

```bash
cd "D:\redstone-mini" && python -c "import sys; sys.path.insert(0, r'D:\redstone-mini'); from recipe import parse_recipe; from sim import layout_retry; r = parse_recipe(open('latch_sr.txt').read()); print(sorted(layout_retry(r, verify=True)[2]['lamps'].items()))"
```

Expected: prints one lamp cell, e.g. `[(...)]` (any coords — record them).

- [ ] **Step 2: Flip the direction order (one line)**

```python
        for dx, dz in ((1, 0), (0, 1), (0, -1), (-1, 0)):
```

(Replaces `((1, 0), (0, 1), (-1, 0), (0, -1))`: west moves last so outputs never face backward into producers.)

- [ ] **Step 3: Re-run Step 1, compare lamp cells**

Run: same command as Step 1.
Expected: same cell (east was already free here) or a north cell where west was taken before — either way `layout_retry` verifies clean.

- [ ] **Step 4: Commit**

```bash
cd "D:\redstone-mini" && git add layout.py && git commit -m "lamps prefer east, never face producers first"
```

### Task 2: Port-grid drift asserts in `layout.py.__main__`

**Files:**
- Modify: `D:\redstone-mini\layout.py` (append `__main__` block; file has none today)
- Test: same file (`python layout.py` must print ok)

**Interfaces:**
- Consumes: `layout()`, `parse_recipe`, `eval_net` (existing imports in worker scope).
- Produces: nothing (assert-only block).

- [ ] **Step 1: Write the self-check (fails on drift, passes today)**

```python
if __name__ == "__main__":
    # ponytail: ONE runnable check — port grid spec (docs/phase1).
    # Asserts each tile's ports sit at spec offsets from its out stub.
    # (NOR has no recipe syntax — reachable only via banded OR expansion,
    # so it's covered indirectly whenever a banded build verifies.)
    from recipe import parse_recipe, eval_net
    from sim import layout_retry
    _r = parse_recipe("IN a, b\nOUT y, z, w\n"
                      "n = NOT a\nt = a AND b\nl = t OR n\n")
    _blocks, _size, _io, _ = layout_retry(_r, verify=True)
    _nets = _io["nets"]
    assert _io["lamps"], "lamp missing"
    # NOT out is the easternmost "n" cell; port sits 3 west, net "a".
    _nx = max(c[0] for c, v in _nets.items() if v == "n")
    _nz = [c[2] for c, v in _nets.items() if v == "n" and c[0] == _nx][0]
    assert _nets.get((_nx - 3, 1, _nz)) == "a", "NOT port drifted"
    # AND out is the easternmost "t" cell; A-port 8 west 1 north (net
    # "a"), B-port 8 west 2 south (net "b").
    _tx = max(c[0] for c, v in _nets.items() if v == "t")
    _tz = [c[2] for c, v in _nets.items() if v == "t" and c[0] == _tx][0]
    assert _nets.get((_tx - 8, 1, _tz - 1)) == "a", "AND A-port drifted"
    assert _nets.get((_tx - 8, 1, _tz + 2)) == "b", "AND B-port drifted"
    print("ports ok: AND/NOT grid matches spec")
```

Run: `cd "D:\redstone-mini" && python layout.py`
Expected: prints `ports ok: ...` (asserts hold on current geometry).

- [ ] **Step 2: Verify it catches drift (negative control)**

Run: temporarily change one `assert` RHS (e.g. expect `"zzz"`), run `python layout.py`.
Expected: FAIL with AssertionError. Revert the sabotage.

- [ ] **Step 3: Commit**

```bash
cd "D:\redstone-mini" && git add layout.py && git commit -m "port-grid drift asserts"
```

### Task 3: Full suite green + push

**Files:**
- Modify: none (verification only).

- [ ] **Step 1: Run the suite**

```bash
cd "D:\redstone-mini" && python recipe.py && python serve.py --check && python sim.py
```

Expected: all three print their ok lines (`minimize ok`, `serve ok`, `comparator ok` etc.).

- [ ] **Step 2: Run the build proofs (4-gate, demo, micro1)**

```bash
cd "D:\redstone-mini" && python redstone_mini.py
```

Expected: `ok: 114 blocks -> build.html + build.mcfunction`. Then re-export micro1 (`python -u scratch/exportmicro.py`) since demo overwrites `build.html`, and confirm `micro1 ok`. Then verify the 4-gate latch still routes clean on 6 seeds with a correct hold sequence:

```bash
cd "D:\redstone-mini" && python -u scratch/check4gate.py
```

Expected: `4-gate bad: 0 /6` plus `sequence ok`. (`scratch/check4gate.py` is a 20-line helper the worker writes first: layout the 4-gate recipe from `docs/phase1-standard-tiles.md` on seeds None/0/1/2/7/42, sim-check every defined vector via `eval_net`, then `sim_sequence` set/hold/reset/hold — mirroring the latch proof in `sim.py.__main__`.)

- [ ] **Step 3: Push**

```bash
cd "D:\redstone-mini" && git push origin master && git log --oneline -2 && git status --short
```

Expected: push succeeds, worktree clean.
