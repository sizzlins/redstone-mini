"""Which side of the freeze holds the mojibake? Codepoints, not console glyphs.

The console cannot be trusted to render U+2014, so refdrift.py's diff output
was ambiguous about which file was corrupt. Print repr() and the codepoint list
for every line where HEAD:sim.py and ref_sim.py's body differ, and classify the
corruption by its known signatures:

  'â€"' == U+00E2 U+20AC U+0094  -> UTF-8 em-dash decoded as cp1252, i.e.
                                     subprocess text=True with a Windows locale,
                                     then re-encoded as UTF-8. That is mkref.
  U+FFFD                          -> lossy decode, unrecoverable.
  'Â±' == U+00C2 U+00B1           -> same trap on '+/-'.

NEVER HANGS: one git show, two file reads, no engine calls.

Usage:  python scratch/refbytes.py
"""
import subprocess
import sys

ROOT = r'D:\redstone-mini'
ENC = dict(encoding='utf-8', errors='surrogateescape')
SIG = {
    '\u00e2\u20ac\u201a': 'UTF8-as-CP1252 em-dash (mkref text=True)',
    '\u00e2\u20ac\u201e': 'UTF8-as-CP1252 em-dash variant',
    '\u00c2\u00b1': 'UTF8-as-CP1252 +/-',
    '\ufffd': 'LOSSY decode (unrecoverable)',
    '\u00e2\u0080': 'UTF8-as-CP1252 3-byte prefix',
}


def sig(txt):
    for k, v in SIG.items():
        if k in txt:
            return v
    return 'unrecognised'


def show(tag, line, n):
    marks = [(i, hex(ord(c)), c) for i, c in enumerate(line)
             if ord(c) > 127]
    print('  %s L%-5d %r' % (tag, n, line.strip()[:78]))
    if marks:
        print('       non-ascii: %s' % ' '.join(
            '%s=%s' % (repr(c)[1:-1], h) for i, h, c in marks))
    else:
        print('       non-ascii: none')


def main():
    src = subprocess.run(['git', 'show', 'HEAD:sim.py'], cwd=ROOT,
                         capture_output=True, check=True, **ENC).stdout
    raw = open(ROOT + r'\scratch\ref_sim.py', 'rb').read().decode(
        'utf8', 'surrogateescape')
    i = raw.index('"""', raw.index('"""') + 3) + 3
    ref = raw[i:].lstrip('\r\n').replace('\r\n', '\n')
    src = src.replace('\r\n', '\n')
    a, b = src.splitlines(), ref.splitlines()
    print('HEAD:sim.py lines=%d  ref_sim lines=%d' % (len(a), len(b)))
    ndiff = 0
    for n, (x, y) in enumerate(zip(a, b), 1):
        if x == y:
            continue
        ndiff += 1
        xs = [c for c in x if ord(c) > 127]
        ys = [c for c in y if ord(c) > 127]
        kind = 'TEXT-ONLY' if x.split('#')[0].strip() == \
            y.split('#')[0].strip() else 'EXECUTABLE'
        print('\nL%-5d [%s]' % (n, kind))
        show('HEAD', x, n)
        show('ref ', y, n)
        if xs or ys:
            print('       verdict: HEAD=%s | ref=%s' % (sig(x), sig(y)))
        if ndiff >= 6:
            print('\n(stopping after 6 differing lines)')
            break
    print('\ntotal differing lines: %d' % ndiff)
    # Which commit is the freeze actually from?
    log = subprocess.run(['git', 'log', '--oneline', '-8', '--', 'sim.py'],
                         cwd=ROOT, capture_output=True, **ENC)
    print('\nsim.py history (newest first):\n%s' % log.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())