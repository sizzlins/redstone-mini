"""Evolutionary netlist superoptimizer: reads a recipe, finds a smaller build.

Genome = gate list (out/op/args/band). Operators are function-preserving
by construction (buffer/dedup/dead/rebind/unshare) or gated by exhaustive
recipe_equiv (cheap, no placement). Fitness: equiv (ms) -> compose +
sim_verify (seconds, the real cost) -> minimize blocks. Bounded evals,
deterministic seed. Only verified individuals reproduce.

Speed (measured rationale, not hope): mutants derive from best by one
gate, so the rung best won almost always routes them too. Each eval
therefore tries best's rung pinned first (REDSTONE_FORCE rung 1,
seconds) and only climbs the full ladder on failure -- instead of
paying a full ladder per mutant. Memo is engine-fingerprinted (a
physics/router change voids stale fitness, which once would have
promoted a pre-lock pass under locking sim).

Usage: python scratch/evolve.py <recipe.txt> <workdir> <evals> [seed]
Writes best.txt + log.txt into workdir.
"""
import copy
import functools
import itertools
import os
import random
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
from recipe import eval_net, parse_recipe

OPS = ('NOT', 'AND', 'OR', 'XOR')


def topo(gates, inputs):
    """Topological order (eval_net needs defs before uses). Stable."""
    done, out, rest = set(inputs), [], list(gates)
    while rest:
        for i, g in enumerate(rest):
            if all(a in done or a in inputs for a in g['args']):
                done.add(g['out'])
                out.append(g)
                del rest[i]
                break
        else:
            raise ValueError('cycle in %s' % [g['out'] for g in rest])
    return out


def render(recipe):
    out = ['IN ' + ', '.join(recipe['inputs']),
           'OUT ' + ', '.join(recipe['outputs'])]
    band = None
    for g in recipe['gates']:
        gb = g.get('band', 0)
        if gb != band:
            band = gb
            out.append('BAND %d' % band)
        op = g['op']
        if op == 'NOT':
            out.append('%s = NOT %s' % (g['out'], g['args'][0]))
        else:
            out.append('%s = %s %s %s' % (g['out'], g['args'][0], op, g['args'][1]))
    return '\n'.join(out) + '\n'


def loads_of(gates):
    uses = {}
    for g in gates:
        for a in g['args']:
            uses.setdefault(a, []).append(g['out'])
    return uses


def kills(gates, out):
    return [g for g in gates if g['out'] != out]


def op_buffer(rng, r):
    """Double-NOT on a shared wire, move half its loads over."""
    g = copy.deepcopy(r)
    uses = loads_of(g['gates'])
    cands = [w for w, u in uses.items()
             if len(u) >= 2 and w not in r['inputs']]
    if not cands:
        return None
    w = rng.choice(cands)
    n1, n2 = w + '_eb', w + '_eb2'
    if any(x['out'] in (n1, n2) for x in g['gates']):
        return None
    idx = next(i for i, x in enumerate(g['gates']) if x['out'] == uses[w][0])
    g['gates'].insert(idx, {'out': n1, 'op': 'NOT', 'args': [w],
                            'band': g['gates'][idx]['band']})
    g['gates'].insert(idx + 1, {'out': n2, 'op': 'NOT', 'args': [n1],
                                'band': g['gates'][idx]['band']})
    for u in uses[w][::2]:
        for x in g['gates']:
            if x['out'] == u:
                x['args'] = [n2 if a == w else a for a in x['args']]
    return g


def op_dedup(rng, r):
    """Merge two gates computing the same thing."""
    g = copy.deepcopy(r)
    seen = {}
    for x in g['gates']:
        key = (x['op'], tuple(x['args']))
        if key in seen and x['out'] not in r['outputs']:
            old = seen[key]
            for y in g['gates']:
                y['args'] = [old if a == x['out'] else a for a in y['args']]
            g['gates'] = kills(g['gates'], x['out'])
            return g
        seen.setdefault(key, x['out'])
    return None


