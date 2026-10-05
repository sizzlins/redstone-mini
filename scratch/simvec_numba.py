"""Numba-compiled mirror of simvec.run_scalar's table engine.

ADDITIVE PROTOTYPE, not the shipped engine: simvec.py is untouched. This file
converts simvec's tables to numpy once per build (CSR for every id list,
specs as (code, payload) int pairs with lever names mapped to input indices)
and runs the same event loop in njit. Goal: identical 6-tuple (lamps, live,
torch, ticks, rep, comp) at a fraction of the Python overhead.

NEVER HANGS: fixed caps from sim (ticks/steps/stall/burnout), no pool, no
compose, no unbounded structures (ring buckets are typed lists drained by
replacement; torch toggle windows are fixed 128-slot arrays). snap_at/init/
target_hits/_warm delegate to simvec.run_scalar.

Usage: python scratch/nb_diff.py [nvec]  (A/B vs simvec, all six fields)
"""
import os as _os
import sys as _sys

# ponytail: `python scratch/*.py` puts scratch/ first on sys.path, where the
# repo's coverage.py SHADOWS the installed coverage package; numba then dies
# in coverage_support (`coverage.types.Tracer`) and the pre-import would hit
# the shadow too. Import the real one with scratch/ off the path first --
# afterwards sys.modules satisfies numba without further path games.
_path_saved = _sys.path[:]
_sys.path[:] = [p for p in _sys.path
                if _os.path.basename(p.rstrip("/\\")).lower() != "scratch"]
try:
    import coverage.types  # noqa: F401
finally:
    _sys.path[:] = _path_saved
del _path_saved
import numpy as _np
from numba import njit as _njit
from numba import types as _ntypes
from numba.typed import List as _TList

_sys.path.insert(0, r"D:\redstone-mini")
_sys.path.insert(0, r"D:\redstone-mini\scratch")
_os.environ.pop("REDSTONE_SIM_GATE", None)
_os.environ["REDSTONE_SIM_TICKS"] = "20000"
_os.environ["REDSTONE_SIM_STEPS"] = "2000000"

import sim as _sim
import simvec as _simvec

K_D, K_C, K_T, K_R, K_K, K_X = 0, 1, 2, 4, 6, 9

_NP = {}


def _csr(lists, nid):
    off = _np.zeros(nid, dtype=_np.int64)
    ln = _np.zeros(nid, dtype=_np.int64)
    tot = 0
    for c in range(nid):
        v = lists[c]
        ln[c] = len(v)
        off[c] = tot
        tot += len(v)
    data = _np.zeros(max(tot, 1), dtype=_np.int64)
    for c in range(nid):
        v = lists[c]
        o = off[c]
        for j, m in enumerate(v):
            data[o + j] = m
    return off, ln, data


def _spec_pair(spec):
    if spec is None:
        return (-1, -1)
    return (spec[0], spec[1])


def _bundle_load(tag, fp):
    # ponytail: cross-process bundle cache. The filename carries the fp AND
    # the payload carries it; both must match, otherwise rebuild. Atomic
    # save (tmp + replace) means readers only ever see complete files, so a
    # racing build is benign (identical content, last writer wins). Own
    # files only -- never a trust boundary, pickle is fine.
    try:
        with open(tag, "rb") as f:
            import pickle as _pk
            d = _pk.load(f)
    except Exception:  # noqa: BLE001 -- missing/corrupt/racing: rebuild
        return None
    if not isinstance(d, dict) or d.get("_fp") != fp:
        return None
    return d


def _bundle_save(tag, d):
    try:
        import pickle as _pk
        tmp = "%s.tmp-%d" % (tag, _os.getpid())
        with open(tmp, "wb") as f:
            _pk.dump(d, f, protocol=4)
        _os.replace(tmp, tag)
    except Exception:  # noqa: BLE001 -- cache best-effort, never fatal
        pass


