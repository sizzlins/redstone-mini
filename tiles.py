"""Tiles: pure stamping builders on an explicit state object (hoisted from layout())."""

from types import SimpleNamespace

from core import DIRS


def new_ctx(blocks, solid, rings, wires, junctions, repeaters, pos, recs, sup):
    return SimpleNamespace(blocks=blocks, solid=solid, rings=rings, wires=wires,
                           junctions=junctions, repeaters=repeaters, pos=pos,
                           recs=recs, sup=sup)


def own(*nets):
    return set(nets)


def ring(ctx, x, z, nets):
    ctx.rings.setdefault((x, z), set()).update(nets)


def stamp_wire(ctx, path, net, ends=()):
    for cell in path:
        if len(cell) == 2:
            cell = (cell[0], 1, cell[1])  # placement stubs are y=1
        flat = (cell[0], cell[2])
        if cell[1] == 1:
            if flat in ctx.solid:
                raise RuntimeError(f"wire {net} hits solid at {cell}")
        elif cell in ctx.sup:
            raise RuntimeError(f"wire {net} hits pillar at {cell}")
        # (tile columns never block y>=2 overflight: correction 1)
        if cell in ctx.wires and ctx.wires[cell] != net:
            if cell[1] == 1 and flat in ctx.junctions and net in ctx.junctions[flat]:
                continue  # OR junction: wired-OR is the gate
            raise RuntimeError(f"wire {net} bridges {ctx.wires[cell]} at {cell}")
        if cell[1] == 1 and flat in ctx.rings and net not in ctx.rings[flat]:
            # astar exempts the ports (a tile port sits inside rings by
            # construction and the router MUST start and end there), so
            # stamping must agree — otherwise a legal route dies at its own
            # endpoint. The ring overlap is a tile-placement artefact
            # either way; sim is the selector for whether it miscomputes.
            if cell[1] == 1 and flat in ctx.junctions and net in ctx.junctions[flat]:
                pass
            elif flat in ends:
                pass
            else:
                raise RuntimeError(f"wire {net} hits guarded {cell}")
        # ponytail: same-level adjacency guard. A* guarantees a routed path
        # never side-touches a foreign net (touches_foreign), but every
        # OTHER stamp goes through here with no search at all: output taps,
        # bank stubs, tile port rows, XOR side wires, the cover tail. Those
        # were checked only for "a foreign wire sits ON this cell", never
        # "one sits next to it" — so a routed net could end up touching an
        # output tap. Measured: `SHORT: m0 touches Y at (223,1,13)
        # ->(222,1,13)`, Y's cell in no routed path at all.
        for dx, dz in DIRS:
            nb = ctx.wires.get((cell[0] + dx, cell[1], cell[2] + dz))
            if nb is not None and nb != net and not (
                    (cell[0] + dx, cell[2] + dz) in ctx.junctions
                    and net in ctx.junctions[(cell[0] + dx, cell[2] + dz)]):
                raise RuntimeError(f"wire {net} touches {nb} beside {cell}")
        ctx.wires.setdefault(cell, net)


def stamp_cobble(ctx, x, z, o):
    ctx.blocks.append((x, 1, z, "minecraft:cobblestone"))
    ctx.solid[(x, z)] = ("cobble", o)


def stamp_torch(ctx, x, z, o):
    ctx.blocks.append((x, 1, z, "minecraft:redstone_wall_torch[facing=east]"))
    ctx.solid[(x, z)] = ("torch", o)


