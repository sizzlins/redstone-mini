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

Preview `build.html` streams real textures from your fork
`sizzlins/minecraft-assets` (needs internet, falls back to flat colors offline).

## Note
Visual model only for now, not tick-accurate redstone.
