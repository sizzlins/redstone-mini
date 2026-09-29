# redstone-mini improvement plan (trimmed)

Studied: `D:\redstone_description_language`, `C:\Users\LOQ\AppData\Local\Temp\opencode\redstonebuilder`, `D:\MinecraftHDL` (itsfrank/MinecraftHDL), `D:\RedHDL` (Iltotore/redhdl), `D:\redstone-compiler` (Redstone-Compiler/redstone-compiler), `D:\minecraft-hdl` (cemulate/minecraft-hdl).

**This file does not own the placement work.** Two repo specs do, and they are the live plan:

- `docs/superpowers/specs/2026-09-28-compositional-backend-design.md` — §1 tile hoist (partly landed: AND 11x9→9x7), §2 `compose.py` (landed, 4/4 small green), §3 ladder integration (landed, `sim.py:57` composer-first).
- `docs/superpowers/specs/2026-09-28-recursive-locality-design.md` — **§1 is unimplemented and is the approved open hypothesis.** Producer-consumer locality replaces topo bands; §3:55-57 declares it FALSIFIED and bans a fifth mechanism if dense still fails march-class loud.

What lives here is only the cross-repo survey (Phase A) and the infra work nothing else covers (Phases B–D). Placement phases an earlier draft of this file proposed are removed: buses/hierarchy were YAGNI, tile-reserve tightening is spent, levelize+relay is subsumed by bump-until-disjoint (`recursive-locality-design.md:34`), and compose-first already shipped.

Standing constraints (`handoff.md:377-410`): bar = engine generality (any recipe verifies fast in default ladder, not pinned greens); frozen = sim vanilla contract + suite gates; unfrozen = tiles; holdout = `cpu4` (never tune to it); barred = corridors / bank / chaining / grow-field / 5th placement-or-router tweak without ground-creating hypothesis.

## Phase A — Cross-repo survey (done; Allowed-APIs for B–D)

Sources: `D:\redstone-mini/{README,handoff.md,PONYTAIL-DEBT.md,recipe.py,layout.py,tiles.py,sim.py,export.py,compose.py,serve.py,docs/phase{1,2,3}*,docs/superpowers/specs/*,scratch/ladder2.py,seed2.py,census_cause.py}`; RDL `{README,src/vhdl/tokenizer.zig,parser.zig,dl.zig,construction.zig,nbt.zig,node.zig,main.zig,nbt_test.zig,sample/fa.vhd}`; redstonebuilder `{README,Cargo.toml,rb-core/*,rb-parser/hdl.pest+parse.rs+validate.rs+elaborate.rs,rb-synthesis/netlist.rs+cycle.rs+lower.rs+optimize.rs+cell_library.rs+place/*+route/*+timing.rs+budget.rs,rb-nbt/*,cli.rs,pipeline.rs,specs/003-design.md,examples/}`; MinecraftHDL via `git show HEAD:{README,markdown/*.md,verilog/*/auto.ysy+synth.*,src/main/java/GraphBuilder/GraphBuilder.java,MinecraftGraph/*.java,synthesis/IntermediateCircuit.java+LogicGates.java+Circuit.java,routing/Router.java+Channel.java+Net.java+pins/*+vcg/*.java,block/blocks/Synthesizer.java}`; RedHDL `{README,build.mill,cli/Main.scala,parser/*,ast/*,typer/TypeChecker.scala,ir/Expander.scala+Simplifier.scala,graph/GraphRouter.scala+GraphBuilder.scala+NodeType.scala+Channel.scala+Net.scala,minecraft/SchematicGenerator.scala+GateType.scala+Structure.scala,main/resources/gates/*,test/resources/golden/good/*}`; redstone-compiler via `git show HEAD:{README,AGENTS.md,docs/*.md,src/ir/*.rs,global_pnr/policy.rs+placer.rs+router.rs+search.rs+candidate_cache.rs,sequential/core.rs+layout.rs,world/simulator.rs,nbt/mod.rs,output.rs,snapshot.rs,tools/nbt-viewer/*}`; minecraft-hdl `{README,src/main.py+input_parse.py+Input.py+combinational_element_factory.py+fitter.py+block_constants.py,tests/test{1,2,3}.json}`.

