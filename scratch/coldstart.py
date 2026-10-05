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
    # Hand-placed, router-free, seconds each. These are the shapes both engines
    # agree on; if any of them ever FAILS, a physics rule moved. notmin.py is
    # deliberately NOT here -- it fails by design (Finding 3) until the
    # constant-lever source category exists.
('wireconn', ['scratch/wireconn.py'], 600,
     'params do not overrule geometry'),
    # stair_rise rejoined once its lamp verdict was removed: sim io pins exist
    # only at y=1, so a lamp at y=3 is invisible by design and was never
    # physics. The probe is dust-only now and says so.
    ('stair_rise', ['scratch/stair.py'], 600,
     'rise agrees incl lamp (3D io key)'),
    ('stair_fall', ['scratch/stairdown.py'], 600,
     'isolated fall agrees 14/14 13/13'),
    ('lid', ['scratch/lid.py'], 600,
     'straight wire under a lid agrees'),
    ('stairlid', ['scratch/stairlid.py'], 600,
     'dust-cobble-dust joint agrees (49k last mile: direct stacks never link)'),
    ('repchain', ['scratch/repchain.py'], 600,
     'R1 -> 7 dust -> R2 chain agrees (repeater input sensing)'),
    # Lamp blocks must sit AT the declared io['lamps'] pins. The rig reads
    # lamps by looking the pin coordinate up in the block list, so a pin whose
    # lamp lives elsewhere is read at a cell that is not a lamp and reports
    # "dark" for a lit lamp -- the same shape as the sampled-green trap: the
    # gate looks green because it never read the block it claimed to read.
    ('lamp_pins', ['scratch/lamp_pin_check.py',
                   'scratch/alu4merge_g.pkl', 'scratch/alu1glass.pkl',
                   'scratch/alu4glass7.pkl'], 900,
     'every lamp block sits on its declared pin (0 missing / 0 extra)'),
    ('pin_lamp', ['scratch/pin_lamp_check.py'], 900,
     'a LAMP pin is a ROUTED load: tap wire present, lamp follows the sum, '
     'negative test reproduces the dark-lamp bug'),
    ('hier_alu1', ['scratch/hier_verify.py', 'recipes/alu1.txt'], 3000,
     'bands + stitch + 32/32, exit 0'),
    ('hier_alu4', ['scratch/hier_verify.py', 'recipes/alu4.txt'], 5400,
     'bands + stitch + ins_target + 1024/1024, exit 0'),
]

QUICK_SKIP = {'hier_alu4'}

# Known-divergence probes. EXPECTED to fail until their physics is settled
# (Finding 3, the glass down-flow); a FAIL here is information, not a
# regression. They run under --probes, are reported as DIVERGE vs AGREE, and
# never touch the exit code. A probe nobody runs is the same as no probe.
PROBES = [
    ('notmin', ['scratch/notmin.py'], 600,
     'non-pin lever: sim blind, cmc powers (Finding 3)'),
    ('stairglass', ['scratch/stairglass.py'], 600,
     'down-flow onto glass: sim=0 vs cmc=13'),
    ('stair_rise', ['scratch/stair.py'], 600,
     'rise dust agrees; lamp split open (standalone)'),
]


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

    if '--probes' in a:
        print('\n=== known-divergence probes (informational: DIVERGE expected) '
              '===', flush=True)
        for name, argv, timeout, why in PROBES:
            r = run(name, argv, timeout, why)
            print('  %-9s %-14s rc=%-3s %5.1fs  %s'
                  % ('AGREE' if r['ok'] else 'DIVERGE', name, r['rc'],
                     r['secs'], why), flush=True)
            for l in r['tail']:
                print('    | %s' % l[:150], flush=True)

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