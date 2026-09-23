"""Shared bits: directions, block-id helper."""


DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))



def base(bid):
    return bid.split("[")[0]

