"""Per-child RSS of one verify worker (spawn cost included, one vector).

Answers: how many concurrent verify children fit in free RAM? Bounded: one
parse + one vector + one print. No pool, no search, no unbounded work.

Usage: python scratch/rss_probe.py [build.pkl]
"""
import os
import pickle
import sys
import time

sys.path.insert(0, r"D:\redstone-mini")
os.environ.pop("REDSTONE_SIM_GATE", None)


def rss_mb():
    # psutil is not installed here; the kernel gives peak working set
    # through GetProcessMemoryInfo (PeakWorkingSetSize is index 2).
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(PMC),
                                           wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    if not psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(),
                                      ctypes.byref(c), c.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return c.WorkingSetSize / (1024.0 * 1024.0)


def main():
    pkl = sys.argv[1] if len(sys.argv) > 1 else \
        r"D:\redstone-mini\scratch\alu4merge_g.pkl"
    print("baseline RSS: %.0f MB" % rss_mb(), flush=True)
    import sim
    import simvec
    from recipe import parse_recipe
    r = parse_recipe(open(r"D:\redstone-mini\recipes\alu4.txt").read())
    t = time.monotonic()
    d = pickle.load(open(pkl, "rb"))
    print("after unpickle: %.0f MB (%.1fs)"
          % (rss_mb(), time.monotonic() - t), flush=True)
    t = time.monotonic()
    P = sim._parse_build(d["blocks"], d["io"])
    print("after parse: %.0f MB (%.1fs)" % (rss_mb(), time.monotonic() - t),
          flush=True)
    vec = {n: 1 for n in r["inputs"][:4]}
    t = time.monotonic()
    simvec.run_scalar(vec, P)
    print("after 1 vector + tables: %.0f MB (%.1fs)"
          % (rss_mb(), time.monotonic() - t), flush=True)
    import multiprocessing as mp
    print("cpus: %d" % mp.cpu_count(), flush=True)


if __name__ == "__main__":
    main()