def op_dead(rng, r):
    """Delete a gate with no path to any output."""
    g = copy.deepcopy(r)
    uses = loads_of(g['gates'])
    outs = set(r['outputs'])
    cands = [x['out'] for x in g['gates']
             if x['out'] not in outs and not uses.get(x['out'])]
    if not cands:
        return None
    g['gates'] = kills(g['gates'], rng.choice(cands))
    return g


def op_rebind(rng, r):
    """Move a gate to a neighbouring band."""
    g = copy.deepcopy(r)
    bands = sorted({x['band'] for x in g['gates']})
    if len(bands) < 2:
        return None
    x = rng.choice([t for t in g['gates'] if t['out'] not in r['outputs']])
    opts = [b for b in bands if b != x['band']]
    x['band'] = rng.choice(opts)
    g['gates'].sort(key=lambda t: t['band'])
    return g


def op_unshare(rng, r):
    """Duplicate a 2+-load gate so each band keeps its own copy."""
    g = copy.deepcopy(r)
    uses = loads_of(g['gates'])
    cands = [x for x in g['gates'] if len(uses.get(x['out'], [])) >= 2
             and x['out'] not in r['inputs'] + r['outputs']]
    if not cands:
        return None
    x = rng.choice(cands)
    lanes = {}
    for u in uses[x['out']]:
        t = next(t for t in g['gates'] if t['out'] == u)
        lanes.setdefault(t['band'], []).append(u)
    if len(lanes) < 2:
        return None
    keep, rest = sorted(lanes)[0], sorted(lanes)[1:]
    for i, b in enumerate(rest):
        nn = '%s_uc%d' % (x['out'], i)
        g['gates'].append({'out': nn, 'op': x['op'], 'args': list(x['args']),
                           'band': b})
        for u in lanes[b]:
            t = next(t for t in g['gates'] if t['out'] == u)
            t['args'] = [nn if a == x['out'] else a for a in t['args']]
    g['gates'].sort(key=lambda t: t['band'])
    return g


def op_factor(rng, r):
    """(A AND B) OR (A AND C) -> A AND (B OR C). Distributive, exact."""
    g = copy.deepcopy(r)
    by_out = {x['out']: x for x in g['gates']}
    ors = [x for x in g['gates'] if x['op'] == 'OR' and len(x['args']) == 2]
    rng.shuffle(ors)
    for o in ors:
        u, v = (by_out.get(a) for a in o['args'])
        if u is None or v is None or u['op'] != 'AND' or v['op'] != 'AND':
            continue
        shared = sorted(set(u['args']) & set(v['args']))
        if not shared:
            continue
        a = rng.choice(shared)
        bu = [x for x in u['args'] if x != a]
        bv = [x for x in v['args'] if x != a]
        if not bu or not bv:
            continue
        w = '%s_for%d' % (o['out'], rng.randrange(1 << 30))
        if len(bu) == 1 and len(bv) == 1:
            wgate = {'out': w, 'op': 'OR', 'args': [bu[0], bv[0]],
                     'band': o['band']}
        else:
            continue
        g['gates'].append(wgate)
        o['op'] = 'AND'
        o['args'] = [a, w]
        return g
    return None


def _drop(g, out):
    """Delete gate `out` and point every load of it at nothing (dead sweep)."""
    g['gates'] = [x for x in g['gates'] if x['out'] != out]


def _alias(g, out, w):
    """Retarget every load of `out` to `w`, then delete the gate."""
    for x in g['gates']:
        x['args'] = [w if a == out else a for a in x['args']]
    _drop(g, out)


