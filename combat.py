"""Ordered BasicCombat rows and move data, independent of graphics."""

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


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height)
    for row, (key, name, damage, reach, height) in enumerate(config.COMBAT_MOVE_SPECS, 1)
}
