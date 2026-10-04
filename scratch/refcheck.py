"""Settle it: is scratch/ref_sim.py's BODY byte-identical to HEAD:sim.py?

A blob-hash comparison cannot answer this. Two independent reasons:

  1. mkref.py PREPENDS a docstring header, so ref_sim.py can never hash-equal
     sim.py even when the body is verbatim.
  2. core.autocrlf=true (system gitconfig) makes git normalise line endings on
     checkout and Python's text-mode open() translate \\n -> \\r\\n on write,
     so a worktree file's bytes never equal the blob's bytes anyway.

So compare the BODY, with newlines normalised, and separately report which
module-level helpers the body carries -- the actual hazard the opt agent
described (a partial three-function extraction omits everything _run_vec calls).

Also answers the standing rule: run this after ANY commit touching sim.py or
simvec.py. Nonzero exit = diff_engine is comparing against a stale baseline.

NEVER HANGS: one git show, one file read, no engine calls, no loops over
builds.

Usage:  python scratch/refcheck.py
"""
import subprocess
import sys

ROOT = r'D:\redstone-mini'
# ponytail: NEVER let subprocess decode for us. text=True uses the locale
# encoding (cp1252 here), and sim.py contains UTF-8 em-dashes, so git's bytes
# came back as mojibake and this check reported an UNCOMMITTED PHYSICS EDIT
# that did not exist -- the third encoding trap of the night, after
# core.autocrlf and the prepended mkref header. A gate that cries wolf is
# worse than no gate. Bytes in, utf-8 decode by us, compare.
ENC = dict(encoding='utf-8', errors='strict')
HELPERS = ('def dust_lvl', 'def cob_state', 'def rep_locked', 'def rep_on',
           'def comp_in', 'def comp_out', 'def _run_vec', 'def _parse_build')


def main():
    src = subprocess.run(['git', 'show', 'HEAD:sim.py'], cwd=ROOT,
                         capture_output=True, check=True, **ENC).stdout
    raw = open(ROOT + r'\scratch\ref_sim.py', 'rb').read().decode('utf8')
    # strip the leading docstring header, then the blank lines after it
    i = raw.index('"""', raw.index('"""') + 3) + 3
    body = raw[i:].lstrip('\r\n').replace('\r\n', '\n')
    same = body == src.replace('\r\n', '\n')
    print('ref_sim.py header bytes : %d' % i)
    print('HEAD:sim.py chars       : %d' % len(src))
    print('ref_sim body == HEAD:sim.py (newlines normalised): %s' % same)
    if not same:
        import difflib
        d = [l for l in difflib.unified_diff(src.replace('\r\n', '\n').splitlines(),
                                             body.splitlines(),
                                             'HEAD:sim.py', 'ref_sim body',
                                             lineterm='', n=1)]
        print('DIFF (%d lines):' % len(d))
        print('\n'.join(d[:40]))
    missing = [h for h in HELPERS if h not in raw]
    print('module-level helpers    : %s'
          % ('ALL PRESENT' if not missing else 'MISSING ' + ', '.join(missing)))
    # is the LIVE worktree sim.py itself in sync with HEAD? an uncommitted
    # physics edit means diff_engine's "verbatim" claim is quietly false.
    live = open(ROOT + r'\sim.py', 'rb').read().decode('utf8').replace(
        '\r\n', '\n')
    print('worktree sim.py == HEAD:sim.py : %s%s'
          % (live == src.replace('\r\n', '\n'),
             '' if live == src.replace('\r\n', '\n')
             else '   <-- UNCOMMITTED sim.py EDIT'))
    ok = same and not missing
    print('\n%s' % ('BASELINE OK' if ok else 'BASELINE STALE -- run mkref.py'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())