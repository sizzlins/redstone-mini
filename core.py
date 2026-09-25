"""Shared bits: directions, block-id helper."""


DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

# wall-torch attach offset by facing (block the torch mounts on).
TORCH_BACK = {"east": (-1, 0), "west": (1, 0),
              "south": (0, -1), "north": (0, 1)}



def base(bid):
    return bid.split("[")[0]

