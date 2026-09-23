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

