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
        self.cooldown = 0.0
        self.has_hit = False
        self.animation = Animation(config.ENEMY_ANIMATIONS)

    @property
    def state(self):
        return self.animation.state

    @property
    def body(self):
        return Rect(self.x - config.ENEMY_HALF_WIDTH, self.y,
                    self.x + config.ENEMY_HALF_WIDTH, self.y + config.ENEMY_HEIGHT)

    @property
    def attack_box(self):
        if (self.state != "ATTACK" or self.has_hit
                or self.animation.frame not in config.ENEMY_ACTIVE_FRAMES):
            return None
        near = self.x + self.facing * 12
        far = self.x + self.facing * config.ENEMY_ATTACK_REACH
        return Rect(min(near, far), self.y + 20, max(near, far),
                    self.y + config.ENEMY_HEIGHT)

    def try_hit(self, player):
        box = self.attack_box
        if box is not None and box.overlaps(player.body):
            # A swing is spent even when the target is temporarily invulnerable.
            self.has_hit = True
            return player.take_damage(config.ENEMY_DAMAGE)
        return False

    def update(self, dt, player):
        self.previous_x = self.x
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.state == "ATTACK":
            self.vx = 0.0
            self.animation.update(dt)
            if self.animation.finished:
                self.animation.set_state("IDLE")
            return

        distance = player.x - self.x
        if distance:
            self.facing = 1 if distance > 0 else -1
        self.vx = 0.0
        if abs(distance) > config.ENEMY_ATTACK_DISTANCE:
            self.vx = self.facing * config.ENEMY_SPEED
        elif self.cooldown <= 0:
            self.animation.set_state("ATTACK")
            self.has_hit = False
            self.cooldown = config.ENEMY_ATTACK_INTERVAL
            self.animation.update(dt)
            return
        self.x = clamp(self.x + self.vx * dt, config.ENEMY_HALF_WIDTH,
                       config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
        self.animation.set_state("WALK" if self.vx else "IDLE")
        self.animation.update(dt)