def build_np(ctx, inputs, tag=None, fp=None):
    """Convert simvec tables to numpy. Memoised per (ctx, inputs).

    tag/fp enable the cross-process bundle file: with both given, a matching
    bundle loads in ~0.5s instead of converting (~2.4s) in every worker.
    ponytail: inputs are canonicalized to sorted order HERE, once, because
    two callers disagreed (parent pre-build used recipe order, run_scalar
    uses sorted) and the bundle silently carried the wrong input mapping --
    every worker then fed scrambled inputs and went RED. One canonical order
    makes memo keys, bundles and varr agree by construction.
    """
    inputs = tuple(sorted(inputs))
    k = (id(ctx), inputs)
    e = _NP.get(k)
    if e is not None and e[0] is ctx:
        return e[1]
    if len(_NP) > 8:
        _NP.clear()
    if tag is not None and fp is not None:
        d = _bundle_load(tag, fp)
        if d is not None:
            _NP[k] = (ctx, d)
            return d
    st = _simvec._tables(ctx)
    nid = st["nid"]
    idx = {p: i for i, p in enumerate(inputs)}

    def _lev_csr(table):
        out = []
        for c in range(nid):
            ids = []
            for nm in table[c]:
                ids.append(idx.get(nm, -1))
            out.append(ids)
        return _csr(out, nid)

    d = {}
    d["nid"] = nid
    d["kind"] = _np.array(list(st["kind"]), dtype=_np.int64)
    for name in ("dust_ids", "pwr_ids", "torch_ids", "rep_ids", "comp_ids"):
        d[name] = _np.array(list(st[name]), dtype=_np.int64)
    d["seed_order"] = _np.concatenate(
        [d["dust_ids"], d["pwr_ids"], d["torch_ids"], d["rep_ids"],
         d["comp_ids"]])
    for name in ("d_torch", "d_cob", "d_dust", "d_rep", "d_comp", "d_cup",
                 "d_cdn", "c_dust", "c_rep", "c_torch"):
        d[name + "_off"], d[name + "_ln"], d[name] = _csr(st[name], nid)
    d["d_lev_off"], d["d_lev_ln"], d["d_lev"] = _lev_csr(st["d_lev"])
    d["c_lev_off"], d["c_lev_ln"], d["c_lev"] = _lev_csr(st["c_lev"])
    d["d_bt"] = _np.array(list(st["d_bt"]), dtype=_np.int64)
    d["d_bp"] = _np.array(list(st["d_bp"]), dtype=_np.int64)
    d["d_rblk"] = _np.array(list(st["d_rblk"]), dtype=_np.uint8)
    d["c_rblk"] = _np.array(list(st["c_rblk"]), dtype=_np.uint8)
    d["c_up"] = _np.array(list(st["c_up"]), dtype=_np.int64)
    d["r_delay"] = _np.array(list(st["r_delay"]), dtype=_np.int64)
    d["t_att"] = _np.array(list(st["t_att"]), dtype=_np.int64)
    d["t_dead"] = _np.array(list(st["t_dead"]), dtype=_np.uint8)
    for name in ("r_src", "k_rear"):
        code = _np.full(nid, -1, dtype=_np.int64)
        pay = _np.full(nid, -1, dtype=_np.int64)
        for c in range(nid):
            spec = st[name][c]
            if spec is None:
                continue
            code[c] = spec[0]
            v = spec[1]
            pay[c] = idx.get(v, -1) if spec[0] == 2 else v
        d[name + "_code"] = code
        d[name + "_pay"] = pay
    for name in ("r_side", "k_side"):
        for s in (0, 1):
            code = _np.full(nid, -1, dtype=_np.int64)
            pay = _np.full(nid, -1, dtype=_np.int64)
            for c in range(nid):
                pair = st[name][c]
                spec = pair[s] if pair is not None else None
                if spec is None:
                    continue
                code[c] = spec[0]
                v = spec[1]
                pay[c] = idx.get(v, -1) if spec[0] == 2 else v
            d["%s%d_code" % (name, s)] = code
            d["%s%d_pay" % (name, s)] = pay
    d["k_mode"] = _np.zeros(nid, dtype=_np.uint8)
    for c in range(nid):
        if st["k_mode"][c] == "subtract":
            d["k_mode"][c] = 1
    # wake keeps sign encoding (~m = bool-only edge); flatten signed.
    woff = _np.zeros(nid, dtype=_np.int64)
    wln = _np.zeros(nid, dtype=_np.int64)
    wtot = 0
    for c in range(nid):
        wln[c] = len(st["wake"][c])
        woff[c] = wtot
        wtot += len(st["wake"][c])
    wdata = _np.zeros(max(wtot, 1), dtype=_np.int64)
    for c in range(nid):
        o = woff[c]
        for j, m in enumerate(st["wake"][c]):
            wdata[o + j] = m
    d["wake_off"], d["wake_ln"], d["wake"] = woff, wln, wdata
    # lamp nets
    for name in ("l_arm", "l_cob", "l_torch"):
        d[name + "_off"], d[name + "_ln"], d[name] = _csr(st[name], nid)
    d["l_lev_off"], d["l_lev_ln"], d["l_lev"] = _lev_csr(st["l_lev"])
    d["l_rblk"] = _np.array(list(st["l_rblk"]), dtype=_np.uint8)
    d["l_up"] = _np.array(list(st["l_up"]), dtype=_np.int64)
    lamp_cell = _np.array([i for i, _n in st["lamp_ids"]], dtype=_np.int64)
    d["lamp_cell"] = lamp_cell
    d["lamp_net"] = [n for _i, n in st["lamp_ids"]]
    d["cell"] = list(st["cell"])
    d["ncells"] = st["ncells"]
    d["torch_index"] = _np.full(nid, -1, dtype=_np.int64)
    for k2, tid in enumerate(d["torch_ids"]):
        d["torch_index"][int(tid)] = k2
    if fp is not None:
        d["_fp"] = fp
    _NP[k] = (ctx, d)
    if tag is not None and fp is not None:
        _bundle_save(tag, d)
    return d


