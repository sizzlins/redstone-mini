"""Minimal reproducer for the one cross-engine divergence found in add2opt:

  a powered dust wire has a neighbour dust that mutually points at it, and
  that neighbour sits directly against a COMPARATOR's side.
  cmc gives the neighbour 14 (vanilla: a dust pointing at a powered dust
  gives it power-1, regardless of what else is adjacent).
  our sim gives it 0.

Both engines are run here on the same 6-cell build so the claim is
checkable in one command. Extends the motif with mode=compare and with the
comparator removed, to separate "comparator adjacency" from "subtract mode".

Usage: motif.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r'D:\redstone-mini')

W = 'minecraft:redstone_wire[east=side,west=side,south=none,north=none,power=0]'
FLOOR = 'minecraft:stone'


def build(cells, z0=0):
    """cells: list of (x, bid) placed at y=1; floor stone under each."""
    blocks = []
    for x, bid in cells:
        blocks.append([x, 0, z0, FLOOR])
        blocks.append([x, 1, z0, bid])
    return blocks


def variants():
    """name -> blocks. Every variant has the same powered-dust pair; only
    what sits east of the second dust changes."""
    base = [(0, 'minecraft:redstone_block'), (1, W), (2, W)]
    v = {}
    v['no_comparator'] = build(base)
    v['comparator_subtract'] = build(
        base + [(3, 'minecraft:comparator[facing=east,mode=subtract]')])
    v['comparator_compare'] = build(
        base + [(3, 'minecraft:comparator[facing=east,mode=compare]')])
    # same again on a second deck, to prove it is not a z/layer artifact
    v['subtract_deck2'] = build(
        base + [(3, 'minecraft:comparator[facing=east,mode=subtract]')], z0=4)
    return v


def sim_power(doc):
    from sim import _parse_build, _run_vec
    io = {'levers': {}, 'lamps': {}}
    P = _parse_build([tuple(b) for b in doc['blocks']], io)
    out = {}
    for i, vec in enumerate(doc['vectors']):
        _g, live, _t, _n, _r, _c = _run_vec(vec, None, P)
        out[i] = {'%d,%d,%d' % c: int(p) for c, p in live.items()}
    return out


def cmc_power(doc, tag):
    p = os.path.join(HERE, '_motif_%s.json' % tag)
    d = os.path.join(HERE, '_motif_%s.doc.json' % tag)
    json.dump(doc, open(d, 'w'))
    cells = p + '.cells'
    cmd = ['node', os.path.join(HERE, 'cmc_harness.mjs'), d,
           '--ticks', '200', '--dump-cells', cells, '--dump-vec', '0',
           '--vectors', '0']
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                       cwd=r'D:\redstone-mini')
    blob = r.stdout
    j = blob[blob.find('{'):blob.rfind('}') + 1] if '{' in blob else '{}'
    try:
        res = json.loads(j)
    except ValueError:
        res = {'raw': blob[-200:], 'stderr': r.stderr[-200:]}
    cm = {}
    if os.path.exists(cells):
        cm = json.load(open(cells)).get('cells') or {}
    return res, cm


def main():
    print('motif: powered dust (1,1,z) -> dust (2,1,z) -> comparator east')
    print('probing the SECOND dust (2,1,z); vanilla says 14\n')
    rows = []
    for name, blocks in variants().items():
        z0 = 4 if name.endswith('deck2') else 0
        doc = {'blocks': blocks, 'levers': [], 'lamps': [],
               'vectors': [{}], 'expected': [{}], 'sampled': False,
               'n_inputs': 0}
        sp = sim_power(doc)
        res, cp = cmc_power(doc, name)
        key = '2,1,%d' % z0
        key1 = '1,1,%d' % z0
        rows.append((name, sp[0].get(key1), sp[0].get(key),
                     cp.get(key1), cp.get(key)))
    print('%-22s %-14s %-14s %s' % ('variant', 'sim (src, tgt)', 'cmc (src, tgt)',
                                    'AGREE'))
    bad = 0
    for name, s1, s2, c1, c2 in rows:
        agree = (s2 or 0) == (c2 or 0)
        bad += (not agree)
        print('%-22s %-14s %-14s %s' % (
            name, '%s,%s' % (s1 or 0, s2 or 0), '%s,%s' % (c1 or 0, c2 or 0),
            'yes' if agree else 'NO  <-- DIVERGENCE'))
    print('\n%d/%d variants diverge' % (bad, len(rows)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
