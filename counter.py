"""Matching player/enemy counter rows and their shared playback timing."""

from dataclasses import dataclass

import config


@dataclass(frozen=True)
class CounterMove:
    key: str
    name: str
    row: int
    damage: int
    fps: float
    impact_frame: int

    @property
    def state(self):
        return f"COUNTER_{self.key.upper()}"

    @property
    def enemy_state(self):
        return f"SUBDUED_{self.key.upper()}"

    @property
    def duration(self):
        return 8 / self.fps


COUNTERS = {
    f"counter_{key}": CounterMove(key, name, row, config.COUNTER_DAMAGE,
                                 config.COUNTER_FPS, impact_frame)
    for key, name, row, impact_frame in config.COUNTER_MOVE_SPECS
}
