# Morning report

Overnight autonomous session on `D:\redstone-mini`, branch `phase2-design`.
Started from 2/5 dense green. Nothing is committed that isn't verified.

## DONE bar

**1. All dense recipes build and verify** — 13 of 17 do. Four are still red,
each with an identified wall (details below). Not fully met.

**2. 3+ new dense builds that never built before** — **met, with margin: 6.**

| new recipe | what it is | blocks | size |
|---|---|---|---|
| `sub2.txt` | 2-bit subtractor with borrow out | 3487 | 187x129 |
| `mux4.txt` | 4-bit 2:1 mux, 9 inputs | 20239 | 991x106 |
| `andor8.txt` | 8-input AND tree + 8-input OR tree | 17997 | 739x117 |
| `decode3.txt` | 3-to-8 decoder | 9799 | 541x99 |
| `add2.txt` | 2-bit adder (corrected carry) | 12539 | 689x87 |
| `chainmix.txt` | 24-gate logic chain | 11497 | 415x273 |

`mux4` at 20239 blocks is now the largest build in the repo.

## Verified green (authoritative: compose -> maze -> verify)

All via `tools/gate.ps1` (parallel, hard-bounded, exit 1 iff anything is red).

```
add2.txt         OK    12539 blocks  (689, 87)    16.2s
alu1.txt         OK    13300 blocks  (359, 140)  127.6s   <- was RED
andor8.txt       OK    17997 blocks  (739, 117)  170.1s   <- NEW
chainmix.txt     OK    11497 blocks  (415, 273)    5.2s
ctrl_decode.txt  OK     5501 blocks  (341, 86)    18.5s
decode3.txt      OK     9799 blocks  (541, 99)    59.5s
example_2gates   OK      322 blocks  (44, 36)      0.1s
example_and.txt  OK      144 blocks  (28, 24)      0.0s
example_xor.txt  OK      214 blocks  (24, 30)      0.0s
latch_sr.txt     OK      224 blocks  (28, 31)      0.1s
micro1.txt       OK     2925 blocks  (173, 89)     2.0s
mux4.txt         OK    20239 blocks  (991, 106)  150.5s   <- NEW
sub2.txt         OK     3487 blocks  (187, 129)  106.9s   <- NEW
```

`alu1` went from red to green. That is the one previously-"hard" build the
session cracked.

## Still failing, with logs

### cmp2.txt -- compose wall, budget-sensitive
```
compose long spread 10 gates_first failed (compose: no ground for A0: (-43,-17) -> (4,12))
```
Two distinct walls depending on budget:
- At 300s cap: compose *succeeds*, then the maze step dies on
  `BUDGET: layout_retry hit REDSTONE_MAX_SECS=300`.
- At 2400s cap: compose exhausts all 32 rungs on `no ground for A0`.
- Earlier, at a mid budget, compose reached the end and left the **constant
  net** orphaned: `OPEN (unconnected dust): [((751,1,190),'1'), ((752,1,190),'1')]`

So the shape is: input `A0` cannot reach ground, and the constant `1` net has
no driver path to its two loads. The constant is the more tractable of the two.

### alu4.txt / cpu4.txt -- the >=10-input approach cone
```
alu4: compose spread 2 inputs_first failed (no ground for A3B3: (672,13) -> (500,34))
alu4 at spread 6/10: wire B3 touches A1 beside (1268,1,7)   (and 2108,1,7 at s10)
cpu4: no ground for OPC1: (-43,-9) -> (428,347)
```
Both have 10+ inputs. Low spreads have no corridor; high spreads route but the
input-to-load legs cross each other and `stamp_wire` refuses the touch.
Already ruled out: lever rows are staggered 2 per input index, lane columns are
`4*spread` apart, and the near-end clearance window is already down to 1 cell.
So it is the approach cone, not the port row.

**`mux4` at 9 inputs is the proven ceiling.** That is the useful number.

### shift4.txt -- LATCH chain
```
no route for Q0: (12, 27) -> (29, 16) (grid full, widen W)
```
My own recipe (4-stage SR shift register), not part of the original dense set.
It got past compose (was `TORCH BURNOUT at (64,1,47)`) and now dies in the maze
step: latch tiles are large enough to saturate the grid for a 17-cell route.

## What actually fixed things

1. **Routing order became a retry axis.** Inputs routed last into a saturated
   field and collided (alu1 `OP1`/`OP0` at y=3). Inputs-first gives them clean
   ground. This is what turned alu1 green.
2. **Jog depth became a retry axis.** The 16-32 row jogs are what unseal a
   sprawling field (alu1) but they once let add2's input march wander unsealed
   and killed all four of its input ports. Both are rungs now: short first
   (proven baseline), long as escalation.