def stamp_and(ctx, ox, gz, A, B, O):
    # compact torch AND (textbook): NOT-A top, NOT-B bottom, NOR middle-right.
    na, nb = f"{O}~a", f"{O}~b"
    fam = own(A, B, O, na, nb)
    stamp_cobble(ctx, ox, gz, O)
    stamp_torch(ctx, ox + 1, gz, O)
    stamp_cobble(ctx, ox, gz + 3, O)
    stamp_torch(ctx, ox + 1, gz + 3, O)
    stamp_cobble(ctx, ox + 3, gz + 1, O)
    stamp_torch(ctx, ox + 4, gz + 1, O)
    for rx, rz in ((ox - 1, gz), (ox + 1, gz), (ox, gz - 1), (ox, gz + 1),
                   (ox + 2, gz), (ox + 1, gz - 1), (ox + 1, gz + 1),
                   (ox - 1, gz + 3), (ox + 1, gz + 3), (ox, gz + 2), (ox, gz + 4),
                   (ox + 2, gz + 3), (ox + 1, gz + 2), (ox + 1, gz + 4),
                   (ox + 2, gz + 1), (ox + 4, gz + 1), (ox + 3, gz),
                   (ox + 5, gz + 1), (ox + 4, gz), (ox + 4, gz + 2)):
        ring(ctx, rx, rz, fam)
    stamp_wire(ctx, [(ox - 2, gz), (ox - 1, gz)], A)
    stamp_wire(ctx, [(ox - 2, gz + 3), (ox - 1, gz + 3)], B)
    # ponytail: funnel the input stubs with cobble (no repeaters: a
    # repeater fronting a block back-feeds its own supply through the
    # block into route dust beside it — a permanent latch once kicked).
    # Straight dust reads identically mirrored or correct, so the tile
    # behaves exactly like its verified-green era; the funnels only keep
    # joins straight (router must arrive E-W, cannot hug parallel and
    # corner the stub dead). Footprints already cover these cells.
    for _fx, _fz in ((ox - 2, gz - 1), (ox - 1, gz - 1),
                     (ox - 2, gz + 1), (ox - 1, gz + 1),
                     (ox - 2, gz + 2), (ox - 1, gz + 2),
                     (ox - 2, gz + 4), (ox - 1, gz + 4)):
        stamp_cobble(ctx, _fx, _fz, O)
    # ponytail: ~A must APPROACH the NOR host along the axis it points at.
    # Vanilla: powered dust powers a block only when it is on top of it or
    # POINTING at it, and pointing comes from the connection shape
    # (dust_points). The old N-S stub ((ox+2,gz),(ox+2,gz+1)) left its end
    # cell pointing north and south, so it never powered the host at
    # (ox+3,gz+1) -- the AND tile's NOR input was dead in vanilla and only
    # appeared to work because the sim assumed every cell is a cross. This
    # E-W stub ends at (ox+2,gz+1), which points east into the host. Both
    # cells were already in the ring list above, so no ring edit is needed.
    stamp_wire(ctx, [(ox + 1, gz + 1), (ox + 2, gz + 1)], na)
    # ponytail: ~B hugs the west side on purpose. It must never touch the
    # NOR torch (ox+4,gz+1): torch->wire->block->torch is a ring oscillator
    # that blinks instead of computing whenever both NOTs are off.
    stamp_wire(ctx, [(ox + 2, gz + 3), (ox + 3, gz + 3), (ox + 3, gz + 2)], nb)
    stamp_wire(ctx, [(ox + 5, gz + 1), (ox + 6, gz + 1)], O)
    return (ox - 2, gz), (ox - 2, gz + 3), (ox + 6, gz + 1)


def footprint(op, ox, gz):
    if op == "AND":
        # ponytail: reserve what spot_free checks (9x7), not 11x9. Stamped
        # cells max out at ox+6/gz+4 plus funnels; the old box held 2 spare
        # columns + 2 spare rows of pure clearance nobody measured.
        return {(x, z) for x in range(ox - 2, ox + 7) for z in range(gz, gz + 7)}
    if op in ("NOT", "NOR"):
        return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 1, gz + 2)}
    if op == "LATCH":
        return {(x, z) for x in range(ox - 6, ox + 8) for z in range(gz - 5, gz + 6)}
    if op == "XOR":
        return {(x, z) for x in range(ox - 3, ox + 8) for z in range(gz - 2, gz + 8)}
    return {(x, z) for x in range(ox - 3, ox + 4) for z in range(gz - 3, gz + 4)}


