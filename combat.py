"""ASDF basic attack rows, damage and reach, independent of graphics."""

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
    def state(self):
        return f"ATTACK_{self.key.upper()}"


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height)
    for key, name, row, damage, reach, height in config.COMBAT_MOVE_SPECS
}
