"""Recipes: parse, evaluate, expand, 8-bit adder builder."""


OPS = ("AND", "OR", "XOR", "NOT")



def parse_recipe(text):
    inputs, outputs, gates = [], [], []
    band = None
    for raw in text.strip().splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("IN "):
            inputs = [s.strip() for s in line[3:].split(",") if s.strip()]
        elif up.startswith("OUT "):
            outputs = [s.strip() for s in line[4:].split(",") if s.strip()]
        elif up.startswith("BAND "):
            # ponytail: optional datapath columns (adder8 pattern). Untagged
            # recipes auto-band exactly as before; nothing else changes.
            try:
                band = int(up[5:].strip())
            except ValueError:
                raise ValueError(f"bad BAND (use: BAND 0): {raw!r}")
        else:
            out, _, expr = line.partition("=")
            out = out.strip()
            parts = expr.strip().split()
            if len(parts) == 3 and parts[1].upper() in ("AND", "OR", "XOR"):
                gates.append({"out": out, "op": parts[1].upper(), "args": [parts[0], parts[2]]})
            elif len(parts) == 3 and parts[0].upper() == "LATCH":
                gates.append({"out": out, "op": "LATCH", "args": [parts[1], parts[2]]})
            elif len(parts) == 2 and parts[0].upper() == "NOT":
                gates.append({"out": out, "op": "NOT", "args": [parts[1]]})
            else:
                raise ValueError(f"can't parse: {raw!r} (use: t = a AND b)")
            if band is not None:
                gates[-1]["band"] = band
    if not inputs or not gates:
        raise ValueError("need at least IN ... and one gate line")
    return {"inputs": inputs, "outputs": outputs, "gates": gates}



def eval_net(recipe, values):
    def val(x):
        if x == "0":
            return False
        if x == "1":
            return True
        return bool(sig[x])
    sig = dict(values)
    for _ in range(20):
        before = dict(sig)
        for g in recipe["gates"]:
            a = [val(x) for x in g["args"]]
            if g["op"] == "AND":
                sig[g["out"]] = a[0] and a[1]
            elif g["op"] == "OR":
                sig[g["out"]] = a[0] or a[1]
            elif g["op"] == "XOR":
                sig[g["out"]] = a[0] != a[1]
            elif g["op"] == "NOT":
                sig[g["out"]] = not a[0]
            elif g["op"] == "NOR":
                sig[g["out"]] = not (a[0] or a[1])
            elif g["op"] == "LATCH":
                o = g["out"]
                # garbage-in: S=R=1 settles at 0 (matches settled hardware).
                # Gauss-Seidel order (qb first) converges hold from any state;
                # synchronous update would ring forever on S=R=0.
                sig[o + "~qb"] = not (a[0] or sig.get(o, False))
                sig[o] = not (a[1] or sig.get(o + "~qb", False))
        if sig == before:
            break
    else:
        raise ValueError("no stable state (oscillating loop?)")
    return sig



def expand_gates(gates, inputs=()):
    """Crossing relays: no net spans more than one band gap (bus v2).
    Unbanded recipes are topo-columned first (the order layout() used),
    then every cross-band hop goes through buf = x AND x: one shared
    buffer per (net, band), chained producer→consumers and parked by the
    normal band machinery. Inputs chain from a single head (one lever
    downstream); constants never chain; same-band hops stay direct.
    (Subsumes fanout chains + per-band replication.)"""
    gates = [dict(g, args=list(g["args"])) for g in gates]
    c = [0]

    def T(p):
        c[0] += 1
        return f"_{p}{c[0]}"
    # ponytail: topo-column unbanded first (layout()'s old order, verbatim).
    # layout() then sees bands and skips its own sort — same columns either way.
    if not any(g.get("band") is not None for g in gates):
        by_out = {}
        for i, g in enumerate(gates):
            by_out.setdefault(g["out"], i)
        deps = {i: {by_out[a] for a in g["args"] if a in by_out and by_out[a] != i}
                for i, g in enumerate(gates)}
        ready = sorted(i for i, d in deps.items() if not d)
        order = []
        while ready:
            i = ready.pop(0)
            order.append(i)
            for j, d in deps.items():
                if i in d:
                    d.discard(i)
                    if not d and j not in order and j not in ready:
                        ready.append(j)
            ready.sort()
        if len(order) == len(gates):
            gates = [gates[i] for i in order]
        for i, g in enumerate(gates):
            g.setdefault("band", i)
    for g in gates:
        if g.get("band") is None:
            g["band"] = 0  # unbanded stragglers (shared head like n1/n0): band 0, chains cover the rest
    by_out = {}
    for i, g in enumerate(gates):
        by_out.setdefault(g["out"], i)
    buf = {}
    out = []
    for g in gates:
        nargs = []
        for a in g["args"]:
            if a in ("0", "1") or a in inputs:
                # constants and inputs never chain: constants tie off,
                # inputs fan out via one lever per load at stamp time.
                nargs.append(a)
                continue
            db = gates[by_out[a]].get("band", 0)
            lb = g.get("band", 0)
            if lb <= db:
                nargs.append(a)
                continue
            prev = a
            for k in range(db + 1, lb + 1):
                if (a, k) not in buf:
                    bn = T("rl")
                    buf[(a, k)] = bn
                    out.append({"out": bn, "op": "AND", "args": [prev, prev],
                                "band": k, "relay": True})
                prev = buf[(a, k)]
            nargs.append(prev)
        out.append(dict(g, args=nargs))
    return out


