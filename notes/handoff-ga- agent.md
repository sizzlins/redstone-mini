# handoff — 2026-10-04 night (GA agent): vanilla rig is not an oracle; dual-engine gate + a real sim bug fixed

Repo: `D:\redstone-mini`, branch `phase2-design`.

**Note on this file:** it was byte-identical to `notes/handoff-opt agent.md`
(the opt agent's session record). Their copy is intact; this is now mine.

My commits this session (in order):

| commit | what |
|---|---|
| `14697e7` | rig: vanilla servers do not propagate power from `setblock` → drop live-rig-as-oracle |
| `38b872f` | **sim+simvec: a dust cell in front of a comparator must OR its other sources** (real bug) |
| `4b8de55` | re-baseline frozen `ref_sim.py` to that fix |
| `c110299` | LOG: the differential + the fix |
| `85d74cd` | note to opt agent |
| `sweep.py` (uncommitted at time of writing) | dual-engine sweep over every banked pkl |

`fe71ca1`, `a5ee1ef`, `470c84c` are the **opt agent's** — do not read those as mine.

---

## Goal

Standing goal unchanged: every recipe in `recipes/` generates, verifies and
exports, with evidence that survives an independent implementation.

Tonight's goal was the **verification layer**, because I had just discovered
the RCON rig's verdicts were meaningless. Two outcomes:

1. Establish whether the live vanilla rig can be an oracle at all.
2. If not, replace it with something trustworthy, and use it.

**Outcome: (1) no — the rig is fundamentally unusable here. (2) done — and it
immediately paid for itself by finding a real physics bug in our own sim.**

---

## Current state

### The vanilla rig cannot serve as ground truth

Measured identically on vanilla **26.3** (the jar we already had) and on a
fresh **Mojang 1.21.11** (SHA1-verified `64bb6d76…`, installed at
`D:\put gitrepos here\mc-server-1.21`, rcon 25576 / port 25566, so the 26.3
server was left alone):

| probe | result | vanilla says |
|---|---|---|
| redstone block directly under a lamp | lamp `lit=false` | **lit** |
| redstone block adjacent to dust | dust `power=0` | **15** |
| wall lever → host block → dust on top (our own `_lp3` canary, verbatim) | dust `power=0` | **15** |
| redstone block directly behind a repeater, lamp in front | no output, `powered=false` | output |
| comparators, all modes/delays/orders | `OutputSignal: 0` | output |

Every cell verified present with `execute if block` before and after, so it is
not a placement artifact. And the servers are **alive**: `time query gametime`
advances ~20 tps, java CPU climbs, and a redstone torch correctly burns out
when its block is powered and re-lights when unpowered. Scheduled ticks run.

Two independent Mojang jars behave identically, so it is not a bad download.
**Conclusion: do not spend more time on the live rig.** The reason our earlier
rig numbers looked like a physics divergence is mundane — see "what failed".

### Verification is now sim + cmc

| build | sim | cmc | per-cell diff |
|---|---|---|---|
| add2opt (`recipes/add2.txt`, `compact_add2/best.pkl`, 3730 blk) | 16/16 | 16/16 | **0 / 25872** dust, 0 / 3584 repeaters |
| alu1glass (13300 blk) | 32/32 | 32/32 | **0 / 179296**, 0 / 25728 |
| alu4glass7 / alu4merge / alu4merge_g / alu4_av7 / alu4merge.preflip / alu4fix | green | green | 0 diff |
| `compose_check.py` | unchanged 144/322/224/214 | — | — |
| `python sim.py` | green (+1 new canary) | — | — |
| `scratch/diff_engine.py` | ALL IDENTICAL after re-baseline | — | — |

### Sweep in flight (41/42 done when this was written)

`scratch/sweep.py --max-vectors 4 --diff` auto-matches each pkl to a recipe by
its **io pin names** (so a stale pkl cannot be scored against the wrong
recipe — that mistake briefly made `alu4_build.pkl` look like a physics
failure). **`diff=0` on every single build that ran** — the comparator fix was
the only physics disagreement between the two engines.

---

## What changed

### 1. `sim.py` + `simvec.py` — a real bug, found without the game

`sim.py dust_lvl()`:

```python
if m in comp:
    md = comp[m]
    if (m[0] - md["rear"][0], m[1], m[2] - md["rear"][1]) == c:
        return con.get(m, 0)      # <-- early return
```

The dust cell on a comparator's **output** side took the comparator's level as
its *only* input, so it read `0` whenever the comparator was off — even with a
15-level dust wire next to it pointing at it. **Vanilla ORs every contribution
to a cell**, so the game powers that wire and the sim did not.

`simvec.py` carried the identical early return (its own comment said
`# early return: discards lv, as upstream`), so both changed together — the
mirror is a hard requirement or `diff_engine` diverges.

Fixed to `lv = max(lv, con.get(m, 0))`, plus a new canary `comp-front-dust ok`
next to the existing `comp-side-dust ok`. The old canary only asserted the
comparator's *own output level*, which is exactly why it never covered this.

**Fingerprint on add2opt:** 3 cells, 9 of 16 vectors, always `sim=0 cmc=14`,
all one motif — a dust cell sandwiched between a powered dust and a
`facing=east` comparator: `(197,1,57)`, `(228,1,26)`, `(48,1,26)`.

**Why it matters:** this is the same family as the anomaly the opt agent found
live (compact deck, nets B0/B1). A build that routes power through a wire
running past a comparator side was green in our sim and would wire
differently in the game. That is the sim-overfit class, now caught
mechanically instead of by argument.

**Reproducer:** `python scratch/motif.py` — 6 cells, 4 variants,
3/4 divergent before → 0/4 after.

### 2. `scratch/verify2.py` — the dual-engine gate (new)

```
python scratch/verify2.py <recipe.txt> <build.pkl> [--diff-all] [--vec N]
                          [--ticks N] [--max-vectors N]
                          [--sim-timeout S] [--cmc-timeout S]
```

Runs our sim **and** cmc, each in a child process under a hard timeout, then
diffs them **per cell** (every dust level and repeater state, per vector), not
just the lamps. Exit 0 only if both engines pass every vector and the per-cell
diff is empty. Writes `<doc>.verdict.json`.

Why per cell and not lamps: both engines already agreed on lamps for every
banked build, so a lamp-only gate is structurally incapable of seeing this
class of bug. The per-cell diff is the only thing that found it.

Supporting changes:
- `scratch/cmc_harness.mjs` — added `--dump-cells/--dump-vec/--dump-all`
  (emits per-cell dust power and repeater power from cmc).
- `scratch/sweep.py` — runs the gate over every banked pkl with automatic
  recipe matching by pin names.
- `scratch/diffwhy.py`, `scratch/simwhy.py` — triage: which cells, which
  vectors, and the block neighbourhood with both engines' values.

**No-hang guarantee:** every external process runs under `subprocess` timeout;
the parent adds a further deadline; every script has a `__main__` guard.

### 3. `scratch/rig_verify.py` (kept, but the rig is not an oracle)

Changes are still correct and worth keeping: `execute store success` +
`scoreboard players get` as the only RCON-visible read channel, per-vector
poll-to-stable settling instead of a fixed sleep, post-`/reload` seed-probe
gate, `forceload query` verification, a floor-cell paste gate ("no floor, no
vectors"), and now creates the `__rig` objective.

---

## What failed, and why (so it is not re-derived)

| attempt | result | lesson |
|---|---|---|
| Trust the vanilla rig's lamp verdicts | Chased a "physics divergence" for hours | the server never propagated power; every number was fiction |
| Chasing the rig divergence as a sim bug via `dustcmp` | 1090/1617 "mismatches" | my probe read only levels 15/1/0 (any 2..14 read as a mismatch), **and** I compared an all-ones sim table against a world left at B1-only by my own earlier probe. Both faults mine. |
| "Repeaters are dead in 26.3" | True but unprovable there | two more false verdicts followed: the `__rig` scoreboard objective did not exist on the fresh 1.21.11 server, so *every* read silently returned "absent"; and `setblock` dust is deleted without a supporting block, so 3 of my own controls were invalid |
| Fixing the rig by disabling the server pause | Helped (ticks resumed) but not enough | `pause-when-empty-seconds=60` was real and worth fixing, but power propagation is broken independently of it |
| `alu4_build.pkl` + `recipes/alu4.txt` | Both engines red (8/16, Y2 stuck true) | **stale artifact, not a regression** — fails identically on the pristine engine. `alu4glass7.pkl` is the green one. Worth reconciling with the opt agent's "alu4 1024/1024" claim. |
| `cpu4retry_merge.pkl` (129953 blk) | sim raises `TORCH BURNOUT`, cmc says green | by-design sim guard; verify2 now reports a raised engine as a first-class verdict instead of a bare `None` |
| Downgrading to 1.21.11 to "fix" the rig | Did not fix it | two Mojang jars, same behaviour ⇒ environment/server-class issue, not a version regression. The download was still worth it as an independent control. |

### Four measurement traps that each produced a false verdict

1. `pause-when-empty-seconds=60` — server stops ticking with no player;
   scheduled redstone freezes while instant neighbour updates keep working.
   Symptom looked exactly like a physics divergence (early vectors failing,
   later ones passing). Check `latest.log` for "Server empty … pausing".
2. `setblock` redstone dust is **silently deleted** without a supporting block
   (vanilla `canSurvive`, but it reports success first). Any paste must give
   dust a floor.
3. The scoreboard readback channel returns `0` if the `__rig` objective does
   not exist → every probe reads "block absent".
4. `wire[power=N]` is an exact match (no `>=` form), so any probe that only
   tests 15/1/0 mislabels every mid-range cell.

---

## Files I touched

**Shared-core, changed deliberately (reviewable, revertible):**

| file | change |
|---|---|
| `sim.py` | one line (`return` → `max`) + one canary `comp-front-dust ok` |
| `simvec.py` | the mirrored one line |

**Mine (gitignored `scratch/`, force-added):**

| file | what |
|---|---|
| `scratch/verify2.py` | the dual-engine gate + per-cell diff |
| `scratch/sweep.py` | gate sweep over all banked pkls, recipe auto-match |
| `scratch/motif.py` | 6-cell reproducer for the comparator bug |
| `scratch/diffwhy.py`, `scratch/simwhy.py` | differential triage |
| `scratch/cmc_harness.mjs` | `--dump-cells/--dump-vec/--dump-all` |
| `scratch/ref_sim.py` | re-baselined via `mkref.py` (extracts from HEAD) |
| `scratch/rig_verify.py` | readback channel, poll-to-stable, gates, `__rig` |
| `scratch/sanity.py` `retain.py` `sup.py` `leverrep.py` `raw.py` `four.py` `ctrl2.py` `controls.py` `ab.py` | the evidence scripts — each reproduces one of the four traps above |

**Docs:** `LOG.md` (two appended sections), `notes/to-opt-agent.md`
(Notes 3 and 4, append-only), this file.

**Explicitly NOT touched:** `dustcmp.py`, `evo_*`, `compact.py`, `enum_*`,
`verify_par.py`, `bench_scalar.py`, `prof_scalar.py`, `compose.py`.
Reference repos read-only.

---

## What we should do next

1. **Finish the sweep and read `scratch/sweep.json`.** Green in both engines
   and zero-diff is now the admission ticket for a banked build. Anything with
   `sim=True cmc=False` (e.g. `alu4mergeNEW`, `alu4mergeNEW4`) is the
   interesting class: our sim accepts it and the independent engine does not.
2. **Reconcile the alu4 artifacts.** `alu4_build.pkl` and `alu4bank.pkl` are
   red in both engines; `alu4glass7.pkl` is green. Establish which pkl the
   "1024/1024" claim rests on and mark the stale ones (no deleting — the
   no-delete rule stands).
3. **Wire the gate into the bank path.** A build should not be exported without
   `verify2.py --diff-all` green. That is the durable fix for the whole class
   of sim-overfit bugs, and it is what would have caught the comparator rule
   before it reached a banked artifact.
4. **Torchless 1-bit full adder is still open** (NOT is proven impossible:
   2/2, 12 cells, width 3, 527 candidates). XOR/AND unfound after ~100k evals.
   The gate makes it safe to search now — but note `evo_*`/`compact.py` belong
   to the other agent, so coordinate before touching that search.
5. **Decide the vanilla rig's fate.** Two servers are staged and idle. Without
   a client that can place blocks by hand, neither can be pushed further;
   keeping them costs only disk. If a real client paste is ever wanted, that is
   the only path that would settle vanilla-vs-sim questions.
6. **Coordination:** opt agent owns compose/sim/compose_check; I now also hold
   `sim.py`/`simvec.py` (one line each, canaried, committed). Re-agree scopes.
