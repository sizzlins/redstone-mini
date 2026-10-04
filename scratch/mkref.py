"""Freeze the COMMITTED engine as a reference module.

The reference is a frozen copy of sim.py as of HEAD, so an optimisation can be
proven behaviour-identical against it instead of against memory. Regenerate
with:  python scratch/mkref.py

Why the WHOLE FILE and not a surgical extract (2026-10-04): this used to pull
out only `_target_shots`, `_parse_build` and `_run_vec` and rewrite their
`_`-prefixed globals. That silently produced a reference MISSING every
module-level helper `_run_vec` calls (`dust_lvl`, `cob_state`, `rep_locked`,
`rep_on`, `sched` helpers...), so a re-frozen reference disagreed with the
live engine for reasons that had nothing to do with the change under test --
a gate that cries wolf is worse than no gate. Copying the file verbatim
cannot drift: whatever HEAD runs is what the reference runs.

Rule 7: one `git show` + one write, no loops, no engine calls.

FIX (2026-10-05, diagnosed with scratch/refdrift.py + scratch/refbytes.py):
this script used `text=True`, which decodes git's output with the WINDOWS LOCALE
(cp1252) -- not UTF-8. sim.py contains em-dashes and +/- signs, so every re-freeze
mangled them to 'â€"' / 'Â±' and then re-encoded the mojibake as UTF-8. The freeze
was therefore LOSSY BY CONSTRUCTION and the damage compounded with each run
(the freeze had been regenerated twice on 10/4). Codepoint proof, HEAD clean vs
freeze corrupt:

    HEAD:sim.py  L16  one char 0x2014   (em-dash)
    ref_sim.py   L16  0xe2 0x20ac 0x201d ('â€"')
    HEAD:sim.py  L393 one char 0xb1     (+/-)
    ref_sim.py   L393 0xc2 0xb1         ('Â±')

Both lost characters live in COMMENTS and in one log-message f-string, so no
redstone behaviour ever differed -- but the artifact could never be diffed
textually again, and any future freeze-vs-HEAD comparison was guaranteed to
cry wolf. `encoding="utf-8"` on the decode plus `newline=""` on the write makes
the body byte-identical to the blob.

Verify a freeze with:  python scratch/refdrift.py   (0 changed lines, AST equal)
"""
import subprocess
import sys

# ponytail: never let subprocess decode for us. text=True picks the locale
# encoding, which on Windows is cp1252 and silently corrupts this repo's
# non-ASCII comments. Bytes out, we decode.
SRC = subprocess.run(["git", "show", "HEAD:sim.py"], cwd=r"D:\redstone-mini",
                     capture_output=True, check=True,
                     encoding="utf-8", errors="strict").stdout
if "_run_vec" not in SRC or "_parse_build" not in SRC:
    sys.exit("HEAD:sim.py does not look like the engine (no _run_vec?)")

HEADER = (
    '"""FROZEN reference copy of sim.py as of git HEAD -- verbatim.\n\n'
    'Do not edit: scratch/diff_engine.py compares the live engine against this\n'
    'to prove an optimisation changed nothing but the speed. Regenerate with\n'
    'scratch/mkref.py AFTER committing a physics change (an optimisation must\n'
    'be measured against the physics it was written for, not against a stale\n'
    'copy: a pre-burnout reference disagreed with the live engine on alu4\n'
    'vec001+ and looked exactly like a broken optimisation).\n'
    '"""\n')

open(r"D:\redstone-mini\scratch\ref_sim.py", "w", encoding="utf-8").write(
    HEADER + SRC)
print("wrote scratch/ref_sim.py (%d lines, verbatim HEAD:sim.py)"
      % (SRC.count("\n") + 1))
