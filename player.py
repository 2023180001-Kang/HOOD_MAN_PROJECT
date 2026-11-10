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
        if not self.alive:
            return False
        self.hp = max(0, self.hp - damage)
        self.vx = 0.0
        # Every enemy swing applies damage. Re-entering HIT preserves the
        # current animation clock; a lethal hit always overrides it with DYING.
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
            if self.jump_count == 0:
                self.vy = config.JUMP_SPEED
            elif controls.running and controls.direction:
                self.vy = config.RUN_DOUBLE_JUMP_SPEED
            else:
                self.vy = config.DOUBLE_JUMP_SPEED
            self.jump_count += 1
            self.animation.set_state("JUMP")
            self.animation.elapsed = 0.0

        direction = controls.direction
        speed = config.RUN_SPEED if controls.running else config.WALK_SPEED
        target = direction * speed
        if direction and self.vx * direction < 0:
            # Brake to zero first; only the remaining time accelerates the turn.
            stop_time = abs(self.vx) / config.FRICTION
            self.vx = approach(self.vx, 0.0, config.FRICTION * dt)
            if stop_time < dt:
                self.vx = approach(0.0, target, config.ACCELERATION * (dt - stop_time))
        else:
            # Releasing Shift must use the same strong braking as releasing a key.
            slowing = not direction or abs(self.vx) > speed
            rate = config.FRICTION if slowing else config.ACCELERATION
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
