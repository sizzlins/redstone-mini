"""A/B harness: run a scratch tool with an OLD compose.py overlaid.

Usage: python scratch/overlay_run.py <commit> <tool> [args...]
Extracts compose.py at <commit> to temp, pre-imports it (so sys.modules
wins over the repo copy), then runpy's the tool. Read-only: the shared
tree is never modified. Hard-bounded: passes through to the tool's own
bounds. Import-safe (all work in _main).
"""
import os
import subprocess
import sys


def _main():
    commit, tool = sys.argv[1], sys.argv[2]
    args = sys.argv[3:]
    repo = r"D:\redstone-mini"
    tmp = r"C:\Users\LOQ\AppData\Local\Temp\opencode\oldcompose"
    os.makedirs(tmp, exist_ok=True)
    src = subprocess.run(["git", "show", f"{commit}:compose.py"],
                         capture_output=True, cwd=repo, timeout=60)
    assert src.returncode == 0, src.stderr[:200]
    open(os.path.join(tmp, "compose.py"), "wb").write(src.stdout)
    sys.path.insert(0, tmp)
    sys.path.insert(1, repo)
    import compose  # noqa: F401  (binds the OLD module in sys.modules)
    assert compose.__file__.startswith(tmp), compose.__file__
    print("overlay: compose from %s" % commit, flush=True)
    sys.argv = [tool] + args
    import runpy
    runpy.run_path(os.path.join(repo, tool), run_name="__main__")


if __name__ == "__main__":
    _main()
