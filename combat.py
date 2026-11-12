"""ASDF basic attacks and a separate guard sheet, independent of graphics."""

from dataclasses import dataclass

import config


@dataclass(frozen=True)
class Move:
    key: str
    name: str
    row: int
    damage: int
    reach: float
    height: float

    @property
    def blocking(self):
        return self.key == "h"

    @property
    def state(self):
        return "BLOCK" if self.blocking else f"ATTACK_{self.key.upper()}"

    @property
    def image(self):
        return config.BLOCK_IMAGE if self.blocking else config.COMBAT_IMAGE


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height)
    for key, name, row, damage, reach, height in config.COMBAT_MOVE_SPECS
}
