"""Player state, movement and animation; graphics stay in the renderer."""

import config
from animation import Animation
from physics import approach, clamp


class Player:
    def __init__(self):
        self.x = config.START_X
        self.y = config.GROUND_Y
        self.vx = 0.0
        self.facing = 1
        self.animation = Animation(config.PLAYER_ANIMATIONS)

    @property
    def state(self):
        return self.animation.state

    def update(self, dt, controls):
        direction = controls.direction
        speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
        target = direction * speed
        rate = config.ACCELERATION if direction else config.FRICTION
        self.vx = approach(self.vx, target, rate * dt)
        self.x += self.vx * dt
        bounded = clamp(self.x, config.PLAYER_HALF_WIDTH,
                        config.WORLD_WIDTH - config.PLAYER_HALF_WIDTH)
        if bounded != self.x:
            self.vx = 0.0
            self.x = bounded
        if direction:
            self.facing = direction

        state = "IDLE"
        if abs(self.vx) > 0.1:
            state = "RUN" if controls.running else "WALK"
        self.animation.set_state(state)
        self.animation.update(dt)