def op_simplify(rng, r):
    """Rewrite away the exact waste the search actually piles up, to fixpoint.

    Three rules, all function-preserving on 2-state logic:
      X AND X / X OR X -> X   (a self-gate is a buffer; expand_gates already
                               turns AND(x,x) into one, so the gate is pure
                               bookkeeping)
      NOT NOT X -> X          (only where the inner NOT feeds nothing else,
                               so no phase/pole is stolen from another load)
      dead sweep              (no loads, not an output; repeat, because
                               deleting one gate can strand the next)

    Output gates are never deleted -- nothing would produce them -- which is
    exactly why the fat hides: evo_add2's best ended at
    `S0 = x0_eb2 AND x0_eb2` over `x0 = A0 XOR B0`, and the fold below eats
    the two inverters underneath it, then the sweep eats the dead1/dead2/
    dead3 chain, while S0 itself legally stays one buffer.
    """
    g = copy.deepcopy(r)
    outs = set(r['outputs'])
    n0 = len(g['gates'])
    while True:
        uses = loads_of(g['gates'])
        by_out = {x['out']: x for x in g['gates']}
        hit = None
        for x in g['gates']:
            if (x['op'] in ('AND', 'OR') and x['args'][0] == x['args'][1]
                    and x['out'] not in outs):
                hit = ('self', x['out'], x['args'][0])
                break
        if hit is None:
            for x in g['gates']:
                if x['op'] != 'NOT':
                    continue
                a = by_out.get(x['args'][0])
                if (a is not None and a['op'] == 'NOT'
                        and set(uses.get(a['out'], ())) == {x['out']}):
                    hit = ('fold', x['out'], a['out'], a['args'][0])
                    break
        if hit is None:
            dead = [x['out'] for x in g['gates']
                    if x['out'] not in outs and not uses.get(x['out'])]
            if not dead:
                break
            _drop(g, dead[0])
            continue
        if hit[0] == 'self':
            _alias(g, hit[1], hit[2])
        else:
            _, outer, inner, wire = hit
            _alias(g, outer, wire)   # fold both inverters into the wire
            _drop(g, inner)
    return g if len(g['gates']) < n0 else None


MUTS = [op_buffer, op_dedup, op_dead, op_rebind, op_unshare, op_factor,
        op_simplify]


def equivalent(a, b):
    if a['inputs'] != b['inputs'] or a['outputs'] != b['outputs']:
        return False
    for vals in itertools.product([0, 1], repeat=len(a['inputs'])):
        env = dict(zip(a['inputs'], vals))
        ga, gb = eval_net(a, env), eval_net(b, env)
        if any(bool(ga[o]) != bool(gb[o]) for o in a['outputs']):
            return False
    return True


@functools.lru_cache(maxsize=None)
def _input_cols(n):
    """Bit k of column i = value of input i in vector k (cached per width)."""
    out = []
    for i in range(n):
        ones = (1 << (1 << i)) - 1
        step, period = 1 << i, 1 << (i + 1)
        c = 0
        for base in range(0, 1 << n, period):
            c |= ones << (base + step)
        out.append(c)
    return tuple(out)


def _eval_cols(gates, sig, mask):
    """One topo pass over whole-space bit columns. Combinational only."""
    for g in gates:
        v = []
        for x in g['args']:
            v.append(0 if x == '0' else mask if x == '1' else sig[x])
        op = g['op']
        if op == 'AND':
            sig[g['out']] = v[0] & v[1]
        elif op == 'OR':
            sig[g['out']] = v[0] | v[1]
        elif op == 'XOR':
            sig[g['out']] = v[0] ^ v[1]
        elif op == 'NOT':
            sig[g['out']] = ~v[0] & mask
        else:
            raise ValueError('non-combinational %s' % op)
    return sig


def _vec_equiv(a, b):
    """Bit-parallel equivalent(): whole input space in O(gates) big-int
    ops instead of O(2^n) env-dict evals. Exact: anything stateful or
    cyclic falls back to equivalent() (same verdicts, same exceptions),
    and evo only ever breeds NOT/AND/OR/XOR, so the fast path always
    fires where it matters. Space drops from 2^n env dicts to O(gates)
    ints."""
    if a['inputs'] != b['inputs'] or a['outputs'] != b['outputs']:
        return False
    if any(g['op'] == 'LATCH' for g in a['gates'] + b['gates']):
        return equivalent(a, b)
    try:
        ta = topo(a['gates'], a['inputs'])
        tb = topo(b['gates'], b['inputs'])
    except ValueError:
        return equivalent(a, b)
    n = len(a['inputs'])
    mask = (1 << (1 << n)) - 1
    cols = _input_cols(n)
    try:
        sa = _eval_cols(ta, dict(zip(a['inputs'], cols)), mask)
        sb = _eval_cols(tb, dict(zip(b['inputs'], cols)), mask)
    except (ValueError, KeyError):
        return equivalent(a, b)
    return all(sa[o] == sb[o] for o in a['outputs'])