@_njit(cache=True)
def _lev_nb(code, pay, pw, pbs, tl, ron, con, vec):
    if code == 1:
        return pw[pay]
    if code == 2:
        return _np.int64(15) if (pay >= 0 and vec[pay]) else _np.int64(0)
    if code == 3:
        return _np.int64(15) if tl[pay] else _np.int64(0)
    if code == 4:
        return _np.int64(15)
    if code == 5:
        return _np.int64(15) if ron[pay] else _np.int64(0)
    if code == 6:
        return _np.int64(15) if pbs[pay] else _np.int64(0)
    if code == 7:
        return con[pay]
    return _np.int64(0)


@_njit(cache=True)
def _dust_lvl_nb(c, d_bt, d_bp, d_rblk, d_torch_off, d_torch_ln, d_torch,
                 d_lev_off, d_lev_ln, d_lev, d_cob_off, d_cob_ln, d_cob,
                 d_dust_off, d_dust_ln, d_dust, d_rep_off, d_rep_ln, d_rep,
                 d_comp_off, d_comp_ln, d_comp, d_cup_off, d_cup_ln, d_cup,
                 d_cdn_off, d_cdn_ln, d_cdn, pw, pbs, tl, ron, con, vec):
    t = d_bt[c]
    if t >= 0 and tl[t]:
        return _np.int64(15)
    p = d_bp[c]
    if p >= 0 and pbs[p]:
        return _np.int64(15)
    if d_rblk[c]:
        return _np.int64(15)
    o = d_cob_off[c]
    for j in range(d_cob_ln[c]):
        if pbs[d_cob[o + j]]:
            return _np.int64(15)
    o = d_torch_off[c]
    for j in range(d_torch_ln[c]):
        if tl[d_torch[o + j]]:
            return _np.int64(15)
    o = d_rep_off[c]
    for j in range(d_rep_ln[c]):
        if ron[d_rep[o + j]]:
            return _np.int64(15)
    o = d_lev_off[c]
    for j in range(d_lev_ln[c]):
        m = d_lev[o + j]
        if m >= 0 and vec[m]:
            return _np.int64(15)
    lv = _np.int64(0)
    o = d_dust_off[c]
    for j in range(d_dust_ln[c]):
        x = pw[d_dust[o + j]] - _np.int64(1)
        if x > lv:
            lv = x
    o = d_comp_off[c]
    for j in range(d_comp_ln[c]):
        x = con[d_comp[o + j]]
        if x > lv:
            lv = x
    o = d_cup_off[c]
    for j in range(d_cup_ln[c]):
        x = pw[d_cup[o + j]] - _np.int64(1)
        if x > lv:
            lv = x
    o = d_cdn_off[c]
    for j in range(d_cdn_ln[c]):
        x = pw[d_cdn[o + j]] - _np.int64(1)
        if x > lv:
            lv = x
    return lv


