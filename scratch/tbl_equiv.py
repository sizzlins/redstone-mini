"""Exhaustive equivalence check: old tuple tables vs new int tables.

NEVER HANGS: one build, both table sets built once, every cell compared, no
simulation at all. Usage:

    python scratch/tbl_equiv.py [build.pkl]

The int-index rewrite must produce tables that are EQUIVALENT, not merely
similar. This converts both representations back to a common form (cell
tuples, with the wake KIND restored) and compares every entry of every table,
so a rewrite bug shows up as a named cell and a named table instead of as
"some vectors settle one tick earlier". It is the check that separates "the
tables are wrong" from "the ring loop is wrong".
"""
import os
import sys
import pickle

sys.path.insert(0, r"D:\redstone-mini")
sys.path.insert(0, r"D:\redstone-mini\scratch")
os.environ.pop("REDSTONE_SIM_GATE", None)
import sim                      # noqa: E402
import simvec                   # noqa: E402
import simvec_old               # noqa: E402

BAD = 0


def note(what, detail):
    global BAD
    BAD += 1
    if BAD <= 25:
        print(f"  MISMATCH {what}: {detail}")


def norm_old_lev(spec):
    """('d',cell)->(1,cell) style, matching the new int codes."""
    if spec is None:
        return None
    m = {"d": 1, "l": 2, "t": 3, "c": 6, "k": 7, "z": 8}
    if spec[0] == "r":
        return (4, None) if len(spec) == 1 else (5, spec[1])
    return (m[spec[0]], spec[1])


def make_norm_new(ids):
    """(int code, id) -> (int code, cell). Code 2 carries a lever NAME and
    codes 4/8 carry nothing, so they pass through untouched."""
    def f(spec):
        if spec is None:
            return None
        code, payload = spec
        if code in (2, 4, 8):
            return (code, None if code != 2 else payload)
        return (code, ids[payload])
    return f


def main():
    dp = sys.argv[1] if len(sys.argv) > 1 else r"D:\redstone-mini\scratch\alu1merge.pkl"
    d = pickle.load(open(dp, "rb"))
    P = sim._parse_build(d["blocks"], d["io"])
    O = simvec_old._tables_from(P, {})
    N = simvec._tables_from(P, {})
    ids = N["cell"]
    cid = N["cid"]
    KIND = {0: "d", 1: "c", 2: "t", 4: "r", 6: "k", 9: "?"}

    print(f"{os.path.basename(dp)}: ncells old={O['ncells']} new={N['ncells']} "
          f"id universe={N['nid']}")
    if O["ncells"] != N["ncells"]:
        note("ncells", f"{O['ncells']} vs {N['ncells']}")

# ---- wake: subset check, not equality (the map is filtered on purpose) ---
    # REDSTONE_WAKE_EXACT=1 keeps only edges some table relation actually
    # reads, so the exact wake is legitimately SMALLER than the geometric one
    # (measured: 279376 -> 126946 edges on alu4, 54.6% dead). What must hold is
    # that it is a SUBSET -- an exact map can drop dead edges but never a live
    # one -- and that the dropped ones are genuinely unreferenced, which is
    # scratch/wake_miss.py's job (it scans every table generically).
    dead = 0
    bad = 0
    import os as _os
    exact = _os.environ.get("REDSTONE_WAKE_EXACT", "1") == "1"
    for c, oldw in O["wake"].items():
        if c not in cid:
            dead += 1
            continue
        old_set = {m for _, m in oldw}
        # the new engine stores IDS; convert back to cells or the comparison is
        # ids against tuples and everything looks like an EXTRA
        new_set = {ids[m] for m in N["wake"][cid[c]]}
        extra = new_set - old_set
        if extra:
            bad += 1
            if bad <= 10:
                note(f"wake[{c}] EXTRA", f"not in geometric map: {extra}")
    print(f"  wake: geometric edges {sum(len(v) for v in O['wake'].values())}"
          f"  exact edges "
          f"{sum(len(N['wake'][i]) for i in range(N['nid']))}"
          f"  (exact filter {'ON' if exact else 'OFF'})")
    print(f"  (old wake entries for never-evaluated cells, dropped: {dead})")
    for i in range(N["nid"]):
        if ids[i] not in O["wake"] and N["wake"][i]:
            note("wake missing cell", ids[i])

    # ---- dust: per-code classes must partition the old direction list ---
    for c, dirs in O["d_dirs"].items():
        i = cid[c]
        got = {"t": [], "l": [], "rblk": 0, "c": [], "d": [], "r": [], "k": [],
               "cup": [], "cdn": []}
        for m, code, payload, cup, cdn in dirs:
            if code == 1:
                got["t"].append(m)
            elif code == 2:
                got["l"].append(payload)
            elif code == 3:
                got["rblk"] = 1
            elif code in (4, 8):
                got["c"].append(m)
            elif code == 5:
                got["d"].append(m)
            elif code == 6:
                got["r"].append(m)
            elif code == 7:
                got["k"].append(m)
            if cup is not None:
                got["cup"].append(cup)
            if cdn is not None:
                got["cdn"].append(cdn)
        exp = {
            "t": [ids[x] for x in N["d_torch"][i]],
            "l": list(N["d_lev"][i]),
            "rblk": N["d_rblk"][i],
            "c": [ids[x] for x in N["d_cob"][i]],
            "d": [ids[x] for x in N["d_dust"][i]],
            "r": [ids[x] for x in N["d_rep"][i]],
            "k": [ids[x] for x in N["d_comp"][i]],
            "cup": [ids[x] for x in N["d_cup"][i]],
            "cdn": [ids[x] for x in N["d_cdn"][i]],
        }
        for k in got:
            if got[k] != exp[k]:
                note(f"dust[{c}].{k}", f"old={got[k]} new={exp[k]}")
        bt, bp = O["d_below"][c]
        nbt = ids[N["d_bt"][i]] if N["d_bt"][i] >= 0 else None
        nbp = ids[N["d_bp"][i]] if N["d_bp"][i] >= 0 else None
        below = (c[0], c[1] - 1, c[2])
        if bool(bt) != (nbt is not None) or (bt and nbt != below):
            note(f"dust[{c}].d_bt", f"old={bt}/{nbt}")
        if bool(bp) != (nbp is not None) or (bp and nbp != below):
            note(f"dust[{c}].d_bp", f"old={bp}/{nbp}")

    # ---- solids ---------------------------------------------------------
    for c in O["pwr"]:
        i = cid[c]
        pairs = (("c_dust", O["c_dust"].get(c, ())),
                 ("c_rep", O["c_rep"].get(c, ())),
                 ("c_torch", O["c_torch"].get(c, ())))
        for k, oldv in pairs:
            newv = [ids[x] for x in N[k][i]]
            if list(oldv) != newv:
                note(f"{k}[{c}]", f"old={list(oldv)} new={newv}")
        if list(O["c_lev"].get(c, ())) != list(N["c_lev"][i]):
            note(f"c_lev[{c}]", f"old={list(O['c_lev'].get(c,()))} "
                                f"new={list(N['c_lev'][i])}")
        if bool(O["c_rblk"].get(c)) != bool(N["c_rblk"][i]):
            note(f"c_rblk[{c}]", f"old={O['c_rblk'].get(c)} new={N['c_rblk'][i]}")
        ou, nu = O["c_up"].get(c), N["c_up"][i]
        if (ou is None) != (nu < 0) or (ou is not None and ids[nu] != ou):
            note(f"c_up[{c}]", f"old={ou} new={nu}")

