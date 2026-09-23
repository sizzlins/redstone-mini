# redstone-mini

Tiny recipe -> Minecraft redstone 3D model. Write small logic, get blocks.

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

8-bit adder (first ALU slice, ripple-carry from the same gates):
```bash
python redstone_mini.py --alu8
# opens: build_alu8.html + build_alu8.mcfunction (datapack only — first run:
# gamerule maxCommandChainLength 200000)
# The adder is ~75k setblocks of real torch gates (preview stays fast).
```

Preview `build.html` streams real textures from the upstream
`PrismarineJS/minecraft-assets` pack (needs internet, falls back to flat colors offline).
Torches add a tick of delay each; the compiler doesn't model timing yet.
