"""Stamp labels on levers and lamps. Signs, so they cost no redstone.

1.21 has no `rotation` on signs; `oak_wall_sign` takes `facing`, `oak_sign`
takes none. BOTH front_text and back_text must be present or the setblock is
refused, `messages` must carry 4 slots (a 1-slot list is accepted then
silently dropped), and `TextComponent:'...'` is accepted and ignored. All
four verified live on 1.21.11 -- see LOG.md.

Labels never touch physics: a sign is not a redstone block, so sim and cmc see
the same circuit before and after. Each label is one stone pad + one sign.

NEVER HANGS: pure string building + RCON roundtrips, one bounded call each.

Usage:
  python scratch/label_build.py <pkl>            # dry run: list placements
  python scratch/label_build.py <pkl> --live     # place via RCON at y+64
"""
import pickle
import sys

ROOT = r'D:\redstone-mini'
PW = 'D:/put gitrepos here/mc-server-1.21/rcon_pass.txt'
DQ = chr(34)


def cmd(c, to=120):
    sys.path.insert(0, ROOT + r'\scratch')
    from rcon import Rcon
    try:
        r = Rcon('127.0.0.1', 25576, open(PW).read().strip(), timeout=to)
        return str(r._roundtrip(2, c)[0][1])[:120]
    except Exception as e:
        return 'ERR ' + str(e)[:60]


def sign_cmd(x, y, z, text):
    e = DQ + DQ
    msgs = '[' + DQ + text + DQ + ',' + e + ',' + e + ',' + e + ']'
    blk = DQ + 'black' + DQ
    return ('setblock %d %d %d minecraft:oak_sign'
            '{front_text:{messages:%s,color:%s,has_glowing_text:0b},'
            'back_text:{messages:%s,color:%s,has_glowing_text:0b}}'
            ) % (x, y, z, msgs, blk, msgs, blk)


DESCRIPTIONS = {
    'A': 'A bit %d', 'B': 'B bit %d',
}


def label_for(name):
    if name.endswith('L') and name[:-1] in ('A', 'B') and name[:-1][1:].isdigit():
        return name
    if name.startswith(('S', 'C')) and name[1:].isdigit():
        return name
    if name == 'COUT':
        return 'CARRY OUT'
    return name


def main():
    a = sys.argv[1:]
    pkl = a[0]
    live = '--live' in a
    m = pickle.load(open(pkl, 'rb'))
    oy = 64 if live else 0
    have = {(x, y, z) for x, y, z, _ in m['blocks']}

    jobs = []
    # lever labels: one cell WEST of the lever row, pad + standing sign
    for key, name in sorted(m['io']['levers'].items(), key=lambda kv: str(kv[1])):
        x, z = int(key[0]), int(key[1])
        sx, sz = x - 2, z
        jobs.append(((sx, sz), name, 'lever'))
    # lamp labels: one cell SOUTH of each lamp
    for key, name in sorted(m['io']['lamps'].items(), key=lambda kv: str(kv[1])):
        c = tuple(key) if isinstance(key, (list, tuple)) else (key,)
        lx, lz = c[0], c[1] if len(c) == 2 else c[2]
        jobs.append(((lx, lz + 2), label_for(name), 'lamp'))

    seen = set()
    n = 0
    for (sx, sz), text, kind in jobs:
        if (sx, sz) in seen:
            continue
        seen.add((sx, sz))
        pad = 'setblock %d %d %d minecraft:stone' % (sx, oy + 0, sz)
        sgn = sign_cmd(sx, oy + 1, sz, text)
        n += 1
        if live:
            a1 = cmd(pad)
            a2 = cmd(sgn)
            ok = 'Changed' in a1 and 'Changed' in a2
            print('%-4s %-6s pad=%-8s sign=%-8s %s'
                  % (kind, text, 'ok' if 'Changed' in a1 else 'FAIL',
                     'ok' if 'Changed' in a2 else 'FAIL', '' if ok else '<<<'))
        else:
            print('%-4s %-6s  pad %d,%d  sign %d,65,%d' % (kind, text, sx, sz, sx, sz))
    print('%d labels%s' % (n, ' placed' if live else ' (dry run)'))


if __name__ == '__main__':
    main()