Allowed-APIs to copy (exact):
- RDL: `dl.zig:172-233` builders + `:97-133` `paddingNecessary` + `:235-249` `eval`; `construction.zig:920 translateGate`, `:1093 connectPoints` (`:1120` repeater every `STEPS_BEFORE_REPEATER=5`), `:1038 bridge()`, `:781 combine()` (`width+10`), `:1148-1197` lever-bus+lamp; `parser.zig:413-492` precedence; `main.zig:59-101` NBT+gzip. The measured no-shared-ground result (recursive tiles sized by subtree, Z-stacked children, X+10 spread, wool over-bridges, repeaters/5) is quoted at `compositional-backend-design.md:30-37`: alu1 3485 blocks 0.2s, ctrl_decode 1440 0.0s, alu4 24396 0.2s, byte-identical, 7–9% elevated, equivalence 32/32 alu1 + 1024/1024 alu4.
- RB: `hdl.pest:1-114` bus/conn rules; `parse.rs:289-299` bus desugar; `elaborate.rs:58-117` flatten; `validate.rs:118-230` port table; `netlist.rs:142` `build_netlist`; `cycle.rs:25` `detect_cycles`; `lower.rs:22` `lower_xor_gates`; `optimize.rs:24` `prune_dead_gates`; `cell_library.rs:79 macrocell_for`; `place/sa.rs:22 SaConfig`; `route/cost.rs:45 CostMap + :257 EdgeCostConfig`; `route/pathfinder.rs:68 route_pathfinder`; `timing.rs:61 analyse_timing`; `budget.rs:20 BudgetGuard`; `cli.rs:19-164` flags; `pipeline.rs:111-156` exits 0-9.
- MHDL: `auto.ysy` (`read_verilog; hierarchy -check; proc; opt; fsm; opt; memory; opt; techmap; opt; json`); `GraphBuilder.java:buildGraph + resolveType` (and/or/not/xor/mux/dlatch_p); `IntermediateCircuit.java:loadGraph` (Kahn + RELAY splice) `+buildGates/genGate +routeChannels/genCircuit`; `LogicGates.java` sizes; `Router.java:initializePins/initializeNets/placeNets`; `Channel.java:findAvailableTrack/genChannelCircuit` (repeaters X~14/Z~10-13); VCG ctor+`canRoute/routed`.
- RedHDL: `Parser.scala:18-31` grammar; `TypeChecker.scala:checkProgram/checkComponent` + `TypeFailure` variants; `Expander.scala:expandExpr/prefixExpr` (`$`); `Simplifier.scala:optimizeSimplified` (10 rules); `GraphRouter.scala:getLayers/addRelays/getXPositions/createChannel/assignTrack/breakCycle/sortNets/routeChannel/routeGraph`; `NodeType.sizeX` (1 vs 2); `SchematicGenerator.scala:31-42` (`gateSizeZ=4,layerSizeZ=6,columnSpacing=2,trackSpacing=4`, repeaters X/14 Z/15); `GateType.resourceName`; `Main.scala:56-79` flags.
- RC: `policy.rs:29-146` heuristics + weights (`wire 8, vertical 16`); `pnr.rs:242-310` intent (`Inside/LayerRange/FixedOrigin/NetPriority/NetAvoid/PreferInside/SameLayer`); `sequential/core.rs:8-81` RS core; `layout.rs:9-36` macro; `simulator.rs:15-88` events + `TORCH_BURNOUT 60/8`; `nbt/mod.rs:73-120` emit; snapshot dir layout `compilation_snapshots.md:5-33`.
- mini own: `recipe.py:8/47/82`; `layout.py:33 dust_points, 314 astar, 825 layout, 1084 spot_free, 1282 try_bridge, 1430 seal_nets, 1531 place_rep`; `tiles.py:22/76/125/140/191/224/291/375/429`; `sim.py:27 layout_retry, 149 dust_lvl, 465 sim_verify`; `export.py:41/59/72`; `compose.py:327 compose, 137 lwire, 242 _plant_repeaters`; `serve.py:24 compile_recipe`; harnesses `scratch/ladder2.py, seed2.py, census_cause.py`.

Anti-patterns (do not copy / do not re-propose): mini corridors-ray, median-bank, fanout-chaining, grow-field (all measured 0/12, `handoff.md:213-251,412-453`); directional-OPEN walk (red on green `example_xor`); naive one-circuit probes (green s3-D gap-15 false-positive); `minecraft-hdl` SOP-only + `pymclevel`/Py2 + `fitter.py:272` output-spacing bug + `addition_element_factory=None` stub; MHDL destructive `placeInWorld` + no-sequential + Forge 1.10.2; RC doc-only `MappingPolicy/TargetSpec` (code is `lower_to_routable()` argless); nonexistent `docs/place_and_route.md`.

