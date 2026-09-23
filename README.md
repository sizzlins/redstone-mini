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

Supports: AND OR XOR NOT. `build.mcfunction` = list of `setblock` to paste in a flat world.

8-bit adder (first ALU slice, ripple-carry from the same 2-input gates):
```bash
python redstone_mini.py --alu8
# opens: build_alu8.html + build_alu8.mcfunction (386 setblocks — install as datapack, run /function)
```

Preview `build.html` streams real textures from the upstream
`PrismarineJS/minecraft-assets` pack (needs internet, falls back to flat colors offline).

## Note
Visual model only for now, not tick-accurate redstone.