@_njit(cache=True)
def _cob_state_nb(c, c_dust_off, c_dust_ln, c_dust, c_torch_off, c_torch_ln,
                  c_torch, c_rep_off, c_rep_ln, c_rep, c_lev_off, c_lev_ln,
                  c_lev, c_rblk, c_up, pw, tl, ron, vec):
    if c_rblk[c]:
        return True, True
    o = c_torch_off[c]
    for j in range(c_torch_ln[c]):
        if tl[c_torch[o + j]]:
            return True, True
    o = c_rep_off[c]
    for j in range(c_rep_ln[c]):
        if ron[c_rep[o + j]]:
            return True, True
    o = c_lev_off[c]
    for j in range(c_lev_ln[c]):
        m = c_lev[o + j]
        if m >= 0 and vec[m]:
            return True, True
    pwrd = False
    o = c_dust_off[c]
    for j in range(c_dust_ln[c]):
        if pw[c_dust[o + j]]:
            pwrd = True
    u = c_up[c]
    if u >= 0 and pw[u]:
        pwrd = True
    return pwrd, False


@_njit(cache=True)
def _rep_on_nb(c, r_src_code, r_src_pay, r_side0_code, r_side0_pay,
               r_side1_code, r_side1_pay, pw, pb, tl, ron, con, vec):
    s0c = r_side0_code[c]
    if s0c >= 0 and _lev_nb(s0c, r_side0_pay[c], pw, pb, tl, ron, con,
                            vec) >= 1:
        return bool(ron[c])
    s1c = r_side1_code[c]
    if s1c >= 0 and _lev_nb(s1c, r_side1_pay[c], pw, pb, tl, ron, con,
                            vec) >= 1:
        return bool(ron[c])
    k = r_src_code[c]
    if k < 0:
        return False
    s = r_src_pay[c]
    if k == 1:
        return pw[s] >= 1
    if k == 6:
        return bool(pb[s])
    if k == 2:
        return bool(s >= 0 and vec[s])
    if k == 3:
        return bool(tl[s])
    if k == 4:
        return True
    if k == 5:
        return bool(ron[s])
    if k == 7:
        return con[s] >= 1
    return False


@_njit(cache=True)
def _comp_out_nb(c, k_rear_code, k_rear_pay, k_side0_code, k_side0_pay,
                 k_side1_code, k_side1_pay, k_mode, pw, pbs, tl, ron, con,
                 vec):
    rl = _lev_nb(k_rear_code[c], k_rear_pay[c], pw, pbs, tl, ron, con, vec)
    sl = _np.int64(0)
    c0 = k_side0_code[c]
    if c0 >= 0:
        v = _lev_nb(c0, k_side0_pay[c], pw, pbs, tl, ron, con, vec)
        if v > sl:
            sl = v
    c1 = k_side1_code[c]
    if c1 >= 0:
        v = _lev_nb(c1, k_side1_pay[c], pw, pbs, tl, ron, con, vec)
        if v > sl:
            sl = v
    if k_mode[c] == 1:
        d = rl - sl
        if d > 0:
            return d
        return _np.int64(0)
    if sl <= rl:
        return rl
    return _np.int64(0)