def place_or(ctx, place, g, ox, gz, pos, W, D):
    # repeater-isolated OR (wiki). Junction stays on-grid (merging by
    # touch would short); diodes face drivers. Grid fallback inside.
    op, o, a = g["op"], g["out"], g["args"]
    jx, jz = ox, gz
    if not (0 <= jx - 3 and jx + 3 < W and 0 <= jz - 3 and jz + 3 < D):
        raise RuntimeError(f"OR out of bounds for {o} at {(jx, jz)} field {W}x{D}")
    s = place.snap()
    try:
        j = (jx, jz)
        if j in ctx.solid or (j[0], 1, j[1]) in ctx.wires:
            raise RuntimeError(f"OR cell blocked at {j}")
        reps = []
        seen = {j}
        for sig in a:
            sx, sz = pos.get(sig, (jx - 4, jz))
            if abs(sx - jx) >= abs(sz - jz):
                order = [(1 if sx >= jx else -1, 0)]
            else:
                order = [(0, 1 if sz >= jz else -1)]
            order += [(1, 0), (-1, 0), (0, 1), (0, -1)]
            ok = False
            for dx, dz in order:
                for step in (1, 2, 3):
                    r = (j[0] + dx * step, j[1] + dz * step)
                    b = (j[0] + dx * (step + 1), j[1] + dz * (step + 1))
                    if r in ctx.solid or (r[0], 1, r[1]) in ctx.wires or b in ctx.solid or (b[0], 1, b[1]) in ctx.wires \
                       or r in seen or b in seen:
                        continue
                    facing = {(1, 0): "west", (-1, 0): "east",
                              (0, 1): "north", (0, -1): "south"}[(dx, dz)]
                    ctx.blocks.append((r[0], 1, r[1], f"minecraft:repeater[facing={facing},delay=1]"))
                    ctx.solid[r] = ("repeater", o)
                    reps.append((r, b))
                    seen.add(r)
                    seen.add(b)
                    ok = True
                    break
                if ok:
                    break
            if not ok:
                raise RuntimeError(f"OR cell blocked around {j} for {sig}")
        stamp_wire(ctx, [j], o)
        ctx.junctions[j] = {o}
        pos[o] = j
        ctx.recs.append((op, o, a, (j, reps)))
    except RuntimeError:
        place.restore(s)
        raise


def place_and(ctx, place, g, i, ox, gz, pos):
    # in-A port lands touching its driver (zero-wire tap). Chained
    # stays local (else grid): marches cause top-edge stranding.
    # (in-B chaining marches north; dropped for that reason.)
    op, o, a = g["op"], g["out"], g["args"]
    dv = pos.get(a[0])
    cands = []
    if dv is not None and dv not in ctx.junctions and not g.get("rep"):
        cands.append((dv[0] + 3, dv[1], True))
    cands.append((ox, gz, False))
    placed = False
    for ox2, gz2, local in cands:
        rows = [(ox2, gz2)] if local else place.gridrows(ox2, gz2)
        for ox3, gz3 in rows:
            if local and (abs(ox3 - ox) > 16 or abs(gz3 - gz) > 7):
                break
            if not place.spot_free("AND", ox3, gz3, i):
                continue
            s = place.snap()
            try:
                pa, pb, po = stamp_and(ctx, ox3, gz3, a[0], a[1], o)
                pos[o] = po
                ctx.recs.append((op, o, a, (pa, pb, po)))
                placed = True
                break
            except RuntimeError:
                place.restore(s)
        if placed:
            break
    if not placed:
        raise RuntimeError(f"AND blocked for {o}")


