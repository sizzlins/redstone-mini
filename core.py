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


def pin_tap_cell(name, recipe):
    """The cell a pinned output's wire must reach, or None if it is not pinned.

    One rule, two callers, and that is the whole point. `layout.build_netspec`
    runs BEFORE routing and needs the cell to make the pin a routing goal;
    `tiles._tap_pinned` runs AFTER and needs the same cell to sit the lamp
    against. Fixed (the lamp's west neighbour) rather than "first free
    neighbour" precisely because a free-cell search answers differently either
    side of a route -- the two stages would disagree and the lamp would hang off
    a wire nobody drove. A pin the west neighbour cannot serve fails loudly
    instead of quietly landing somewhere else, which is the whole contract of a
    pin: you asked for a cell, you get that cell or an error.
    """
    pin = (recipe.get("lamps_at") or {}).get(name)
    if pin is None:
        return None
    return (int(pin[0]) - 1, int(pin[1]))

