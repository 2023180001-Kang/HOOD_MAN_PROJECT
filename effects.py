"""Short-lived, world-space hit bursts; no display or actor references."""

from dataclasses import dataclass

import config


@dataclass
class HitEffect:
    x: float
    y: float
    facing: int
    elapsed: float = 0.0

    @classmethod
    def at_contact(cls, attack, body, facing):
        return cls((max(attack.left, body.left) + min(attack.right, body.right)) / 2,
                   (max(attack.bottom, body.bottom) + min(attack.top, body.top)) / 2,
                   facing)

    def update(self, dt):
        self.elapsed += dt

    @property
    def frame(self):
        count = config.HIT_EFFECT_COLUMNS * config.HIT_EFFECT_ROWS
        return min(count - 1, int(self.elapsed * config.HIT_EFFECT_FPS + 1e-9))

    @property
    def finished(self):
        count = config.HIT_EFFECT_COLUMNS * config.HIT_EFFECT_ROWS
        return self.elapsed + 1e-9 >= count / config.HIT_EFFECT_FPS
