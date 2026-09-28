"""Compose: deterministic placement + wiring (no search, no seeds)."""

from core import DIRS
from tiles import stamp_wire
from layout import _support

_VEC = {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}


def lwire(ctx, sup, guard, a, b, net):
    """Z-then-X path at y=1; insulated overpass (cobble y=2, wire y=3) over
    sealing cells; repeaters every 14 on flat straight triples."""
    cells = []
    x, z = a
    while z != b[1]:
        z += 1 if b[1] > z else -1
        cells.append((x, 1, z))
    while x != b[0]:
        x += 1 if b[0] > x else -1
        cells.append((x, 1, z))
    done = []
    for (cx, cy, cz) in cells:
        try:
            stamp_wire(ctx, [(cx, cz)], net)
            done.append((cx, cy, cz))
        except RuntimeError:
            # overpass: opaque cobble stacked on the sealed column, wire
            # above that (upstream's insulated geometry — the block between
            # severs any slope link; the lid rule keeps the lower net live).
            # finish_assembly emits wire bids from the wires dict alone, so
            # routed cells append NOTHING to blocks here — only the pillar.
            r = _support((cx, 3, cz), net, ctx.solid, ctx.wires, sup,
                         ctx.repeaters, guard)
            if r is False:
                raise RuntimeError(f"compose: no ground for {net}: {a} -> {b}")
            sup[(cx, 2, cz)] = net
            ctx.blocks.append((cx, 2, cz, "minecraft:cobblestone"))
            ctx.solid.setdefault((cx, cz), ("cobble", net))
            ctx.wires[(cx, 3, cz)] = net
            done.append((cx, 3, cz))
    _plant_repeaters(ctx, done, net)
    return done


def _plant_repeaters(ctx, cells, net):
    for k in range(13, len(cells) - 1, 14):
        (px, py, pz), (cx, cy, cz), (nx, ny, nz) = cells[k - 1], cells[k], cells[k + 1]
        dx, dz = cx - px, cz - pz
        if (dx, dz) == (nx - cx, nz - cz) and (dx, dz) in _VEC and py == cy == ny == 1:
            del ctx.wires[(cx, cy, cz)]
            ctx.repeaters[(cx, cy, cz)] = (net, _VEC[(dx, dz)])


if __name__ == "__main__":
    from tiles import new_ctx, stamp_wire
    _blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs, _sup0 = [], {}, {}, {}, {}, {}, {}, [], {}
    _ctx = new_ctx(_blocks, _solid, _rings, _wires, _junc, _reps, _pos, _recs, _sup0)
    _sup, _guard = {}, set()
    # two nets must cross: A runs east, B must bridge over it.
    stamp_wire(_ctx, [(10, 1, 20), (11, 1, 20), (12, 1, 20), (13, 1, 20)], "A")
    lwire(_ctx, _sup, _guard, (11, 18), (11, 22), "B")
    assert _wires.get((11, 1, 20)) == "A", _wires
    assert any(y >= 2 for (x, y, z), n in _wires.items() if n == "B"), "B never left the ground"
    print("lwire ok: bridge-over crosses without touching")