## Phase B — Routing: local cache + left-edge residual + intent

Blocked on: `recursive-locality-design.md` §1 landing and dense going green. Do not add a router mechanism before the locality kill-criterion resolves.

What to implement: copy RC `candidate_cache.rs:CACHE_FORMAT + load/store` keyed `(target+impl+recipe+version)` for `compose`/`layout` outputs; copy RedHDL `assignTrack/breakCycle` left-edge for adjacent-layer nets, leaving only non-adjacent nets to `layout.py:898 route()` maze; copy RDL `:1120` repeater-every-5 + `:1038 bridge()` discipline into `place_rep (layout.py:1531)` + `_plant_repeaters`; copy RC `pnr.rs:242-310` minimal intent subset (`Inside/LayerRange/NetAvoid`, `NetPriority`) threaded through existing `astar(...,blocked,guard)` params (no new router).
Doc refs: `layout.py:314 astar sig, 582 bridge_free, 653 finish_assembly, 1282 try_bridge cap-24`; RedHDL `Channel.scala:sizeX/sizeZ/isOuterColumn`; RB `detailed_router.rs:31-81` reject reasons; RC `physical_design_intent.md:15-29` example block.
Verify: `ctrl_decode` (15 gates, proving ground) unrouted count falls from 65 @cap-150; `alu1 s8 n0 (8,54)->(9,51)` 4-cell hop routes; `check_shorts/check_opens` still loud (no silent green); `grep -n "bridge_plan\|bridged) >= 24" layout.py` cap intact.
Anti-patterns: no new bridge shape (single shape cap-24 stays); no `congest` full negotiation (lite only); no `REDSTONE_SEARCH_CAP` default-on.

## Phase C — Scale infra: budget + snapshots + STA-lite

Not blocked. Independent of placement; can land any time.

What to implement: copy RB `budget.rs:20 BudgetGuard::new/check` as a `REDSTONE_MAX_SECS` guard around `layout_retry` (exit-loud, not silent skip); copy RC `compilation_snapshots.md:5-33` minimal sidecar (`manifest+summary+ir/{logical,routable}+routes.json`, content-hash cache dir); copy RB `timing.rs:61 analyse_timing` as an arrival-tolerance check on `Q` nets only (the named `s7/s10 Q 16/126 vs 111/111` defect, `handoff.md:287-303`) — data-race warn, not block; copy RDL `nbt_test.zig:32-42` pre-place `eval` gate (already have `eval_net`, wire it as pre-layout reject).
Doc refs: `sim.py:17-24` caps, `:465-520` verify, `:523-537` sequence/pulse; `export.py:41-68` schem/mcfunction; RC `pnr_logging.md` tracing levels.
Verify: `cpu4` holdout still runs bounded (`402s/seed` → capped loud-fail, never tuned); `sim_verify` `<=4096` exhaustive rule unchanged; `grep -rn "STALLED\|SIM MISMATCH" sim.py` behavior identical on greens; snapshot dir replays one green build.
Anti-patterns: no raising `_TICK_CAP/_STEP_CAP/_STALL` to chase greens (needs dense-green calibration first); no `>12-input` sampling change here; no texture/offline change.

## Phase D (deferred, gated) — Sequential + roof-reuse probes

Gate: `docs/phase3-clock-discipline.md` `Q=DFF D CLK` only after the two owning specs resolve and `alu1` is green; copy RC `sequential/core.rs:recognize_rs_latch_core` (4-node SCC check) + `layout.rs:rs_latch_macro` fallback discipline; roof-reuse needs a positive probe (elevated marathon fits AND verifies where ground verifiably doesn't) before any design. Not in current execution budget.

## Final Phase — Verification (always last, fresh context)

1. `python recipe.py && python sim.py && python layout.py` canaries + `python serve.py --check` (demo 288-block) green.
2. `REDSTONE_XCHECK=1` on both green `micro1` seeds; 4/4 small-build hashes byte-identical.
3. `grep -rn "corridor\|_bankz" layout.py` — no revived mechanisms (`_bf` is the pre-existing fanout path, allowed).
4. Ladders: `LADDER_GROW=1 scratch/ladder2.py 700 0 11 micro1.txt alu1.txt` recorded; `census_cause.py 700 alu1 0-5` cause table recorded; `cpu4` untouched except bounded runtime.
5. `grep -rn "ponytail:"` ledger updated (new ceilings named with upgrade path per repo policy).
