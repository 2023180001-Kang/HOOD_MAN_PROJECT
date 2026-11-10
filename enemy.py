"""Independent street-thug AI and animation state."""

import config
from animation import Animation
from collision import Rect
from physics import clamp


class Enemy:
    def __init__(self, x, facing=1, spawned_at=0.0):
        self.x = x
        self.previous_x = x
        self.y = config.GROUND_Y
        self.vx = 0.0
        self.facing = facing
        self.spawned_at = spawned_at
        self.animation = Animation(config.ENEMY_ANIMATIONS)

    @property
    def state(self):
        return self.animation.state

    @property
    def body(self):
        return Rect(self.x - config.ENEMY_HALF_WIDTH, self.y,
                    self.x + config.ENEMY_HALF_WIDTH, self.y + config.ENEMY_HEIGHT)

    def update(self, dt, player):
        self.previous_x = self.x
        distance = player.x - self.x
        if distance:
            self.facing = 1 if distance > 0 else -1
        self.vx = 0.0
        if abs(distance) > config.ENEMY_ATTACK_DISTANCE:
            self.vx = self.facing * config.ENEMY_SPEED
        self.x = clamp(self.x + self.vx * dt, config.ENEMY_HALF_WIDTH,
                       config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
        self.animation.set_state("WALK" if self.vx else "IDLE")
        self.animation.update(dt)