def _ticks_on():
    """Opt-in speed fitness: REDSTONE_EVO_TICKS=1 adds worst-case sim ticks
    (cmc-confirmed model: dust instant, every repeater/gate 1 tick) as the
    tiebreak inside fitness: (blocks, ticks) lexicographic. Default OFF so
    existing runs, memos and logs are byte-identical."""
    return os.environ.get("REDSTONE_EVO_TICKS", "") == "1"


def _worst_ticks(cand, blocks, io):
    """Worst sim settle ticks over a bounded spread (full space at n<=8,
    else 16 vectors, stated in the log line). Separate module so the
    timing model has one home (see scratch/ticks.py)."""
    import sys as _sys
    _sys.path.insert(0, os.path.join(r'D:\redstone-mini', 'scratch'))
    import ticks
    vecs = None
    if len(cand["inputs"]) > 8:
        vecs = ticks.spread_vectors(cand["inputs"], 16)
    worst, _, n, _ = ticks.worst_ticks(blocks, io, cand["inputs"], vecs)
    return worst


def fitness(cand, base_inputs, workdir, tag, budget):
    """(verifies, blocks) normally, (verifies, (blocks, ticks)) with the
    ticks flag. Compose+sim cost lives here. Serial version."""
    from compose import compose
    from sim import sim_verify
    t0 = time.monotonic()
    try:
        blocks, size, io = compose(cand)
    except Exception as e:
        return False, None, 'compose: %s' % str(e)[:80]
    if time.monotonic() - t0 > budget:
        return False, None, 'compose-budget'
    try:
        sim_verify(cand, blocks, io, quiet=True)
    except Exception as e:
        return False, None, 'sim: %s' % str(e)[:80]
    if _ticks_on():
        try:
            return True, (len(blocks), _worst_ticks(cand, blocks, io)), 'ok'
        except Exception as e:
            return False, None, 'ticks: %s' % str(e)[:80]
    return True, len(blocks), 'ok'


def _low_prio():
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except Exception:
        pass


def _eval_worker(conn, text, compose_secs):
    _low_prio()
    import os as _os
    _os.environ['REDSTONE_COMPOSE_SECS'] = str(compose_secs)
    try:
        from recipe import parse_recipe
        from compose import compose
        from sim import sim_verify
        cand = parse_recipe(text)
        # ponytail: pinned rung first. Mutants are one gate from best,
        # so best's rung (rung 1 for every green ever: short spread 1
        # gates-first) routes them in seconds; the full ladder runs
        # only on failure. Way is recorded ('pinned' vs 'full') so the
        # win rate is measured, not assumed.
        how = 'full'
        try:
            _os.environ['REDSTONE_FORCE'] = '1,gates_first,short'
            blocks, size, io = compose(cand)
            how = 'pinned'
        except BaseException:
            _os.environ.pop('REDSTONE_FORCE', None)
            blocks, size, io = compose(cand)
        finally:
            _os.environ.pop('REDSTONE_FORCE', None)
        sim_verify(cand, blocks, io, quiet=True)
        n = len(blocks)
        if _ticks_on():
            sys.path.insert(0, os.path.join(r'D:\redstone-mini', 'scratch'))
            import ticks
            vecs = None
            if len(cand["inputs"]) > 8:
                vecs = ticks.spread_vectors(cand["inputs"], 16)
            w, _, _, _ = ticks.worst_ticks(blocks, io, cand["inputs"], vecs)
            n = (n, w)
        conn.send(('ok', n, how))
    except BaseException as e:
        conn.send(('err', '%s: %s' % (type(e).__name__, str(e)[:100])))
    finally:
        conn.close()