def place_latch(ctx, place, g, i, ox, gz, pos):
    # flat SR latch (textbook NOR latch, adjacent blocks): A-block
    # reads R+Qb, B-block reads S+Q-west; Q exits west at z+2.
    # Hand-placed: cross-coupling is delay-critical, the router must
    # never thread repeaters through it (they sustain power-on race).
    op, o, a = g["op"], g["out"], g["args"]
    qb = f"{o}~qb"
    fam = own(a[0], a[1], o, qb)
    placed = False
    for ox2, gz2 in place.gridrows(ox, gz):
        if not place.spot_free("LATCH", ox2, gz2, i):
            continue
        ox, gz = ox2, gz2
        Sdust = [(ox - 1 + k, gz + 4) for k in range(6)] + \
            [(ox + 4, gz + 3), (ox + 4, gz + 2), (ox + 4, gz + 1)]
        Rdust = [(ox - 2, gz), (ox - 1, gz)]
        Qdust = [(ox + 2, gz), (ox + 3, gz), (ox + 2, gz + 1)] + \
            [(ox + 2 - k, gz + 2) for k in range(8)]
        Qbdust = [(ox + 4, gz - 2), (ox + 4, gz - 3), (ox + 4, gz - 4)] + \
            [(ox + 4 - k, gz - 4) for k in range(5)] + \
            [(ox, gz - 3), (ox, gz - 2), (ox, gz - 1)]
        s = place.snap()
        try:
            stamp_cobble(ctx, ox, gz, o)
            ctx.blocks.append((ox + 1, 1, gz, "minecraft:redstone_wall_torch[facing=east]"))
            ctx.solid[(ox + 1, gz)] = ("torch", o)
            stamp_cobble(ctx, ox + 4, gz, o)
            ctx.blocks.append((ox + 4, 1, gz - 1, "minecraft:redstone_wall_torch[facing=north]"))
            ctx.solid[(ox + 4, gz - 1)] = ("torch", o)
            for cells, net in ((Sdust, a[0]), (Rdust, a[1]),
                               (Qdust, o), (Qbdust, qb)):
                stamp_wire(ctx, cells, net)
            # ponytail: the S row is 9 cells of the tile's OWN dust from
            # the block it must power, so it needs level ~10 at the port
            # and no bus budget can supply that -- the load is the port,
            # the row is past it. A repeater in the row fixes it, and
            # (ox+1) is the only cell that still sees power at the
            # guaranteed minimum. Measured: at level 2 the row died 4
            # cells short and the latch could NEVER set. A repeater on
            # the set input is the textbook shape and costs no race:
            # only set is delayed, reset is not, and the cross-coupled
            # Q/Qb loop itself is untouched.
            del ctx.wires[(ox + 1, 1, gz + 4)]
            ctx.repeaters[(ox + 1, 1, gz + 4)] = (a[0], "east")
            # ponytail: funnel the R stub like the AND/NOT inputs (a
            # repeater here would front the A-block and back-feed its
            # supply the same permanent way). Straight dust reads
            # identically mirrored or correct.
            for _fx, _fz in ((ox - 2, gz - 1), (ox - 1, gz - 1),
                             (ox - 2, gz + 1), (ox - 1, gz + 1)):
                stamp_cobble(ctx, _fx, _fz, o)
            for cx_, cz_ in set([(ox, gz), (ox + 1, gz), (ox + 4, gz),
                                 (ox + 4, gz - 1)] + Sdust + Rdust + Qdust + Qbdust):
                for dx, dz in DIRS:
                    ring(ctx, cx_ + dx, cz_ + dz, fam)
            pa, pb, po = (ox - 1, gz + 4), (ox - 2, gz), (ox - 5, gz + 2)
            pos[o] = po
            ctx.recs.append((op, o, a, (pa, pb, po)))
            placed = True
        except RuntimeError:
            place.restore(s)
        if placed:
            break
    if not placed:
        raise RuntimeError(f"LATCH blocked for {o}")


