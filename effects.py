"""Short-lived, world-space combat effects; no display or actor references."""

from dataclasses import dataclass

import config


@dataclass
class HitEffect:
    x: float
    y: float
    facing: int
    elapsed: float = 0.0
    image_name: str = config.PUNCH_KICK_HIT_IMAGE

    @classmethod
    def at_contact(cls, attack, body, facing, *, depth=0.0, image_name=config.PUNCH_KICK_HIT_IMAGE):
        return cls((max(attack.left, body.left) + min(attack.right, body.right)) / 2,
                   (max(attack.bottom, body.bottom) + min(attack.top, body.top)) / 2 + depth,
                   facing, image_name=image_name)

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


@dataclass
class DamageNumber:
    x: float
    y: float
    damage: int
    elapsed: float = 0.0

    @classmethod
    def above_body(cls, body, damage, *, depth=0.0):
        return cls((body.left + body.right) / 2,
                   body.top + config.ENEMY_HP_BAR_GAP + config.ENEMY_HP_BAR_HEIGHT
                   + config.DAMAGE_NUMBER_GAP + depth, damage)

    def update(self, dt):
        self.elapsed += dt

    @property
    def display_y(self):
        progress = min(1.0, self.elapsed / config.DAMAGE_NUMBER_DURATION)
        return self.y + config.DAMAGE_NUMBER_RISE * progress

    @property
    def finished(self):
        return self.elapsed + 1e-9 >= config.DAMAGE_NUMBER_DURATION