@_njit(cache=True)
def _core_nb(nid, kind, seed_order, wake_off, wake_ln, wake, d_bt, d_bp,
             d_rblk, d_torch_off, d_torch_ln, d_torch, d_lev_off, d_lev_ln,
             d_lev, d_cob_off, d_cob_ln, d_cob, d_dust_off, d_dust_ln, d_dust,
             d_rep_off, d_rep_ln, d_rep, d_comp_off, d_comp_ln, d_comp,
             d_cup_off, d_cup_ln, d_cup, d_cdn_off, d_cdn_ln, d_cdn,
             c_dust_off, c_dust_ln, c_dust, c_torch_off, c_torch_ln, c_torch,
             c_rep_off, c_rep_ln, c_rep, c_lev_off, c_lev_ln, c_lev, c_rblk,
             c_up, r_src_code, r_src_pay, r_side0_code, r_side0_pay,
             r_side1_code, r_side1_pay, r_delay, k_rear_code, k_rear_pay,
             k_side0_code, k_side0_pay, k_side1_code, k_side1_pay, k_mode,
             t_att, t_dead, buckets, qmark, pw, pb, pbs, tl, ron, con,
             tsched, rsched, ksched, flips, bout_times, bout_len, bout_max,
             torch_index, vec, tick_cap, step_cap, stall_cap, bout_n,
             bout_grace):
    # returns (code, now, max_gap); state arrays mutated in place.
    # code: 0 ok, 1 tick/step cap, 2 stall, 3 burnout (tl zeroed at cell in
    #   bout_cell), 4 burnout-cell id in now_out... (see wrapper)
    RING = 5
    now = _np.int64(0)
    steps = _np.int64(0)
    last_change = _np.int64(0)
    max_gap = _np.int64(0)
    bout_cell = _np.int64(-1)
    for c in seed_order:
        buckets[0].append(c)
    alive = _np.int64(len(seed_order))
    while alive > 0:
        if now > tick_cap or steps > step_cap:
            return _np.int64(1), now, max_gap, bout_cell
        i = now % RING
        items = buckets[i]
        n = _np.int64(len(items))
        if n == 0:
            now += _np.int64(1)
            if steps - last_change > stall_cap:
                return _np.int64(2), now, max_gap, bout_cell
            continue
        fresh = _TList.empty_list(_ntypes.int64)
        buckets[i] = fresh
        alive -= n
        here = buckets[i]
        qc = qmark[i]
        for j in range(n):
            it = items[j]
            if it >= 0:
                c = it
                f = False
            else:
                c = ~it
                f = True
            qc[c] = False
            steps += _np.int64(1)
            if steps - last_change > stall_cap:
                return _np.int64(2), now, max_gap, bout_cell
            k = kind[c]
            if k == 0:
                v = _dust_lvl_nb(c, d_bt, d_bp, d_rblk, d_torch_off,
                                 d_torch_ln, d_torch, d_lev_off, d_lev_ln,
                                 d_lev, d_cob_off, d_cob_ln, d_cob,
                                 d_dust_off, d_dust_ln, d_dust, d_rep_off,
                                 d_rep_ln, d_rep, d_comp_off, d_comp_ln,
                                 d_comp, d_cup_off, d_cup_ln, d_cup,
                                 d_cdn_off, d_cdn_ln, d_cdn, pw, pbs, tl,
                                 ron, con, vec)
                if pw[c] != v:
                    old = pw[c]
                    pw[c] = v
                    crossing = (old != 0) != (v != 0)
                    flips[c] += _np.int64(1)
                    g = steps - last_change
                    if g > max_gap:
                        max_gap = g
                    last_change = steps
                    o = wake_off[c]
                    for e in range(wake_ln[c]):
                        c2 = wake[o + e]
                        if c2 < 0:
                            if not crossing:
                                continue
                            c2 = ~c2
                        if not qc[c2]:
                            qc[c2] = True
                            here.append(c2)
                            alive += _np.int64(1)
            elif k == 1:
                pwrd, strong = _cob_state_nb(c, c_dust_off, c_dust_ln, c_dust,
                                             c_torch_off, c_torch_ln, c_torch,
                                             c_rep_off, c_rep_ln, c_rep,
                                             c_lev_off, c_lev_ln, c_lev,
                                             c_rblk, c_up, pw, tl, ron, vec)
                if pb[c] != pwrd or pbs[c] != strong:
                    pb[c] = pwrd
                    pbs[c] = strong
                    flips[c] += _np.int64(1)
                    g = steps - last_change
                    if g > max_gap:
                        max_gap = g
                    last_change = steps
                    o = wake_off[c]
                    for e in range(wake_ln[c]):
                        c2 = wake[o + e]
                        if not qc[c2]:
                            qc[c2] = True
                            here.append(c2)
                            alive += _np.int64(1)
            elif k == 2:
                if f:
                    tsched[c] = _np.uint8(0)
                    a = t_att[c]
                    v = not (pb[a] if a >= 0 else False)
                    if tl[c] != v:
                        if tl[c] and not v:
                            tk = torch_index[c]
                            nl = _np.int64(0)
                            for t2 in range(bout_len[tk]):
                                if now - bout_times[tk, t2] < 30:
                                    bout_times[tk, nl] = bout_times[tk, t2]
                                    nl += _np.int64(1)
                            bout_times[tk, nl] = now
                            nl += _np.int64(1)
                            bout_len[tk] = nl
                            if nl > bout_max[tk]:
                                bout_max[tk] = nl
                            if nl > bout_n and now >= bout_grace:
                                tl[c] = _np.uint8(0)
                                bout_cell = c
                                return _np.int64(3), now, max_gap, bout_cell
                        tl[c] = v
                        flips[c] += _np.int64(1)
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        o = wake_off[c]
                        for e in range(wake_ln[c]):
                            c2 = wake[o + e]
                            if not qc[c2]:
                                qc[c2] = True
                                here.append(c2)
                                alive += _np.int64(1)
                else:
                    if tsched[c] or t_dead[c]:
                        continue
                    a = t_att[c]
                    if (not (pb[a] if a >= 0 else False)) != tl[c]:
                        tsched[c] = _np.uint8(1)
                        tgt = (now + _np.int64(1)) % RING
                        buckets[tgt].append(~c)
                        alive += _np.int64(1)
            elif k == 4:
                if f:
                    rsched[c] = _np.uint8(0)
                    v = _rep_on_nb(c, r_src_code, r_src_pay, r_side0_code,
                                   r_side0_pay, r_side1_code, r_side1_pay,
                                   pw, pb, tl, ron, con, vec)
                    if ron[c] != v:
                        ron[c] = v
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        o = wake_off[c]
                        for e in range(wake_ln[c]):
                            c2 = wake[o + e]
                            if not qc[c2]:
                                qc[c2] = True
                                here.append(c2)
                                alive += _np.int64(1)
                else:
                    if rsched[c]:
                        continue
                    if _rep_on_nb(c, r_src_code, r_src_pay, r_side0_code,
                                  r_side0_pay, r_side1_code, r_side1_pay,
                                  pw, pb, tl, ron, con, vec) != ron[c]:
                        rsched[c] = _np.uint8(1)
                        tgt = (now + r_delay[c]) % RING
                        buckets[tgt].append(~c)
                        alive += _np.int64(1)
            else:
                if f:
                    ksched[c] = _np.uint8(0)
                    v = _comp_out_nb(c, k_rear_code, k_rear_pay,
                                     k_side0_code, k_side0_pay, k_side1_code,
                                     k_side1_pay, k_mode, pw, pbs, tl, ron,
                                     con, vec)
                    if con[c] != v:
                        old = con[c]
                        con[c] = v
                        crossing = (old != 0) != (v != 0)
                        g = steps - last_change
                        if g > max_gap:
                            max_gap = g
                        last_change = steps
                        o = wake_off[c]
                        for e in range(wake_ln[c]):
                            c2 = wake[o + e]
                            if c2 < 0:
                                if not crossing:
                                    continue
                                c2 = ~c2
                            if not qc[c2]:
                                qc[c2] = True
                                here.append(c2)
                                alive += _np.int64(1)
                else:
                    if ksched[c]:
                        continue
                    if _comp_out_nb(c, k_rear_code, k_rear_pay, k_side0_code,
                                    k_side0_pay, k_side1_code, k_side1_pay,
                                    k_mode, pw, pbs, tl, ron, con,
                                    vec) != con[c]:
                        ksched[c] = _np.uint8(1)
                        tgt = (now + _np.int64(1)) % RING
                        buckets[tgt].append(~c)
                        alive += _np.int64(1)
    return _np.int64(0), now, max_gap, bout_cell