3. **Spread ladder 1..5 -> 1,2,3,4,5,6,8,10.** alu4/cpu4 die of `no ground`;
   tile fields are fully stamped before any routing, so a far input has no
   corridor at spread 5.
4. **Slope-link lids** (the one that moved cmp2 past a wall it could not escape
   at any spread). sim couples y=1 dust to a diagonal y=2 wire only when the
   upper has support *and* the lower has no lid over it. Hops and 3D overflights
   mint elevated dust on fresh cobble, and the search that placed them could not
   see the foreign wire landing diagonally below -- so `check_shorts` raised
   `SHORT3D` only after the fact. `_walk` now drops one cobble directly above
   the lower wire, mirroring `check_shorts`' dy=-1 case cell for cell. Because it
   mirrors the raise condition exactly, a build that already passes gets **zero**
   extra blocks: latch_sr 224, micro1 2925, chainmix 11497 all unchanged.
5. **Near-end clearance 3 cells -> 1.** Only the port cell itself may sit inside
   a foreign wire's neighbourhood.

Every one of these is an *axis* on the existing retry ladder, not new machinery.
All 13 greens still succeed on rung 1, bit-identical -- the gates never move.

## Two bugs worth keeping in mind

**`sim_verify` checks fidelity to the recipe, never the recipe's arithmetic.**
add2 once shipped *green* with a wrong carry (`C1 = A0 AND B0` instead of
`A0 OR B0`). Fixed. So I added `scratch/recipe_check.py`, which checks a
recipe's outputs against a reference expression over *every* input vector with
no placement involved. It immediately caught that my first `sub2` was wrong too:
bit-0 sum is `A0 XOR B0` (the +1 carry-in cancels the inversion) and the bit-0
carry is OR, not AND. **Any new recipe should pass `recipe_check.py` before
anyone spends an hour routing it.**

**andor8's 3-level dust OR tree was SIM-RED on 7/256 vectors while its gate
tracing was correct**, and 40000 settle ticks changed nothing -- so the dust OR
tree itself was racing, not the wiring. Rewriting `O8` as `NOT(AND of NOTs)`
(torch ANDs and inverters only, no dust OR) made it green. Prefer AND/NOT trees
over dust OR trees for wide fan-in.

## Hang-proofing (your rule 7)

- `compose()` had **no wall-clock bound at all** and the ladder was about to
  grow to 32 attempts, so a hard recipe could spin forever. Added
  `REDSTONE_COMPOSE_SECS`: a deadline over the whole ladder.
  `REDSTONE_MAX_SECS` still bounds a single attempt.
- `tools/gate.ps1` runs the fleet in parallel, one bounded process per recipe,
  and exits 1 iff anything is red.
- **My own polling was the thing that looked like a hang** -- I used
  `Start-Sleep` for 5-10 minutes inside a tool call, so the shell sat silent.
  Builds are detached and polled with sub-minute calls now.

## What I need from you

Nothing blocking. Decisions I made on your behalf, flagged in case you disagree:

1. **`tools/gate.ps1` is tracked; the older runners in `scratch/` are not**
   (`scratch/` is gitignored). The gate is the reproducibility contract, so it
   should not be ignored.
2. **`shift4.txt` is still in `recipes/`** and stays red, so `tools/gate.ps1`
   exits 1 until it is fixed or moved out. I left it visible rather than delete
   it, because "LATCH chains saturate the maze grid" is a real finding. Say the
   word and I will move it to a `known-hard/` folder so the gate goes green.
3. **I did not treat the constant-net bug as a blocker** even though cmp2 is the
   most promising of the four, because it needs a routing change I could not
   land inside this session.

## Ordered next steps

1. cmp2: give the constant `1` net a real driver path. It is a *source* net with
   two loads and no lever, and `check_opens` reports it orphaned at
   `(751,1,190)`. Start by looking at how `pos`/lever seeding treats a net whose
   name is a literal `1` (`layout.py:800-812` seeds from `pos` and from lever
   islands only).
2. cmp2: then the `A0` `no ground` at `(-43,-17) -> (4,12)`.
3. alu4/cpu4: attack the approach cone, not the port row. Cheapest experiment is
   ordering each input's loads by distance from its port instead of by
   `(x, z)` lexicographic -- currently `sorted(netspec[net]['loads'])`. Expect
   hashes to move; check the 13 greens still pass.
4. shift4: reduce latch count, or find out why a 17-cell route saturates the
   grid. Latch tiles are the outlier in footprint.
