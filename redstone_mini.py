"""redstone-mini: recipe -> working Minecraft redstone build. CLI entry."""
import sys

from core import base
from recipe import eval_net, parse_recipe, build_adder8
from sim import layout_retry
from export import export_mcfunction, export_schem, export_html


DEMO = """IN a, b, c
OUT y
t = a AND b
y = t OR c
"""



def demo():
    r = parse_recipe(DEMO)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                got = eval_net(r, {"a": a, "b": b, "c": c})["y"]
                assert got == ((a and b) or c), (a, b, c, got)
    blocks, size, io = layout_retry(r, verify=True)
    assert any(base(b) == "minecraft:cobblestone" for *_, b in blocks), "gate block missing"
    assert any(base(b) == "minecraft:redstone_wall_torch" for *_, b in blocks), "torch missing"
    export_mcfunction(blocks, "build.mcfunction")
    export_schem(blocks, "build.schem")
    export_html(blocks, size, "build.html", "2-gate demo")
    print(f"ok: {len(blocks)} blocks -> build.html + build.mcfunction")



def demo_alu8():
    r = build_adder8()
    for a, b in ((13, 29), (200, 100), (255, 1), (0, 0)):
        v = {f"A{i}": (a >> i) & 1 for i in range(8)}
        v.update({f"B{i}": (b >> i) & 1 for i in range(8)})
        got = eval_net(r, v)
        s = sum(got[f"S{i}"] << i for i in range(8))
        assert (s, got["C8"]) == ((a + b) & 255, (a + b) >> 8), (a, b, s)
    blocks, size, io = layout_retry(r, verify=True)
    export_mcfunction(blocks, "build_alu8.mcfunction")
    export_schem(blocks, "build_alu8.schem")
    export_html(blocks, size, "build_alu8.html", "8-bit adder")
    print(f"alu8 ok: {len(blocks)} blocks -> build_alu8.html + build_alu8.mcfunction")

if __name__ == "__main__":
    demo()
    if "--alu8" in sys.argv:
        demo_alu8()
    elif len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size, io = layout_retry(r, verify=True)
        export_mcfunction(blocks, "build.mcfunction")
        export_schem(blocks, "build.schem")
        export_html(blocks, size, "build.html", sys.argv[1])
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