def fitness_par(cands, compose_secs=180, workers=4):
    """Evaluate rendered candidates in parallel direct children.
    Returns {render_text: (ok, blocks, msg)}. Hang-safe: hard deadline
    per child, kill on overrun (same pattern as hier_bands._run_all).
    """
    import multiprocessing as mp
    pending = list(enumerate(cands))
    live = []
    out = {}
    dl = compose_secs + 120
    while pending or live:
        while pending and len(live) < workers:
            idx, text = pending.pop(0)
            parent, child = mp.Pipe(duplex=False)
            p = mp.Process(target=_eval_worker,
                           args=(child, text, compose_secs), daemon=False)
            p.start()
            child.close()
            live.append([p, parent, time.monotonic() + dl, idx])
        time.sleep(0.5)
        still = []
        for p, parent, deadline, idx in live:
            done, res = False, (False, None, 'no result')
            if parent.poll(0):
                try:
                    got = parent.recv()
                except EOFError:
                    got = None
                if got is not None and got[0] == 'ok':
                    res = (True, got[1], got[2])
                elif got is not None:
                    res = (False, None, got[1])
                done = True
            elif time.monotonic() > deadline:
                res = (False, None, 'timeout')
                done = True
            if done:
                out[cands[idx]] = res
                p.join(1)
                if p.is_alive():
                    p.terminate()
                    p.join(3)
                    if p.is_alive():
                        p.kill()
                        p.join(3)
                parent.close()
            else:
                still.append([p, parent, deadline, idx])
        live = still
    return out


def engine_fp():
    """Content hash of physics+router+recipe (memo invalidation domain).

    A sim/router change can flip any cached verdict (measured: lock
    semantics landed mid-run and every pre-lock 'ok' went suspect), so
    fitness entries are only trusted under the engine that measured
    them. Called at load and save; cheap (six small files).
    """
    import hashlib
    h = hashlib.sha256()
    for f in ('sim.py', 'simvec.py', 'compose.py', 'recipe.py',
              'tiles.py', 'layout.py'):
        p = os.path.join(r'D:\redstone-mini', f)
        if os.path.exists(p):
            h.update(open(p, 'rb').read())
    return h.hexdigest()[:16]


def memo_load(workdir):
    import hashlib
    import json
    p = os.path.join(workdir, 'memo.json')
    if os.path.exists(p):
        try:
            m = json.load(open(p))
            if isinstance(m, dict) and m.get('__engine__') == engine_fp():
                return m
        except Exception:
            pass
    # ponytail: stale or foreign memo is dropped whole, not merged: a
    # pre-change 'ok' promoting an unverified mutant is exactly how a
    # wrong build ships. '__engine__' cannot collide with sha keys.
    return {'__engine__': engine_fp()}


def memo_save(workdir, memo):
    import json
    try:
        memo['__engine__'] = engine_fp()
        with open(os.path.join(workdir, 'memo.json'), 'w') as f:
            json.dump(memo, f)
    except Exception:
        pass


