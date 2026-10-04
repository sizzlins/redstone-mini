"""RCON rig driver: banked build -> datapack -> ground-truth verdict.

Pipeline (all automatic once server+rcon+b0 exist):
  1. translate build setblocks by b0 delta, write datapack rig/ into world
  2. RCON: gamerules (chain length, quiet feedback), /reload, /function paste
  3. per vector: setblock levers (exact bids from build), sleep settle,
     query lamps via `/execute if block ... lit=true` (pass/fail parse,
     raw bodies logged -- EN-client assumption documented, never silent)
  4. score vs expected, JSON verdict, exit code.

Usage:
  python scratch/rig_verify.py <build.json> --world <dir> --b0 x,y,z
      [--host H] [--port P] [--password-file F] [--settle 4] [--dry-run]
Password NEVER on command line (file only). --dry-run prints every
command without connecting (validates generation offline).
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, r'D:\redstone-mini')
sys.path.insert(0, os.path.join(r'D:\redstone-mini', 'scratch'))
from rcon import Rcon, RconError


def parse_xyz(s):
    x, y, z = s.split(',')
    return int(x), int(y), int(z)


def main():
    a = sys.argv[1:]
    build_p = a[0]
    world = b0 = host = port = pwfile = None
    settle, dry = 4.0, False
    port = 25575
    host = '127.0.0.1'
    i = 1
    while i < len(a):
        if a[i] == '--world':
            world = a[i + 1]
            i += 2
        elif a[i] == '--b0':
            b0 = parse_xyz(a[i + 1])
            i += 2
        elif a[i] == '--host':
            host = a[i + 1]
            i += 2
        elif a[i] == '--port':
            port = int(a[i + 1])
            i += 2
        elif a[i] == '--password-file':
            pwfile = a[i + 1]
            i += 2
        elif a[i] == '--settle':
            settle = float(a[i + 1])
            i += 2
        elif a[i] == '--dry-run':
            dry = True
            i += 1
        else:
            i += 1
    if world is None or b0 is None:
        print('need --world DIR --b0 x,y,z')
        return 2
    if not dry and pwfile is None:
        print('need --password-file F (never pass secrets on cmdline)')
        return 2
    doc = json.load(open(build_p))
    dx, dy, dz = b0[0] - 0, b0[1] - 0, b0[2] - 0
    # note: export origin IS build (0,*,*): world = build + b0. oy=64 in
    # the mcfunction is the export floor offset, but pkl JSON coords are
    # build-local (y=0 floor). b0 = where build (0,0,0) lands in-world.

    def W(x, y, z):
        return (x + dx, y + dy, z + dz)

    # --- datapack (translated paste function) ---
    fn_dir = os.path.join(world, 'datapacks', 'rig', 'data', 'rig',
                           'function')
    os.makedirs(fn_dir, exist_ok=True)
    with open(os.path.join(os.path.dirname(fn_dir), '..', '..',
                           'pack.mcmeta'), 'w') as f:
        json.dump({'pack': {'pack_format': 81, 'description': 'rig'}},
                  f)
    lines = []
    for x, y, z, bid in doc['blocks']:
        wx, wy, wz = W(x, y, z)
        lines.append('setblock %d %d %d %s' % (wx, wy, wz, bid))
    fn_path = os.path.join(fn_dir, 'build.mcfunction')
    with open(fn_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('datapack: %d setblocks -> %s' % (len(lines), fn_path))

    # pin world coords (levers by bid match, lamps by bid match)
    lever_bid = {}
    for x, y, z, bid in doc['blocks']:
        if bid.startswith('minecraft:lever'):
            lever_bid['%d,%d' % (x, z)] = (x, y, z, bid)
    lamp_at = {}
    for x, y, z, bid in doc['blocks']:
        if bid.startswith('minecraft:redstone_lamp'):
            lamp_at['%d,%d' % (x, z)] = (x, y, z)
    lever_of = {}  # net -> (wx,wy,wz,off_bid,on_bid)
    for coord, name in doc['levers']:
        x, z = (int(v) for v in coord.split(','))
        bx, by, bz, bid = lever_bid[coord]
        off = bid
        on = re.sub(r'powered=false', 'powered=true', bid, count=1)
        if 'powered=' not in bid:
            raise ValueError('lever bid lacks power state: %s' % bid)
        wx, wy, wz = W(bx, by, bz)
        lever_of[name] = (wx, wy, wz, off, on)
    lamp_of = {}
    for coord, name in doc['lamps']:
        x, z = (int(v) for v in coord.split(','))
        bx, by, bz = lamp_at[coord]
        lamp_of[name] = W(bx, by, bz)

    cmds_paste = [
        'gamerule maxCommandChainLength 200000',
        'gamerule sendCommandFeedback false',
        'gamerule logAdminCommands false',
        'scoreboard objectives add __rig dummy',
        'reload',
        'function rig:build',
    ]
    seq = []  # (kind, cmd)
    for c in cmds_paste:
        seq.append(('paste', c))
    for vi, vec in enumerate(doc['vectors']):
        for name, val in vec.items():
            if name in lever_of:
                wx, wy, wz, off, on = lever_of[name]
                seq.append(('lever', 'setblock %d %d %d %s'
                            % (wx, wy, wz, on if val else off)))
        seq.append(('sleep', settle))
        for name in doc['expected'][vi]:
            wx, wy, wz = lamp_of[name]
            seq.append(('query', 'execute if block %d %d %d '
                        'minecraft:redstone_lamp[lit=true] run '
                        'scoreboard players set __r__ __rig %d'
                        % (wx, wy, wz, vi)))
    if dry:
        print('dry-run: %d paste cmds + %d steps (no connection)'
              % (len(cmds_paste), len(seq) - len(cmds_paste)))
        for kind, cmd in seq[:6]:
            print('  [%s] %s' % (kind, str(cmd)[:100]))
        print('  ... (%d more)' % (len(seq) - 6))
        # validate every lever/lamp resolved + bids well-formed
        assert len(lever_of) == len(doc['levers']), (lever_of, doc['levers'])
        assert len(lamp_of) == len(doc['lamps']), (lamp_of, doc['lamps'])
        print('dry-run OK: %d levers, %d lamps, %d vectors'
              % (len(lever_of), len(lamp_of), len(doc['vectors'])))
        return 0

    password = open(pwfile).read().strip()
    rc = Rcon(host, port, password)
    raw = []
    try:
        for kind, cmd in seq:
            if kind == 'sleep':
                time.sleep(cmd)
                continue
            try:
                out = rc.exec(cmd)
            except RconError as e:
                raw.append([kind, cmd, 'RCON-ERR: %s' % e])
                continue
            raw.append([kind, cmd, out])
    finally:
        rc.close()
    # score lamp queries: query i-th lamp of vector vi lives right after
    # its sleep marker; walk the raw log in order.
    results, fails, ri = [], 0, 0
    qi = 0
    vecs = doc['vectors']
    exp = doc['expected']
    # regroup: queries appear in seq order; slice per vector by lamp count
    queries = [r for r in raw if r[0] == 'query']
    per = len(exp[0])
    for vi in range(len(vecs)):
        got, bad = {}, []
        for li, name in enumerate(exp[vi]):
            q = queries[qi]
            qi += 1
            body = q[2] or ''
            # EN-client assumption (documented): success/failure wording.
            if re.search(r'pass', body, re.I) and \
                    not re.search(r'fail', body, re.I):
                lit = True
            elif re.search(r'fail', body, re.I):
                lit = False
            else:
                lit = None
            got[name] = lit
            want = exp[vi][name]
            if lit is None or bool(lit) != bool(want):
                bad.append(name)
        ok = not bad
        fails += (not ok)
        results.append({'vec': vecs[vi], 'got': got, 'want': exp[vi],
                        'ok': ok, 'bad': bad})
    print(json.dumps({'ok': fails == 0, 'n': len(vecs), 'fails': fails,
                      'results': results}, indent=1)[:4000])
    with open(os.path.join(os.path.dirname(build_p), 'rig_out.json'),
              'w') as f:
        json.dump({'results': results, 'raw': raw}, f)
    return 0 if fails == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
