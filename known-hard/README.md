# known-hard

Recipes that are valid circuits but the current place-and-route architecture
cannot build. Preserved (not deleted) as regression targets. They are OUT of
`recipes/` so `tools/gate.ps1` reflects the shippable set.

## shift2.txt / shift4.txt -- gate-driven LATCH inputs burn out
2-stage and 4-stage SR shift registers. Both die with `TORCH BURNOUT` at the
same cell `(64,1,47)` during `sim_verify`, 0.1s into compose. The single
`latch_sr` (LATCH with primary-input S/R) is green; a LATCH whose S is driven
by another gate's output (here `L1 = LATCH Q0 R` where `Q0` is an AND) burns
its torch out. Almost certainly the route from the driving gate passes beside
the latch's torch and couples into it (the apron-ring seal covers tile torches,
not a driven input run entering the port). Needs a latch-input keep-out, which
is a new placement rule, not a ladder rung.

Logic of both is proven by `scratch/recipe_check.py` (all vectors OK), so when
the keep-out lands, these are the first two to re-run.