@_njit(cache=True)
def _lamps_nb(lamp_cell, l_arm_off, l_arm_ln, l_arm, l_cob_off, l_cob_ln,
              l_cob, l_torch_off, l_torch_ln, l_torch, l_lev_off, l_lev_ln,
              l_lev, l_rblk, l_up, pw, pb, tl, vec):
    n = lamp_cell.shape[0]
    out = _np.zeros(n, dtype=_np.bool_)
    for li in range(n):
        i = lamp_cell[li]
        lit = False
        o = l_arm_off[i]
        for j in range(l_arm_ln[i]):
            if pw[l_arm[o + j]]:
                lit = True
        if not lit and l_up[i] >= 0 and pw[l_up[i]]:
            lit = True
        if not lit:
            o = l_cob_off[i]
            for j in range(l_cob_ln[i]):
                if pb[l_cob[o + j]]:
                    lit = True
        if not lit:
            o = l_torch_off[i]
            for j in range(l_torch_ln[i]):
                if tl[l_torch[o + j]]:
                    lit = True
        if not lit and l_rblk[i]:
            lit = True
        if not lit:
            o = l_lev_off[i]
            for j in range(l_lev_ln[i]):
                m = l_lev[o + j]
                if m >= 0 and vec[m]:
                    lit = True
        out[li] = lit
    return out


