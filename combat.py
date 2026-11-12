"""ASDF basic attack rows, damage, reach and speed, independent of graphics."""

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
    fps: float

    @property
    def state(self):
        return f"ATTACK_{self.key.upper()}"


MOVES = {
    f"combat_{key}": Move(key, name, row, damage, reach, height, fps)
    for key, name, row, damage, reach, height, fps in config.COMBAT_MOVE_SPECS
}
