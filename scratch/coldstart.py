"""ONE command that runs every gate, so a lying gate cannot hide.

2026-10-05. Four gates in this repo were quietly wrong on arrival, and each got
past a human because the OTHER gates were green:

  1. mkref.py froze a LOSSY baseline (cp1252 decode), so diff_engine's
     "ALL IDENTICAL" was against mangled bytes.
  2. sweep.py wrote its summary only after the loop, so a killed sweep left no
     summary at all -- 44 cached verdicts and no record of them.
  3. A resumed sweep wrote CACHED rows with no numbers, reporting "zero
     differences" for every build because it had none.
  4. hier_verify.py never called ins_target and verified the raw merge, so
     `hier_verify recipes/alu4.txt` could only ever exit 1 -- while every band
     and the merge reproduced perfectly, so it looked like a known-and-handled
     fault.

Nothing catches that class except running everything, in order, in one place.
This is that place. Each gate keeps its own internal timeout; this adds an outer
one and never lets a failure stop the rest, because "gate 3 of 7 failed" is more
useful than "the chain stopped at gate 3".

NEVER HANGS: every gate is a subprocess with a hard timeout (the outer timeout
is per-gate, generous), and a gate that times out is reported as TIMEOUT, not
skipped. A hung gate is a finding.

Usage:
    python scratch/coldstart.py                # everything
    python scratch/coldstart.py --quick        # skip the two 1024-vector gates
    python scratch/coldstart.py --sweep        # also run the dual-engine sweep
    python scratch/coldstart.py --only diff_engine,hier_alu1
"""
import os
import subprocess
import sys
import time

ROOT = r'D:\redstone-mini'
PY = sys.executable

# (name, argv, timeout_seconds, why_it_matters)
GATES = [
    ('refdrift', ['scratch/refdrift.py'], 300,
     'the frozen engine baseline is byte-faithful to HEAD'),
    ('mkref_then_drift', ['scratch/mkref.py'], 120,
     're-freeze after a sim.py/simvec.py commit (run refdrift after this too)'),
    ('diff_engine', ['scratch/diff_engine.py'], 1800,
     'ref == live == table engine, exactly, on all six outputs'),
    ('compose', ['compose.py'], 600, 'router self-test'),
    ('compose_check', ['scratch/compose_check.py'], 1200,
     '144/322/224/214 bit-identical'),
    ('nonhier_suite', ['scratch/nonhier_suite.py'], 2400,
     'flat recipes; alu1 flat RED by design'),
    ('hier_alu1', ['scratch/hier_verify.py', 'recipes/alu1.txt'], 3000,
     'bands + stitch + 32/32, exit 0'),
    ('hier_alu4', ['scratch/hier_verify.py', 'recipes/alu4.txt'], 5400,
     'bands + stitch + ins_target + 1024/1024, exit 0'),
]

QUICK_SKIP = {'hier_alu4'}


def run(name, argv, timeout, why):
    t0 = time.time()
    cmd = [PY, '-u'] + argv
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=ROOT)
        out, rc = p.stdout + p.stderr, p.returncode
        to = False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b'')
        out = out.decode('utf8', 'replace') if isinstance(out, bytes) else out
        rc, to = -9, True
    dt = time.time() - t0
    tail = [l for l in out.splitlines() if l.strip()][-3:]
    return {'name': name, 'ok': rc == 0 and not to, 'rc': rc, 'timeout': to,
            'secs': round(dt, 1), 'why': why, 'tail': tail}


def main():
    a = sys.argv[1:]
    quick = '--quick' in a
    do_sweep = '--sweep' in a
    only = None
    if '--only' in a:
        only = a[a.index('--only') + 1].split(',')

    gates = GATES
    if only:
        gates = [g for g in GATES if g[0] in only]
    elif quick:
        gates = [g for g in GATES if g[0] not in QUICK_SKIP]

    print('coldstart: %d gate(s)%s' % (len(gates),
                                       '  [quick]' if quick else ''), flush=True)
    rows = []
    for name, argv, timeout, why in gates:
        print('\n=== %s ===  %s' % (name, why), flush=True)
        r = run(name, argv, timeout, why)
        # mkref writes the freeze and CANNOT report its own failure -- that is
        # the whole lesson of the lossy-baseline bug, and my first version of
        # this gate had the misleading name mkref_then_drift while doing exactly
        # that. Re-check the freeze it just wrote.
        if name == 'mkref_then_drift' and r['ok']:
            d = run('refdrift_after_mkref', ['scratch/refdrift.py'], 300,
                    'the freeze mkref just wrote is byte-faithful')
            rows.append(d)
            print('  %-6s %-16s rc=%-3s %5.1fs  %s'
                  % ('TIMEOUT' if d['timeout'] else ('PASS' if d['ok']
                                                     else 'FAIL'),
                     'refdrift_after_mkref', d['rc'], d['secs'], d['why']),
                  flush=True)
            for l in d['tail']:
                print('    | %s' % l[:150], flush=True)
        rows.append(r)
        print('  %-6s %-16s rc=%-3s %5.1fs  %s'
              % ('TIMEOUT' if r['timeout'] else ('PASS' if r['ok'] else 'FAIL'),
                 name, r['rc'], r['secs'], why), flush=True)
        for l in r['tail']:
            print('    | %s' % l[:150], flush=True)

    if do_sweep:
        print('\n=== sweep (dual-engine, every banked build) ===', flush=True)
        rows.append(run('sweep', ['scratch/sweep.py', '--diff',
                                  '--out', 'scratch/sweep.json'],
                        7200, 'sim AND cmc per-cell over every build'))

    bad = [r for r in rows if not r['ok']]
    print('\n' + '=' * 70)
    print('coldstart: %d/%d gates green' % (len(rows) - len(bad), len(rows)))
    for r in bad:
        print('  %-8s %-16s rc=%s %ss  %s'
              % ('TIMEOUT' if r['timeout'] else 'FAIL', r['name'], r['rc'],
                 r['secs'], r['why']))
    if not bad:
        print('  every gate ran and agreed')
    print('=' * 70)
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())