def mkey(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _selftest():
    """One runnable check on the only nontrivial new logic: op_simplify must
    shrink known fat AND keep the truth table. An alias bug shows up here as a
    wrong output, not 40 evals later as a mystery red build.
    """
    _r = parse_recipe(
        "IN a, b\nOUT y\n"
        "x = a XOR b\n"          # S0's real source
        "xe = NOT x\n"
        "xe2 = NOT xe\n"
        "y = xe2 AND xe2\n"     # the evo_add2 fat: buffer of a buffer
        "d1 = a AND b\n"
        "d2 = d1 OR a\n"         # dead chain
        "d3 = d2 XOR a\n")
    _g = op_simplify(None, _r)
    assert _g is not None, "selftest: simplifier found nothing"
    _kept = {x['out'] for x in _g['gates']}
    assert _r['outputs'][0] in _kept, "selftest: deleted an output gate"
    assert not (set(('xe', 'xe2', 'd1', 'd2', 'd3')) & _kept), \
        "selftest: fold/sweep left fat behind: %s" % sorted(_kept)
    for _vals in itertools.product([0, 1], repeat=len(_r['inputs'])):
        _env = dict(zip(_r['inputs'], _vals))
        _a, _b = eval_net(_r, _env), eval_net(_g, _env)
        assert all(bool(_a[o]) == bool(_b[o]) for o in _r['outputs']), \
            "selftest: changed function at %s" % (_env,)
    assert op_simplify(None, _g) is None, "selftest: not idempotent"


def main():
    _selftest()
    src, workdir, nevals = sys.argv[1], sys.argv[2], int(sys.argv[3])
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
    rng = random.Random(seed)
    os.makedirs(workdir, exist_ok=True)
    base = parse_recipe(open(src).read())
    for g in base['gates']:
        g.setdefault('band', 0)
    log = open(os.path.join(workdir, 'log.txt'), 'a')
    # baseline fitness (one paid evaluation)
    ok0, b0, msg0 = fitness(base, base['inputs'], workdir, 'base', 600)
    log.write('base verifies=%s blocks=%s %s\n' % (ok0, b0, msg0))
    log.flush()
    if not ok0:
        print('BASE DOES NOT VERIFY:', msg0)
        return
    best, bestn = base, b0
    # ponytail: resume from best.txt (a dead run's progress survives).
    # Read BEFORE overwriting below; verified before trusting (a stale
    # file must never seed the climb).
    try:
        with open(os.path.join(workdir, 'best.txt')) as f:
            prior = parse_recipe(f.read())
    except Exception:
        prior = None
    if prior is not None and equivalent(base, prior):
        okp, bp, _msgp = fitness(prior, base['inputs'], workdir,
                                 'resume', 600)
        if okp and bp is not None and bp < bestn:
            best, bestn = prior, bp
            print('resumed best=%s' % (bp,), flush=True)
            log.write('resumed best=%s\n' % (bp,))
            log.flush()
    with open(os.path.join(workdir, 'best.txt'), 'w') as f:
        f.write(render(best))
    memo = memo_load(workdir)
    PERGEN, WORKERS = 8, 4
    t_end = time.monotonic() + 3600
    done_evals = 0
    for i in range(nevals):
        if time.monotonic() > t_end or done_evals >= nevals:
            break
        # generate a batch (cheap: mutate + topo + equiv, all in-process)
        batch, seen = [], set()
        while len(batch) < PERGEN:
            mut = rng.choice(MUTS)
            cand = mut(rng, copy.deepcopy(best))
            if cand is None:
                continue
            try:
                cand['gates'] = topo(cand['gates'], cand['inputs'])
            except ValueError:
                continue
            if not equivalent(base, cand):
                continue
            t = render(cand)
            k = mkey(t)
            if k in memo or t in seen:
                continue
            seen.add(t)
            batch.append((mut.__name__, t, k))
        # evaluate the batch in parallel (the expensive part)
        res = fitness_par([t for _, t, _ in batch])
        for (mname, t, k), (ok, n, msg) in zip(
                batch, [res.get(tt, (False, None, 'lost')) for _, tt, _ in batch]):
            memo[k] = [ok, n, msg]
            done_evals += 1
            log.write('eval %d %s verifies=%s blocks=%s %s\n'
                      % (done_evals, mname, ok, n, msg))
            if ok and n < bestn:
                bestn = n
                best = parse_recipe(t)
                for g in best['gates']:
                    g.setdefault('band', 0)
                with open(os.path.join(workdir, 'best.txt'), 'w') as f:
                    f.write(render(best))
                print('eval %d NEW BEST %s (%s)' % (done_evals, n, mname),
                      flush=True)
        log.flush()
        memo_save(workdir, memo)
    memo_save(workdir, memo)
    print('done best=%s evals=%d' % (bestn, done_evals))


if __name__ == '__main__':
    main()
