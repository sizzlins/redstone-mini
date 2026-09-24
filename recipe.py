"""Recipes: parse, evaluate, expand, 8-bit adder builder."""


OPS = ("AND", "OR", "XOR", "NOT")



def parse_recipe(text):
    inputs, outputs, gates = [], [], []
    for raw in text.strip().splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("IN "):
            inputs = [s.strip() for s in line[3:].split(",") if s.strip()]
        elif up.startswith("OUT "):
            outputs = [s.strip() for s in line[4:].split(",") if s.strip()]
        else:
            out, _, expr = line.partition("=")
            out = out.strip()
            parts = expr.strip().split()
            if len(parts) == 3 and parts[1].upper() in ("AND", "OR", "XOR"):
                gates.append({"out": out, "op": parts[1].upper(), "args": [parts[0], parts[2]]})
            elif len(parts) == 2 and parts[0].upper() == "NOT":
                gates.append({"out": out, "op": "NOT", "args": [parts[1]]})
            else:
                raise ValueError(f"can't parse: {raw!r} (use: t = a AND b)")
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
    return sig



def expand_gates(gates):
    """XOR->OR,AND,NOT,AND. AND stays a compound, OR a junction, NOT a tile.
    Banded OR (dense datapath) expands to NOR+NOT (proven tiles, spread ports,
    no junction funnel); unbanded keeps the compact repeater junction."""
    gates = [dict(g, args=list(g["args"])) for g in gates]
    c = [0]
    def T(p):
        c[0] += 1
        return f"_{p}{c[0]}"
    banded = any(g.get("band") is not None for g in gates)
    changed = True
    while changed:
        changed = False
        nxt = []
        for g in gates:
            op, o, a = g["op"], g["out"], g["args"]
            bd = g.get("band")
            if op == "OR" and banded:
                n = T("no")
                nxt += [{"out": n, "op": "NOR", "args": [a[0], a[1]], "band": bd},
                        {"out": o, "op": "NOT", "args": [n], "band": bd}]
                changed = True
            elif op == "XOR":
                t1, t2, t3 = T("xo"), T("xa"), T("xn")
                nxt += [{"out": t1, "op": "OR", "args": [a[0], a[1]], "band": bd},
                        {"out": t2, "op": "AND", "args": [a[0], a[1]], "band": bd},
                        {"out": t3, "op": "NOT", "args": [t2], "band": bd},
                        {"out": o, "op": "AND", "args": [t1, t3], "band": bd}]
                changed = True
            else:
                nxt.append(g)
        gates = nxt
    return gates


def minimize_recipe(recipe):
    """Quine-McCluskey: fewest-gate equivalent AND/OR/NOT form (unbanded).
    Returns the original recipe when minimization cannot shrink gate count.
    # ponytail: 10-input cap (tables <=1024 rows, instant); SOP explosion
    # bails out (factored forms like XOR chains beat flat SOP: keep them);
    # banded datapaths pass through (band tags are load-bearing)."""
    if any(g.get("band") is not None for g in recipe["gates"]):
        return recipe
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
            "gates": [dict(g) for g in expand_gates(
                [{"out": "y", "op": "XOR", "args": ["a", "b"]}])]}
    assert len(minimize_recipe(_xor)["gates"]) == 4
    print("minimize ok: clumsy->1 gate, xor keeps factored form")

