"""Is ref_sim.py's drift from HEAD:sim.py COMMENT-ONLY, and is it lossy?

refcheck.py reported the freeze as STALE, but every hunk looked like a mangled
em-dash inside a `#` comment. That distinction decides everything:

  - comment-only drift  -> the freeze is SEMANTICALLY correct, diff_engine's
    ALL IDENTICAL is trustworthy, and the real defect is a LOSSY WRITE in
    mkref.py (it corrupts the freeze every time it runs).
  - any code drift      -> diff_engine has been comparing against a genuinely
    different engine and every "ALL IDENTICAL" claim is void.

Prints a per-changed-line verdict (comment / docstring / CODE) and compares
ASTs, which ignores comments and whitespace entirely: two files with an equal
ast.dump() are the same program. Bytes in, we decode -- never text=True, whose
locale decoding is what corrupted the freeze in the first place.

NEVER HANGS: two file reads, one git show, no engine calls.

Usage:  python scratch/refdrift.py
"""
import ast
import subprocess
import sys

ROOT = r'D:\redstone-mini'
ENC = dict(encoding='utf-8', errors='replace')


def code_of(path):
    return open(path, 'rb').read().decode('utf8')


def main():
    src = subprocess.run(['git', 'show', 'HEAD:sim.py'], cwd=ROOT,
                         capture_output=True, check=True, **ENC).stdout
    ref = code_of(ROOT + r'\scratch\ref_sim.py')
    # drop mkref's prepended docstring header
    i = ref.index('"""', ref.index('"""') + 3) + 3
    ref = ref[i:].lstrip('\r\n').replace('\r\n', '\n')
    src = src.replace('\r\n', '\n')

    a = src.splitlines()
    b = ref.splitlines()
    # align on content ignoring comment text: compare the CODE part of each line
    def strip_comment(l):
        return l.split('#', 1)[0].rstrip()

    changed = [(n, x, y) for n, (x, y) in enumerate(zip(a, b), 1) if x != y]
    print('lines HEAD: %d  ref_sim: %d' % (len(a), len(b)))
    print('changed lines           : %d' % len(changed))
    kinds = {'comment': 0, 'code': 0, 'blank': 0}
    code_lines = []
    for n, x, y in changed:
        if strip_comment(x) != strip_comment(y):
            kinds['code'] += 1
            code_lines.append((n, x, y))
        elif x.strip() == '' or y.strip() == '':
            kinds['blank'] += 1
        else:
            kinds['comment'] += 1
    print('  comment-only drift    : %d' % kinds['comment'])
    print('  blank/structure drift : %d' % kinds['blank'])
    print('  CODE drift            : %d' % kinds['code'])
    for n, x, y in code_lines[:20]:
        print('   L%-5d HEAD: %s' % (n, x))
        print('   %-7s ref : %s' % ('', y))
    same_ast = ast.dump(ast.parse(src)) == ast.dump(ast.parse(ref))
    print('\nAST identical (comments ignored): %s' % same_ast)
    # quantify the corruption: does the freeze still parse, and does the
    # replacement char appear where a real character belonged?
    for name, txt in (('HEAD:sim.py', src), ('ref_sim body', ref)):
        bad = sum(txt.count(c) for c in '\ufffd\ufffc')
        moji = txt.count('\u00c3\u00a2') + txt.count('\u00c2') + txt.count('\u00e2\u0080')
        print('%-14s replacement_chars=%d  suspect_mojibake=%d'
              % (name, bad, moji))
    ok = same_ast and not kinds['code']
    print('\n%s' % ('FREEZE SEMANTICALLY IDENTICAL TO HEAD'
                  if ok else 'FREEZE GENUINELY DIFFERS -- run mkref.py'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())