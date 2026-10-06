"""Rebuild scratch/_dustcy.cp314-win_amd64.pyd from _dustcy.pyx.

The .pyd is platform-locked; whoever moves to a new box runs this once:
    python scratch/_dustcy_build.py
Tries the default toolchain (MSVC on Windows), falls back to mingw32.
Cython must be installed (pip install Cython). Bounded: one cythonize +
one extension build, no tests, no sweeps. Rule 7: never runs at import.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "_dustcy.pyx")


def build(args):
    from setuptools import setup
    from Cython.Build import cythonize
    sys.argv = ["setup.py", "build", "--build-base",
                os.path.join(HERE, "cybuild"), *args,
                "build_ext", "--inplace"]
    setup(name="_dustcy",
          ext_modules=cythonize([SRC], language_level=3))


if __name__ == "__main__":
    cwd = os.getcwd()
    os.chdir(HERE)
    try:
        try:
            build([])
        except (Exception, SystemExit) as e:  # setuptools exits, not raises
            print("default toolchain failed (%s); retrying mingw32" % e,
                  flush=True)
            build(["--compiler=mingw32"])
    finally:
        os.chdir(cwd)
    print("built: scratch/_dustcy.*.pyd (opt in: REDSTONE_DUST_CY=1)",
          flush=True)
