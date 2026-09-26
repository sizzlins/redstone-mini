"""redstone-mini: recipe -> working Minecraft redstone build. CLI entry."""
import sys

from core import base
from recipe import eval_net, parse_recipe
from sim import layout_retry
from export import export_mcfunction, export_schem, export_html
from serve import serve, DEMO



def demo():
    r = parse_recipe(DEMO)
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                got = eval_net(r, {"a": a, "b": b, "c": c})["y"]
                assert got == ((a and b) or c), (a, b, c, got)
    blocks, size, io, st = layout_retry(r, verify=True)
    assert any(base(b) == "minecraft:cobblestone" for *_, b in blocks), "gate block missing"
    assert any(base(b) == "minecraft:redstone_wall_torch" for *_, b in blocks), "torch missing"
    export_mcfunction(blocks, "build.mcfunction")
    export_schem(blocks, "build.schem")
    export_html(blocks, size, "build.html", "2-gate demo", st)
    print(f"ok: {len(blocks)} blocks -> build.html + build.mcfunction")


if __name__ == "__main__":
    if "--serve" in sys.argv:
        i = sys.argv.index("--serve")
        serve(int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 8000)
        sys.exit(0)
    demo()
    if len(sys.argv) > 1:  # custom recipe file
        text = open(sys.argv[1]).read()
        r = parse_recipe(text)
        blocks, size, io, st = layout_retry(r, verify=True)
        export_mcfunction(blocks, "build.mcfunction")
        export_schem(blocks, "build.schem")
        export_html(blocks, size, "build.html", sys.argv[1], st)
        print(f"custom ok: {len(blocks)} blocks -> build.html + build.mcfunction")
