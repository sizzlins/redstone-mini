"""Why does sim say 0 where cmc says 14? Run sim on one vector and dump the
whole neighbourhood's live map plus the nets.
Usage: simwhy.py <doc.v2doc.json> <vecIndex> <cx> <cy> <cz>
"""
import json
import pickle
import sys

sys.path.insert(0, r'D:\redstone-mini')
from sim import _parse_build, _run_vec


def main():
    doc_p, vi = sys.argv[1], int(sys.argv[2])
    cx, cy, cz = [int(v) for v in sys.argv[3:6]]
    doc = json.load(open(doc_p))
    io = {'levers': {tuple(int(v) for v in k.split(',')): n
                     for k, n in doc['levers']},
          'lamps': {tuple(int(v) for v in k.split(',')): n
                    for k, n in doc['lamps']}}
    P = _parse_build([tuple(b) for b in doc['blocks']], io)
    vec = doc['vectors'][vi]
    got, live, tlive, nticks, rlive, conc = _run_vec(vec, None, P)
    print('vec', vi, vec, 'lamps', got, 'ticks', nticks)
    blocks = {(b[0], b[1], b[2]): b[3] for b in doc['blocks']}
    print('live entries near (%d,%d,%d):' % (cx, cy, cz))
    for p in sorted(live):
        if abs(p[0] - cx) <= 4 and abs(p[1] - cy) <= 1 and abs(p[2] - cz) <= 4:
            print('   %-14s live=%-3s block=%s'
                  % (str(p), live[p], blocks.get(p, '?')[:50]))
    print()
    for p in ((cx, cy, cz), (cx - 1, cy, cz), (cx + 1, cy, cz),
              (cx, cy, cz - 1), (cx, cy, cz + 1)):
        print('  probe %-14s live=%-4s block=%s'
              % (str(p), live.get(p, 'ABSENT'), blocks.get(p, '?')[:60]))


if __name__ == '__main__':
    main()
