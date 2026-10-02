"""Extract the COMMITTED _run_vec/_parse_build into a reference module.

The reference is a frozen copy of the engine as of HEAD, so an optimisation
can be proven byte-identical against it instead of against memory.
Regenerate with:  python scratch/mkref.py
"""
import re
import subprocess
import sys

SRC = subprocess.run(["git", "show", "HEAD:sim.py"], cwd=r"D:\redstone-mini",
                     capture_output=True, text=True, check=True).stdout
lines = SRC.split("\n")


def grab(name):
    """Pull a top-level def (and everything indented under it)."""
    out, on = [], False
    for ln in lines:
        if not on and ln.startswith("def %s(" % name):
            on = True
        elif on and ln and not ln[0].isspace() and not ln.startswith(")"):
            break
        if on:
            out.append(ln)
    if not out:
        sys.exit("def %s not found" % name)
    return "\n".join(out)


parts = [
    '"""FROZEN reference copy of sim.py\'s physics, extracted from git HEAD.',
    'Do not edit: scratch/diff_engine.py compares the live engine against this',
    'to prove an optimisation changed nothing but the speed.',
    '"""',
    "import heapq as _hq",
    "import os as _os",
    "",
    "from core import DIRS, base",
    "from layout import dust_points",
    "",
    "TICK_CAP = %d" % 20000,
    "STEP_CAP = %d" % 2000000,
    "STALL = %d" % 5000,
    "BOUT_N = 8",
    "BOUT_GRACE = 60",
    "BOUT = {}",
    "",
    "_TARGET_TICKS = {'arrow': 10, 'trident': 10}",
    "_TARGET_OTHER_TICKS = 4",
    "_TARGET_PROJECTILES = frozenset({",
    "    'arrow', \"bottle o' enchanting\", 'dragon fireball', 'egg',",
    "    'ender pearl', 'fireball', 'firework rocket', 'fishing bobber',",
    "    'lingering potion', 'llama spit', 'shulker bullet', 'snowball',",
    "    'small fireball', 'splash potion', 'trident', 'wind charge',",
    "    'wither skull'})",
    "",
]
for fn in ("_target_shots", "_parse_build", "_run_vec"):
    body = grab(fn)
    body = body.replace("_TICK_CAP", "TICK_CAP").replace("_STEP_CAP", "STEP_CAP")
    body = body.replace("_STALL", "STALL")
    body = body.replace("_BOUT_N", "BOUT_N").replace("_BOUT_GRACE", "BOUT_GRACE")
    body = body.replace("_BOUT", "BOUT")
    parts.append("")
    parts.append(body)

# _run_vec ends with a bare "return ({net: ..." tuple expression; the frozen
# copy keeps it verbatim.
open(r"D:\redstone-mini\scratch\ref_sim.py", "w", encoding="utf-8").write(
    "\n".join(parts) + "\n")
print("wrote scratch/ref_sim.py (%d lines)" % (len(parts) + 1))