def minimize_recipe(recipe):
    """Quine-McCluskey: fewest-gate equivalent AND/OR/NOT form (unbanded).
    Returns the original recipe when minimization cannot shrink gate count.
    # ponytail: 10-input cap (tables <=1024 rows, instant); SOP explosion
    # bails out (factored forms like XOR chains beat flat SOP: keep them);
    # banded datapaths pass through (band tags are load-bearing)."""
    if any(g.get("band") is not None for g in recipe["gates"]):
        return recipe
    if any(g["op"] == "LATCH" for g in recipe["gates"]):
        return recipe  # stateful: no combinational truth table to minimize
    ins = recipe["inputs"]
    if not ins or len(ins) > 10:
        return recipe
    orig = list(recipe["gates"])
    newgates = []
    c = [0]

    def T(p):
        c[0] += 1
        return f"_m{c[0]}"

    for out in recipe["outputs"]:
        ones = []
        for k in range(2 ** len(ins)):
            vec = {ins[j]: (k >> j) & 1 for j in range(len(ins))}
            if eval_net(recipe, vec).get(out):
                ones.append(k)
        if not ones or len(ones) == 2 ** len(ins):
            return recipe  # constant fn: no gate form considered here
        cubes = sorted({"".join(str((k >> j) & 1) for j in range(len(ins)))
                        for k in ones})
        primes = set()
        while cubes:
            used, nxt = set(), set()
            for a in cubes:
                for b in cubes:
                    if a >= b:
                        continue
                    d = [i for i in range(len(ins)) if a[i] != b[i]]
                    if len(d) == 1 and a[d[0]] != "-" and b[d[0]] != "-":
                        nxt.add(a[:d[0]] + "-" + a[d[0] + 1:])
                        used.add(a)
                        used.add(b)
            primes |= set(cubes) - used
            cubes = sorted(nxt)
        cover = {p: [k for k in ones
                     if all(p[j] == "-" or p[j] == str((k >> j) & 1)
                            for j in range(len(ins)))]
                 for p in sorted(primes)}
        if len(primes) > 24:
            return recipe  # SOP explosion: factored original wins
        need = set(ones)
        chosen = sorted(p for p in cover
                        if any(sum(1 for q in cover if k in cover[q]) == 1
                               for k in cover[p]))
        for p in chosen:
            need -= set(cover[p])
        rest = sorted(p for p in cover if p not in chosen)
        if len(rest) > 18:
            return recipe  # cover search intractable: factored original wins
        bestsel = None
        for mask in range(2 ** len(rest)):
            sel = [rest[i] for i in range(len(rest)) if mask >> i & 1]
            hit = set()
            for p in sel:
                hit |= set(cover[p])
            if need <= hit and (bestsel is None or len(sel) < len(bestsel)):
                bestsel = sel
        terms = chosen + (bestsel or [])
        notcache = {}
        tnames = []
        single_lit = len(terms) == 1 and \
            sum(1 for j in range(len(ins)) if terms[0][j] != "-") == 1
        for p in terms:
            lits = []
            for j in range(len(ins)):
                if p[j] == "1":
                    lits.append(ins[j])
                elif p[j] == "0":
                    if (out, ins[j]) not in notcache:
                        notcache[(out, ins[j])] = T("n")
                        newgates.append({"out": notcache[(out, ins[j])],
                                         "op": "NOT", "args": [ins[j]]})
                    lits.append(notcache[(out, ins[j])])
            if not lits:
                return recipe  # constant-1 term: no gate form considered here
            t = lits[0]
            for lit in lits[1:]:
                nt = T("a")
                newgates.append({"out": nt, "op": "AND", "args": [t, lit]})
                t = nt
            tnames.append(t)
        if single_lit:
            newgates.append({"out": out, "op": "AND",
                             "args": [tnames[0], tnames[0]]})
        elif len(tnames) == 1:
            newgates[-1]["out"] = out  # lone term's last AND is the output
        else:
            t = tnames[0]
            for nxt in tnames[1:-1]:
                nt = T("o")
                newgates.append({"out": nt, "op": "OR", "args": [t, nxt]})
                t = nt
            newgates.append({"out": out, "op": "OR",
                             "args": [t, tnames[-1]]})
    if len(newgates) >= len(orig):
        return recipe
    return {"inputs": list(ins), "outputs": list(recipe["outputs"]),
            "gates": newgates}



