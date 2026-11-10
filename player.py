"""Player state, movement and animation; graphics stay in the renderer."""

import config
from animation import Animation
from collision import Rect
from physics import approach, clamp


class Player:
    def __init__(self):
        self.x = config.START_X
        self.previous_x = self.x
        self.y = config.GROUND_Y
        self.vx = 0.0
        self.vy = 0.0
        self.jump_count = 0
        self.facing = 1
        self.hp = config.MAX_HP
        self.invulnerability = 0.0
        self.animation = Animation(config.PLAYER_ANIMATIONS)

    @property
    def state(self):
        return self.animation.state

    @property
    def alive(self):
        return self.hp > 0

    @property
    def grounded(self):
        return self.y <= config.GROUND_Y and self.vy == 0

    @property
    def body(self):
        return Rect(self.x - config.PLAYER_HALF_WIDTH, self.y,
                    self.x + config.PLAYER_HALF_WIDTH, self.y + config.PLAYER_HEIGHT)

    def take_damage(self, damage):
        if self.hp <= 0 or self.invulnerability > 0 or self.state == "HIT":
            return False
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        hit_fps = config.PLAYER_ANIMATIONS["HIT"][1]
        self.invulnerability = max(config.HIT_INVULNERABILITY, 8 / hit_fps)
        self.animation.set_state("HIT" if self.hp else "DYING")
        return True

    def update_vertical(self, dt):
        if not self.grounded:
            self.vy -= config.GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= config.GROUND_Y:
                self.y = config.GROUND_Y
                self.vy = 0.0
                self.jump_count = 0

    def update(self, dt, controls):
        self.previous_x = self.x
        self.invulnerability = max(0.0, self.invulnerability - dt)
        jump_pressed = controls.take_press("jump")
        if self.state in ("HIT", "DYING", "DEAD"):
            self.vx = 0.0
            self.update_vertical(dt)
            if self.state == "DEAD":
                return
            self.animation.update(dt)
            if self.animation.finished:
                if self.state == "DYING":
                    self.animation.set_state("DEAD")
                    self.animation.elapsed = 8 / config.PLAYER_ANIMATIONS["DEAD"][1]
                else:
                    self.animation.set_state("IDLE")
            return

        if jump_pressed and self.jump_count < 2:
            self.vy = config.JUMP_SPEED if self.jump_count == 0 else config.DOUBLE_JUMP_SPEED
            self.jump_count += 1
            self.animation.set_state("JUMP")
            self.animation.elapsed = 0.0

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
        self.update_vertical(dt)

        state = "IDLE"
        if abs(self.vx) > 0.1:
            state = "RUN" if controls.running else "WALK"
        if not self.grounded:
            state = "JUMP"
        self.animation.set_state(state)
        self.animation.update(dt)