def run_scalar(vec, ctx, init=None, until=None, tick_cap=None, step_cap=None,
               stall=None, snap_at=None, target_hits=None, _warm=None,
               _expose=None):
    """Mirror of simvec.run_scalar over the numba core (cold + warm).

    _warm/_expose match simvec's protocol (dicts of 6 level arrays, any
    bytes-like); _warm copies in (the core mutates in place), _expose hands
    out live refs the caller must treat read-only until the next call.
    Anything outside the combinational path (init/snap/targets) delegates
    to simvec.run_scalar. Error STRINGS match simvec's prefixes
    (TORCH BURNOUT / STALLED / settling); dynamic tails may differ.
    """
    if init or snap_at is not None or target_hits:
        return _simvec.run_scalar(vec, ctx, init=init, until=until,
                                  tick_cap=tick_cap, step_cap=step_cap,
                                  stall=stall, snap_at=snap_at,
                                  target_hits=target_hits)
    from sim import _TICK_CAP, _STEP_CAP, _STALL, _BOUT_N, _BOUT_GRACE, _BOUT
    tick_cap = _TICK_CAP if tick_cap is None else tick_cap
    step_cap = _STEP_CAP if step_cap is None else step_cap
    stall = _STALL if stall is None else stall
    inputs = sorted(vec.keys())
    d = build_np(ctx, inputs, tag=_os.environ.get("REDSTONE_NB_BUNDLE"),
                 fp=_os.environ.get("REDSTONE_NB_FP"))
    nid = d["nid"]
    varr = _np.zeros(len(inputs), dtype=_np.bool_)
    idx = {p: i for i, p in enumerate(inputs)}
    for nm, val in vec.items():
        i = idx.get(nm)
        if i is not None and val:
            varr[i] = True
    if _warm is None:
        pw = _np.zeros(nid, dtype=_np.uint8)
        pb = _np.zeros(nid, dtype=_np.uint8)
        pbs = _np.zeros(nid, dtype=_np.uint8)
        tl = _np.zeros(nid, dtype=_np.uint8)
        ron = _np.zeros(nid, dtype=_np.uint8)
        con = _np.zeros(nid, dtype=_np.uint8)
    else:
        # ponytail: MUST copy -- the core mutates in place, and _warm is the
        # previous vector's exposed state (also the next call's fallback).
        pw = _np.array(_warm["pw"], dtype=_np.uint8, copy=True)
        pb = _np.array(_warm["pb"], dtype=_np.uint8, copy=True)
        pbs = _np.array(_warm["pbs"], dtype=_np.uint8, copy=True)
        tl = _np.array(_warm["tl"], dtype=_np.uint8, copy=True)
        ron = _np.array(_warm["ron"], dtype=_np.uint8, copy=True)
        con = _np.array(_warm["con"], dtype=_np.uint8, copy=True)
    tsched = _np.zeros(nid, dtype=_np.uint8)
    rsched = _np.zeros(nid, dtype=_np.uint8)
    ksched = _np.zeros(nid, dtype=_np.uint8)
    flips = _np.zeros(nid, dtype=_np.int64)
    buckets = _TList()
    for _ in range(5):
        buckets.append(_TList.empty_list(_ntypes.int64))
    qmark = _np.zeros((5, nid), dtype=_np.bool_)
    ntorch = len(d["torch_ids"])
    bout_times = _np.zeros((max(ntorch, 1), 128), dtype=_np.int64)
    bout_len = _np.zeros(max(ntorch, 1), dtype=_np.int64)
    bout_max = _np.zeros(max(ntorch, 1), dtype=_np.int64)
    stall_cap = max(stall, 3 * d["ncells"])
    code, now, _gap, bout_cell = _core_nb(
        _np.int64(nid), d["kind"], d["seed_order"], d["wake_off"],
        d["wake_ln"], d["wake"], d["d_bt"], d["d_bp"], d["d_rblk"],
        d["d_torch_off"], d["d_torch_ln"], d["d_torch"], d["d_lev_off"],
        d["d_lev_ln"], d["d_lev"], d["d_cob_off"], d["d_cob_ln"], d["d_cob"],
        d["d_dust_off"], d["d_dust_ln"], d["d_dust"], d["d_rep_off"],
        d["d_rep_ln"], d["d_rep"], d["d_comp_off"], d["d_comp_ln"],
        d["d_comp"], d["d_cup_off"], d["d_cup_ln"], d["d_cup"],
        d["d_cdn_off"], d["d_cdn_ln"], d["d_cdn"], d["c_dust_off"],
        d["c_dust_ln"], d["c_dust"], d["c_torch_off"], d["c_torch_ln"],
        d["c_torch"], d["c_rep_off"], d["c_rep_ln"], d["c_rep"],
        d["c_lev_off"], d["c_lev_ln"], d["c_lev"], d["c_rblk"], d["c_up"],
        d["r_src_code"], d["r_src_pay"], d["r_side0_code"],
        d["r_side0_pay"], d["r_side1_code"], d["r_side1_pay"], d["r_delay"],
        d["k_rear_code"], d["k_rear_pay"], d["k_side0_code"],
        d["k_side0_pay"], d["k_side1_code"], d["k_side1_pay"], d["k_mode"],
        d["t_att"], d["t_dead"], buckets, qmark, pw, pb, pbs, tl, ron, con,
        tsched, rsched, ksched, flips, bout_times, bout_len, bout_max,
        d["torch_index"], varr, _np.int64(tick_cap), _np.int64(step_cap),
        _np.int64(stall_cap), _np.int64(_BOUT_N), _np.int64(_BOUT_GRACE))
    now = int(now)
    for k2 in range(ntorch):
        m = int(bout_max[k2])
        if m > 0:
            cell = d["cell"][int(d["torch_ids"][k2])]
            if m > max(_BOUT.get(cell, 0), 0):
                _BOUT[cell] = m
    if code == 1:
        raise RuntimeError(f"sim not settling on {vec} (numba core)")
    if code == 2:
        raise RuntimeError(f"sim STALLED on {vec} (numba core)")
    if code == 3:
        cell = d["cell"][int(bout_cell)]
        raise RuntimeError(f"TORCH BURNOUT at {cell} (shipping red)")
    if _expose is not None:
        _expose.clear()
        _expose.update(pw=pw, pb=pb, pbs=pbs, tl=tl, ron=ron, con=con)
    lit = _lamps_nb(d["lamp_cell"], d["l_arm_off"], d["l_arm_ln"], d["l_arm"],
                    d["l_cob_off"], d["l_cob_ln"], d["l_cob"],
                    d["l_torch_off"], d["l_torch_ln"], d["l_torch"],
                    d["l_lev_off"], d["l_lev_ln"], d["l_lev"], d["l_rblk"],
                    d["l_up"], pw, pb, tl, varr)
    lamps = {}
    for li, net in enumerate(d["lamp_net"]):
        lamps[net] = bool(lit[li])
    if _os.environ.get("REDSTONE_NB_LAMPS_ONLY", "0") == "1":
        # ponytail: sweep-only fast return. verify_par reads [0] (lamps)
        # and nothing else; the four state dicts cost ~50ms/vector of
        # comprehensions for diagnostics nobody runs in a sweep. tbl_diff
        # and every gate run with the default full tuple.
        return (lamps, {}, {}, int(now), {}, {})
    # ponytail: NO int() casts here. numpy ints index, hash and compare equal
    # to python ints (np.int64(5) == 5, same hash), and the keys are the same
    # shared cell tuples -- casting every element cost ~50ms/vector, doubling
    # the njit runtime it wraps.
    cell = d["cell"]
    return (lamps,
            {cell[j]: pw[j] for j in d["dust_ids"] if pw[j]},
            {cell[j]: 1 if tl[j] else 0 for j in d["torch_ids"]},
            now,
            {cell[j]: 1 if ron[j] else 0 for j in d["rep_ids"]},
            {cell[j]: con[j] for j in d["comp_ids"]})