def build_adder8():
    """8-bit ripple-carry adder. Bit i lives in band i (datapath columns)."""
    ins = [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]
    gates = []
    for i in range(8):
        a, b, cin, cout = f"A{i}", f"B{i}", f"C{i}", f"C{i+1}"
        if i == 0:
            cin = "0"
        gates += [{"out": f"X{i}", "op": "XOR", "args": [a, b], "band": i},
                  {"out": f"S{i}", "op": "XOR", "args": [f"X{i}", cin], "band": i},
                  {"out": f"T{i}", "op": "AND", "args": [a, b], "band": i},
                  {"out": f"U{i}", "op": "AND", "args": [f"X{i}", cin], "band": i},
                  {"out": cout, "op": "OR", "args": [f"T{i}", f"U{i}"], "band": i}]
    return {"inputs": ins, "outputs": [f"S{i}" for i in range(8)] + ["C8"], "gates": gates}


if __name__ == "__main__":
    # ponytail: ONE runnable check — clumsy 4-gate recipe collapses to 1,
    # xor keeps its factored 4-gate form (flat SOP would be 5: guard keeps it).
    _clumsy = {"inputs": ["a", "b"], "outputs": ["y"],
               "gates": [{"out": "n1", "op": "NOT", "args": ["b"]},
                         {"out": "t1", "op": "AND", "args": ["a", "b"]},
                         {"out": "t2", "op": "AND", "args": ["a", "n1"]},
                         {"out": "y", "op": "OR", "args": ["t1", "t2"]}]}
    _min = minimize_recipe(_clumsy)
    assert len(_min["gates"]) == 1, _min["gates"]
    for _k in range(4):
        _v = {"a": (_k >> 0) & 1, "b": (_k >> 1) & 1}
        assert eval_net(_min, _v)["y"] == eval_net(_clumsy, _v)["y"], _v
    _xor = {"inputs": ["a", "b"], "outputs": ["y"],
            "gates": [{"out": "y", "op": "XOR", "args": ["a", "b"]}]}
    assert all(not g.get("relay") for g in expand_gates(_xor["gates"], _xor["inputs"]))  # unbanded: tile, no explosion
    assert len(minimize_recipe(_xor)["gates"]) == 1  # SOP-5 loses to factored 1
    print("minimize ok: clumsy->1 gate, xor keeps factored form")
    # ponytail: crossing relays — every hop spans <=1 band gap, parity kept.
    _r4 = {"inputs": ["D", "W"], "outputs": ["Q"],
           "gates": [{"out": "nD", "op": "NOT", "args": ["D"]},
                     {"out": "S", "op": "AND", "args": ["D", "W"]},
                     {"out": "R", "op": "AND", "args": ["nD", "W"]},
                     {"out": "Q", "op": "LATCH", "args": ["S", "R"]}]}
    _fx = expand_gates(_r4["gates"], _r4["inputs"])
    _bo = {}
    for _i, _g in enumerate(_fx):
        _bo.setdefault(_g["out"], _i)
    for _g in _fx:
        for _a in _g["args"]:
            if _a in ("0", "1") or _a in _r4["inputs"]:
                continue
            _db = _fx[_bo[_a]].get("band", 0)
            _lb = _g.get("band", 0)
            assert 0 <= _lb - _db <= 1, (_g["out"], _a, _db, _lb)
    assert any(_g.get("relay") for _g in _fx), _fx
    _r4m = {"inputs": ["D", "W"], "outputs": ["Q"], "gates": _fx}
    from itertools import product as _prod
    for _vals in _prod([0, 1], repeat=2):
        _v = dict(zip(["D", "W"], _vals))
        _a, _b = eval_net(_r4m, _v), eval_net(_r4, _v)
        assert _a["Q"] == _b["Q"], _v
    print("relay ok: hops intra-gap-local, 4-gate parity on all vectors")
    _fb = [{"out": "s", "op": "AND", "args": ["p", "q"], "band": 0},
           {"out": "o1", "op": "AND", "args": ["s", "u"], "band": 1},
           {"out": "o2", "op": "AND", "args": ["s", "v"], "band": 1}]
    _gx = expand_gates(_fb, ["p", "q", "u", "v"])
    _bufs = [_g for _g in _gx if _g.get("relay")]
    assert len(_bufs) == 1 and _bufs[0]["band"] == 1, _gx  # shared per (net, band)
    _lat = {"inputs": ["S", "R"], "outputs": ["Q"],
            "gates": [{"out": "Q", "op": "LATCH", "args": ["S", "R"]}]}
    assert eval_net(_lat, {"S": 1, "R": 0})["Q"] is True
    assert eval_net(_lat, {"S": 0, "R": 1})["Q"] is False
    assert eval_net(_lat, {"S": 1, "R": 1})["Q"] is False
    _lp = parse_recipe("IN S, R\nOUT Q\nQ = LATCH S R\n")
    assert _lp["gates"] == [{"out": "Q", "op": "LATCH", "args": ["S", "R"]}], _lp
    _le = expand_gates(_lp["gates"], _lp["inputs"])
    assert len(_le) == 1 and _le[0]["out"] == "Q" and not _le[0].get("relay"), _le
    print("latch ok: LATCH passes expansion through for the custom tile")