def place_xor(ctx, place, g, i, ox, gz, pos):
    # comparator XOR (dual subtract, sim-verified): C1 = A-B,
    # C2 = B-A, outputs merged west. Side inputs are tile-stamped
    # repeaters fed by the input nets (wiki: sides need STRONG power,
    # dust never counts, so routed wire can't feed them — and neither
    # can a panel lever beside the comparator, which is why the old
    # tile levers cost a second lever per input).
    op, o, a = g["op"], g["out"], g["args"]
    fam = own(a[0], a[1], o)
    placed = False
    for ox2, gz2 in place.gridrows(ox, gz):
        if not place.spot_free("XOR", ox2, gz2, i):
            continue
        ox, gz = ox2, gz2
        Adust = [(ox + 2, gz), (ox + 1, gz), (ox + 3, gz)]
        Bdust = [(ox + 2, gz + 4), (ox + 1, gz + 4), (ox + 3, gz + 4)]
        Odust = [(ox - 1, gz), (ox - 2, gz), (ox - 2, gz + 1),
                 (ox - 2, gz + 2), (ox - 2, gz + 3), (ox - 2, gz + 4),
                 (ox - 1, gz + 4), (ox - 2, gz + 5), (ox - 2, gz + 6)]
        s = place.snap()
        try:
            ctx.blocks.append((ox, 1, gz, "minecraft:comparator[facing=east,mode=subtract]"))
            ctx.solid[(ox, gz)] = ("comp", o)
            ctx.blocks.append((ox, 1, gz + 4, "minecraft:comparator[facing=east,mode=subtract]"))
            ctx.solid[(ox, gz + 4)] = ("comp", o)
            for cells, net in ((Adust, a[0]), (Bdust, a[1]), (Odust, o)):
                stamp_wire(ctx, cells, net)
            # ponytail: merge-tail diodes (example_xor SIM-dark root).
            # Subtract outs start at whatever decayed level the routed
            # rear delivers (~4, not 15); the 9-cell Odust merge eats
            # it before y-drv. Diodes facing flow restore 15; the
            # second also carries C2's entry south of the first.
            # Ceiling: two fixed diodes; revisit if the merge grows.
            for _jx, _jz in ((ox - 2, gz + 3), (ox - 2, gz + 5)):
                for _fx, _fz in ((_jx, _jz - 1), (_jx, _jz + 1)):
                    _w = ctx.wires.get((_fx, 1, _fz))
                    if _w is not None and _w != o:
                        raise RuntimeError(f"XOR diode guard {o} vs {_w} at {(_fx, _fz)}")
                if ctx.wires.get((_jx, 1, _jz)) != o:
                    raise RuntimeError(f"XOR diode spot holds {ctx.wires.get((_jx, 1, _jz), 'EMPTY')}")
                del ctx.wires[(_jx, 1, _jz)]
                ctx.repeaters[(_jx, 1, _jz)] = (o, "south")
            # ponytail: side feeds are repeaters, not levers. Wiki:
            # comparator sides need STRONG power and dust never counts,
            # so the old tile levers ringed their neighbours shut and
            # every XOR input cost a second lever. REP2 (a -> C2 north
            # side) rides a 3-cell tile stub off Adust; REP1 (b -> C1
            # north side) takes a routed load at (ox,gz-2), kept clear
            # of the output/lamp row down south. Both face south into
            # their comparator; backs read dust, outputs are 15 exactly
            # like the levers were (subtract takes max of sides, so the
            # north/south swap on C1 is equivalent).
            stamp_wire(ctx, [(ox + 1, gz + 1), (ox + 1, gz + 2), (ox, gz + 2)], a[0])
            for _rx, _rz in ((ox, gz - 1), (ox, gz + 3),
                             (ox + 1, gz + 1), (ox + 1, gz + 2), (ox, gz + 2)):
                ring(ctx, _rx, _rz, fam)
            ctx.repeaters[(ox, 1, gz - 1)] = (a[1], "south")
            ctx.repeaters[(ox, 1, gz + 3)] = (a[0], "south")
            for cx_, cz_ in set([(ox, gz), (ox, gz + 4)] + Adust + Bdust + Odust):
                for dx, dz in DIRS:
                    ring(ctx, cx_ + dx, cz_ + dz, fam)
            # ponytail: comparator sides read dust (vanilla: side dust
            # counts; cmc sideInput dust branch). A routed wire beside
            # a side suppresses the output like a side feed — example_xor
            # went dark on a=0,b=1 via b-dust at C2 south, which the old
            # sim (and the tile's "dust never counts" comment) couldn't
            # see. Wall all four side cells in solid: search (hard),
            # bridge, taps and later tiles route around; tile stamps
            # are already done, repeater cells were already unroutable.
            for _sx, _sz in ((ox, gz - 1), (ox, gz + 1),
                             (ox, gz + 3), (ox, gz + 5)):
                ctx.solid[(_sx, _sz)] = ("cmpside", o)
            pa, pb, po = (ox + 3, gz), (ox + 3, gz + 4), (ox - 2, gz + 6)
            pos[o] = po
            ctx.recs.append((op, o, a, (pa, pb, po)))
            placed = True
        except RuntimeError:
            place.restore(s)
        if placed:
            break
    if not placed:
        raise RuntimeError(f"XOR blocked for {o}")


