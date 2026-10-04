"""Shared bits: directions, block-id helper."""

import functools


DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# wall-torch attach offset by facing (block the torch mounts on).
TORCH_BACK = {"east": (-1, 0), "west": (1, 0),
              "south": (0, -1), "north": (0, 1)}


# ponytail: the palette is dozens of distinct ids; builds stamp tens of
# thousands of cells. Cache the split (was ~half of check_shorts: 180k
# splits for one 60k-block pass, 366k across export).
@functools.lru_cache(maxsize=None)
def base(bid):
    return bid.split("[")[0]