# ---- repeaters / comparators ---------------------------------------
    nn = make_norm_new(ids)
    for c in O["r_src"]:
        i = cid[c]
        if norm_old_lev(O["r_src"][c]) != nn(N["r_src"][i]):
            note(f"r_src[{c}]", f"old={O['r_src'][c]} new={nn(N['r_src'][i])}")
    for c in O["r_side"]:
        i = cid[c]
        o = O["r_side"][c]
        n = N["r_side"][i]
        if (norm_old_lev(o[0]), norm_old_lev(o[1])) != (nn(n[0]), nn(n[1])):
            note(f"r_side[{c}]", f"old={o} new={n}")
    for c in O["rep"]:
        if O["repdelay"].get(c, 1) != N["r_delay"][cid[c]]:
            note(f"r_delay[{c}]", f"old={O['repdelay'].get(c,1)} "
                                  f"new={N['r_delay'][cid[c]]}")
    for c in O["k_rear"]:
        i = cid[c]
        if norm_old_lev(O["k_rear"][c]) != nn(N["k_rear"][i]):
            note(f"k_rear[{c}]", f"old={O['k_rear'][c]} new={nn(N['k_rear'][i])}")
        o = O["k_side"][c]
        n = N["k_side"][i]
        if (norm_old_lev(o[0]), norm_old_lev(o[1])) != (nn(n[0]), nn(n[1])):
            note(f"k_side[{c}]", f"old={o} new={n}")
        if O["k_mode"][c] != N["k_mode"][i]:
            note(f"k_mode[{c}]", f"old={O['k_mode'][c]} new={N['k_mode'][i]}")
    for c in O["torch"]:
        i = cid[c]
        if ids[N["t_att"][i]] != O["t_att"][c]:
            note(f"t_att[{c}]", f"old={O['t_att'][c]} new={ids[N['t_att'][i]]}")
        if bool(O["t_dead"][c]) != bool(N["t_dead"][i]):
            note(f"t_dead[{c}]", f"old={O['t_dead'][c]} new={N['t_dead'][i]}")

# ---- lamps ----------------------------------------------------------
    for c in O["lampnet"]:
        i = cid[c]
        if list(O["l_arm"][c]) != [ids[x] for x in N["l_arm"][i]]:
            note(f"l_arm[{c}]", f"old={O['l_arm'][c]} new={N['l_arm'][i]}")
        for k in ("l_cob", "l_torch"):
            if list(O[k][c]) != [ids[x] for x in N[k][i]]:
                note(f"{k}[{c}]", f"old={O[k][c]} new={N[k][i]}")
        if list(O["l_lev"].get(c, ())) != list(N["l_lev"][i]):
            note(f"l_lev[{c}]", "")
        if bool(O["l_rblk"].get(c)) != bool(N["l_rblk"][i]):
            note(f"l_rblk[{c}]", "")
        ou, nu = O["l_up"].get(c), N["l_up"][i]
        if (ou is None) != (nu < 0) or (ou is not None and ids[nu] != ou):
            note(f"l_up[{c}]", f"old={ou} new={nu}")

    # ---- role id tuples -------------------------------------------------
    for k_old, k_new in (("dust", "dust_ids"), ("torch", "torch_ids"),
                         ("rep", "rep_ids"), ("comp", "comp_ids")):
        old_ids = [cid[c] for c in O[k_old]]
        if old_ids != list(N[k_new]):
            note(k_new, f"old-order {[cid[c] for c in O[k_old]][:8]} "
                        f"new-order {list(N[k_new])[:8]}")
    if [cid[c] for c in O["pwr"]] != list(N["pwr_ids"]):
        note("pwr_ids", "order differs")

    print(f"\n{'TABLES EQUIVALENT' if not BAD else str(BAD) + ' MISMATCHES'}")
    sys.exit(1 if BAD else 0)


if __name__ == "__main__":
    main()
