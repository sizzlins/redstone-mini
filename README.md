# redstone-mini

Logic recipe, big or small → Minecraft redstone 3D model → `build.schem`
export to Minecraft.
<img width="1705" height="800" alt="image" src="https://github.com/user-attachments/assets/509e07ee-2981-4f95-8d9d-2a1e05836f38" />

## Use

```bash
python redstone_mini.py
# opens: build.html (3D preview) + build.mcfunction (paste into flat world)
```

Custom recipe `my.txt`:
```
IN a, b, c
OUT y
t = a AND b
y = t OR c
```
```bash
python redstone_mini.py my.txt
```

Supports: AND OR XOR NOT. `build.mcfunction` = list of `setblock` (includes stone
floor, so paste anywhere flat or install as datapack and run `/function`).

Gates are real torch builds (wiki textbook: NOT/NOR = dust into block + torch,
AND = inverted inputs into NOR, OR = joined wires). A built-in short checker
rejects any layout where two nets touch — bad builds fail loudly, never silently.

Big banded builds (a 4-bit ALU, a CPU slice) route in bands, stitch, and verify
every input vector against the logical oracle:

```bash
python scratch/hier_verify.py recipes/alu4.txt   # bands + stitch + 1024/1024
python scratch/hier_verify.py recipes/alu1.txt   # bands + stitch + 32/32
```

Current state: **alu4 green 1024/1024** (71,560 blocks), **alu1 hier green 32/32**.
Verification is dual-engine: the tick-stepped sim (`sim.py`, which models repeater
delays, torch burnout and settling — timing included) plus `cmc`, an independent
implementation that must agree per cell, not just per lamp.

Preview `build.html` streams real textures from the upstream
`PrismarineJS/minecraft-assets` pack (needs internet, falls back to flat colors offline).
