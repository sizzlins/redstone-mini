"""RCON rig driver: banked build -> datapack -> ground-truth verdict.

Pipeline (all automatic once server+rcon+b0 exist):
  1. translate build setblocks by b0 delta, write datapack rig/ into world
  2. RCON: gamerules (chain length, quiet feedback), /reload, /function paste
  3. per vector: setblock levers (exact bids from build), sleep settle,
     query lamps via `execute store success` + `scoreboard players get`
     (the only RCON-visible read channel), score vs expected, JSON verdict.

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
        # ponytail: 26.x renamed gamerules (snake_case, namespaced;
        # max_command_chain_length is now max_command_sequence_length).
        # Discovered live: old names fail with "Incorrect argument".
        'gamerule minecraft:max_command_sequence_length 200000',
        # ponytail: feedback MUST stay true (2026-10-04: with
        # send_command_feedback false, even direct commands like
        # `scoreboard players get` return empty bodies via RCON --
        # every read goes blind. Log spam is already off above).
        'gamerule minecraft:send_command_feedback true',
        'gamerule minecraft:log_admin_commands false',
    ]
    cmds_paste.append('scoreboard objectives add __rig dummy')
    # forceload the build bbox first (setblocks in unloaded chunks fail
    # with "position is not loaded" -- measured on first live run).
    # forceload takes WORLD-block coords (verified live: block rect maps
    # to chunk coverage). NOTE: "No chunks were marked" does NOT mean
    # failure -- it also fires when chunks are ALREADY marked. Trust only
    # `forceload query` below, gated in the paste check.
    _wxs = [x + dx for x, y, z, b in doc['blocks']]
    _wzs = [z + dz for x, y, z, b in doc['blocks']]
    cmds_paste.append('forceload add %d %d %d %d'
                      % (min(_wxs) - 16, min(_wzs) - 16,
                         max(_wxs) + 16, max(_wzs) + 16))
    _probes = [(min(_wxs), min(_wzs)),
               ((min(_wxs) + max(_wxs)) // 2,
                (min(_wzs) + max(_wzs)) // 2),
               (max(_wxs), max(_wzs))]
    for _qx, _qz in _probes:
        cmds_paste.append('forceload query %d %d' % (_qx, _qz))
    cmds_paste += [
        'reload',
        'function rig:build',
    ]
    # paste-verify (fail fast): two floor cells must exist post-paste.
    # (2026-10-04: ran 16 vectors against an unpasted world because the
    # paste failure was silent. Never again: no floor, no vectors.)
    _miny = min(y for x, y, z, b in doc['blocks'])
    _fb = [(x, y, z, b) for x, y, z, b in doc['blocks']
           if y == _miny][:2]
    for i, (x, y, z, bid) in enumerate(_fb):
        wx, wy, wz = W(x, y, z)
        base = bid.split('[')[0]
        tag = 'FL%d' % i
        cmds_paste.append('execute store success score %s __rig '
                          'if block %d %d %d %s'
                          % (tag, wx, wy, wz, base))
        cmds_paste.append('scoreboard players get %s __rig' % tag)
    seq = []  # (kind, cmd)
    for c in cmds_paste:
        seq.append(('paste', c))
    for vi, vec in enumerate(doc['vectors']):
        for name, val in vec.items():
            if name in lever_of:
                wx, wy, wz, off, on = lever_of[name]
                seq.append(('lever', 'setblock %d %d %d %s'
                            % (wx, wy, wz, on if val else off)))
        seq.append(('sleep', (settle, vi, sorted(doc['expected'][vi]))))
        for name in doc['expected'][vi]:
            wx, wy, wz = lamp_of[name]
            # ponytail: `say` and nested `execute ... run <cmd>` return
            # NOTHING via RCON (broadcast/nested outputs are swallowed),
            # so lamp state rides `execute store success` (writes 1/0 to
            # scoreboard silently) + `scoreboard players get` (DIRECT
            # command with visible `'<P> has N [__rig]'` output).
            # Calibrated live 2026-10-04 (26.x): match -> 'Test passed'/1,
            # mismatch -> 'Test failed'/0.
            tag = 'L%d%s' % (vi, name)
            seq.append(('query', 'execute store success score %s __rig '
                        'if block %d %d %d '
                        'minecraft:redstone_lamp[lit=true]'
                        % (tag, wx, wy, wz)))
            seq.append(('query', 'scoreboard players get %s __rig' % tag))
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

    def connect():
        # ponytail: generous timeout (measured 2026-10-04: forceload
        # generating ~150 fresh chunks wedges RCON past 10s; the client
        # timed out mid-read, then everything cascaded. Quick commands
        # still return after 150ms quiet; only the truly-stuck wait).
        return Rcon(host, port, password, timeout=120)

    rc = connect()
    raw = []

    def run(cmd):
        # ponytail: reconnect-resilient exec (measured 2026-10-04: the
        # server drops the RCON client across /reload + bulk /function --
        # 2s freeze, connection reset. Retry once on a FRESH connection;
        # fail loud only if that dies too).
        nonlocal rc
        try:
            return rc.exec(cmd)
        except Exception as e1:
            print('  [reconnect after: %s]' % str(e1)[:80], flush=True)
            try:
                rc.close()
            except Exception:
                pass
            rc = connect()
            return rc.exec(cmd)

    # split paste phase (must verify) from vector phase (must not run
    # on an unpasted world). Paste cmds are contiguous at seq head; the
    # gate fires on the LAST paste index (robust to reconnect-probe
    # entries appended to raw mid-phase).
    _last_paste = max(i for i, (k, _) in enumerate(seq) if k == 'paste')

    try:
        for _i, (kind, cmd) in enumerate(seq):
            if kind == 'sleep':
                # ponytail: poll-to-stable, not fixed sleep (2026-10-04:
                # fixed 6s reads under laggy TPS caught mid-transients --
                # early vectors failed, late passed. Quiescence = two
                # consecutive identical full-lamp reads; timeout loud).
                _floor, _vi, _names = cmd
                time.sleep(min(_floor, 3.0))
                _prev, _stable, _t0 = None, False, time.time()
                while time.time() - _t0 < 120:
                    _cur = []
                    for _nm in _names:
                        _wx, _wy, _wz = lamp_of[_nm]
                        try:
                            run('execute store success score PL __rig '
                                'if block %d %d %d '
                                'minecraft:redstone_lamp[lit=true]'
                                % (_wx, _wy, _wz))
                            _o = run('scoreboard players get PL __rig')
                        except Exception as e:
                            _cur = None
                            break
                        _m = re.search(r'has (\d+)', _o or '')
                        _cur.append(None if not _m else int(_m.group(1)))
                    if _cur is not None and _cur == _prev and \
                            all(v is not None for v in _cur):
                        _stable = True
                        break
                    _prev = _cur
                    time.sleep(2)
                raw.append(['sleep', 'vec%d stable=%s in %.0fs'
                            % (_vi, _stable, time.time() - _t0), ''])
                print('  [settle vec%d stable=%s %.0fs]'
                      % (_vi, _stable, time.time() - _t0), flush=True)
                if not _stable:
                    print('ABORT: vec%d never settled (120s); failing loud'
                          % _vi, flush=True)
                    print(json.dumps({'ok': False, 'stage': 'settle',
                                      'vec': _vi}))
                    return 3
                continue
            print('> [%s] %s' % (kind, str(cmd)[:90]), flush=True)
            try:
                out = run(cmd)
            except Exception as e:
                raw.append([kind, cmd, 'RCON-ERR: %s' % e])
                continue
            raw.append([kind, cmd, out])
            print('  <- %s' % (out[:160].replace('\n', ' | ') if out
                               else '(empty)'), flush=True)
            if cmd == 'reload':
                # ponytail: post-reload RCON goes mute (measured: every
                # command after /reload returned empty until the reload
                # finished server-side). Settle, then gate on `seed`
                # (known-visible) before any command that matters.
                time.sleep(15)
                _ready = False
                for _t in range(12):
                    try:
                        _po = run('seed')
                    except Exception as e:
                        raw.append(['paste', 'seed-probe',
                                    'RCON-ERR: %s' % e])
                        time.sleep(5)
                        continue
                    raw.append(['paste', 'seed-probe', _po])
                    if _po and 'Seed:' in _po:
                        _ready = True
                        break
                    time.sleep(5)
                if not _ready:
                    print('ABORT: server never settled post-reload '
                          '(12 seed probes, no Seed:); vectors skipped)',
                          flush=True)
                    print(json.dumps({'ok': False, 'stage': 'reload'}))
                    return 3
                print('reload settled (seed probe ok)', flush=True)
            if _i == _last_paste:
                _fl = [(r[1], r[2] or '') for r in raw
                       if r[0] == 'paste'
                       and 'scoreboard players get FL' in r[1]]
                _missing = [c for c, b in _fl
                            if not re.search(r'has 1\b', b)]
                _fq = [(r[1], r[2] or '') for r in raw
                       if r[0] == 'paste' and
                       r[1].startswith('forceload query')]
                _unmarked = [c for c, b in _fq
                             if 'is marked for force' not in (b or '')]
                _missing += _unmarked
                if _missing:
                    print('ABORT: paste unverified, missing %s '
                          '(world unpasted or wrong b0; vectors skipped)'
                          % _missing, flush=True)
                    print(json.dumps({'ok': False, 'stage': 'paste',
                                      'missing': _missing}))
                    return 3
                print('paste verified (%d floor markers)' % len(_fl),
                      flush=True)
    finally:
        rc.close()
    # score: store+get pair per lamp; parse the number from get output.
    # (Calibrated live 2026-10-04; raw bodies logged for re-calibration.)
    results, fails = [], 0
    vecs = doc['vectors']
    exp = doc['expected']
    queries = [r for r in raw if r[0] == 'query']
    qi = 0
    for vi in range(len(vecs)):
        got, bad = {}, []
        for name in exp[vi]:
            qi += 1  # store body (pass/fail text, ignored)
            body = queries[qi][2] if qi < len(queries) else ''
            qi += 1
            m = re.search(r'has (\d+)', body or '')
            lit = bool(int(m.group(1))) if m else None
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