def place_not(ctx, place, g, i, ox, gz, pos):
    op, o, a = g["op"], g["out"], g["args"]
    dv = pos.get(a[0])
    cands = []
    if dv is not None and dv not in ctx.junctions:
        cands.append((dv[0] + 3, dv[1], True))
    cands.append((ox, gz, False))
    placed = False
    for bx, bz, local in cands:
        rows = [(bx, bz)] if local else place.gridrows(bx, bz)
        for bx3, bz3 in rows:
            if local and (abs(bx3 - ox) > 16 or abs(bz3 - gz) > 7):
                break
            if not place.spot_free("NOT", bx3, bz3, i):
                continue
            s = place.snap()
            try:
                bx, bz = bx3, bz3
                nets = own(o, *a)
                stamp_cobble(ctx, bx, bz, o)
                stamp_torch(ctx, bx + 1, bz, o)
                for rx, rz in ((bx - 1, bz), (bx + 1, bz), (bx, bz - 1), (bx, bz + 1),
                               (bx + 2, bz), (bx + 1, bz - 1), (bx + 1, bz + 1)):
                    ring(ctx, rx, rz, nets)
                # ponytail: input stub must APPROACH the host along the axis
                # it points at (dust_points) — same reshape as the AND ~a stub
                # (67987b0). The old bare port (bx-1,bz) let the router arrive
                # from any side; from the north it left an end cell pointing
                # N/S that never powered the host. This E-W stub ends at
                # (bx-1,bz), which points east into the host no matter where
                # the router reaches the open load (bx-2,bz) from.
                # ponytail: funnel like the AND inputs (a repeater here
                # back-feeds its supply through the host block — permanent
                # latch; reverted). Straight dust reads identically either
                # convention.
                stamp_wire(ctx, [(bx - 2, bz), (bx - 1, bz)], a[0])
                for _fx, _fz in ((bx - 2, bz - 1), (bx - 1, bz - 1),
                                 (bx - 2, bz + 1), (bx - 1, bz + 1)):
                    stamp_cobble(ctx, _fx, _fz, o)
                if (bx + 2, 1, bz) in ctx.wires:
                    raise RuntimeError(f"out cell blocked at {(bx + 2, bz)}")
                stamp_wire(ctx, [(bx + 2, bz)], o)
                pos[o] = (bx + 2, bz)
                ctx.recs.append((op, o, a, (bx, bz)))
                placed = True
                break
            except RuntimeError:
                place.restore(s)
        if placed:
            break
    if not placed:
        raise RuntimeError(f"NOT blocked for {o}")


def tap_lamps(ctx, recipe, pos, W, D):
    for name in recipe["outputs"]:
        ox_, oz = pos[name]
        done = False
        for dx, dz in ((1, 0), (0, 1), (0, -1), (-1, 0)):
            fx, lx = (ox_ + dx, oz + dz), (ox_ + dx * 2, oz + dz * 2)
            if not (0 <= lx[0] < W and 0 <= lx[1] < D):
                continue
            if lx in ctx.solid or (lx[0], 1, lx[1]) in ctx.wires or fx in ctx.solid or (fx[0], 1, fx[1]) in ctx.wires:
                continue
            # The tap is stamped after routing, so no route could avoid it —
            # it has to dodge instead, and "occupied" now means a foreign wire
            # BESIDE the tap as well as on it (stamp_wire's adjacency guard).
            if any(ctx.wires.get((fx[0] + ax, 1, fx[1] + az)) not in (None, name)
                   for ax, az in DIRS):
                continue
            stamp_wire(ctx, [fx], name)  # touches out stub: zero-wire tap
            ctx.blocks.append((lx[0], 1, lx[1], "minecraft:redstone_lamp"))
            ctx.solid[lx] = ("lamp", name)
            for ddx, ddz in DIRS:
                ring(ctx, lx[0] + ddx, lx[1] + ddz, own(name))
            ctx.recs.append(("OUT", name, [name], fx))
            done = True
            break
        if not done:
            raise RuntimeError(f"lamp spot taken for {name} at {(ox_, oz)}")
