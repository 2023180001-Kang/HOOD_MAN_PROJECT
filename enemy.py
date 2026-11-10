"""Independent street-thug AI and animation state."""

import config
from animation import Animation
from collision import Rect
from physics import approach, clamp


class Enemy:
    def __init__(self, x, facing=1, spawned_at=0.0, *, run_speed=None):
        self.x = x
        self.previous_x = x
        self.y = config.GROUND_Y
        self.vx = 0.0
        self.facing = facing
        self.spawned_at = spawned_at
        self.cooldown = 0.0
        self.has_hit = False
        self.knockback_started = False
        self.run_speed = config.ENEMY_RUN_SPEEDS[0] if run_speed is None else run_speed
        self.running = False
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
            # Per-enemy swing consumption prevents repeated active-frame damage.
            self.has_hit = True
            return player.take_damage(config.ENEMY_DAMAGE)
        return False

    def knockback(self, player_x):
        if self.knockback_started:
            return
        self.knockback_started = True
        self.running = False
        distance = self.x - player_x
        direction = (1 if distance > 0 else -1) if distance else -self.facing
        self.vx = direction * config.KNOCKBACK_SPEED
        self.cooldown = 0.0
        self.has_hit = True
        self.animation.set_state("KNOCKBACK")
        # Facing deliberately stays unchanged while sliding away.

    def stop(self):
        """Cancel pursuit and attacks without moving or turning the enemy."""
        self.vx = 0.0
        self.running = False
        self.cooldown = 0.0
        self.has_hit = True
        self.animation.set_state("IDLE")

    def update_knockback(self, dt):
        if self.state == "KNOCKBACK":
            proposed = self.x + self.vx * dt
            self.x = clamp(proposed, config.ENEMY_HALF_WIDTH,
                           config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
            self.vx = (0.0 if proposed != self.x else
                       approach(self.vx, 0.0, config.KNOCKBACK_FRICTION * dt))
            self.animation.update(dt)
            if self.vx == 0 and self.animation.finished:
                self.animation.set_state("IDLE")
        else:
            self.animation.update(dt)

    def update(self, dt, player):
        self.previous_x = self.x
        if self.knockback_started:
            self.update_knockback(dt)
            return
        if not player.alive:
            self.stop()
            self.animation.update(dt)
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.state == "ATTACK":
            self.vx = 0.0
            self.animation.update(dt)
            if self.animation.finished:
                self.animation.set_state("IDLE")
            return

        distance = player.x - self.x
        gap = abs(distance)
        if distance:
            self.facing = 1 if distance > 0 else -1
        # Separate entry/exit thresholds prevent rapid WALK/RUN flickering.
        if gap >= config.ENEMY_RUN_START_DISTANCE:
            self.running = True
        elif gap <= config.ENEMY_RUN_STOP_DISTANCE:
            self.running = False
        self.vx = 0.0
        state = "IDLE"
        if gap > config.ENEMY_ATTACK_DISTANCE:
            speed = self.run_speed if self.running else config.ENEMY_SPEED
            self.vx = self.facing * speed
            state = "RUN" if self.running else "WALK"
        elif self.cooldown <= 0:
            self.animation.set_state("ATTACK")
            self.has_hit = False
            self.cooldown = config.ENEMY_ATTACK_INTERVAL
            self.animation.update(dt)
            return
        self.x = clamp(self.x + self.vx * dt, config.ENEMY_HALF_WIDTH,
                       config.WORLD_WIDTH - config.ENEMY_HALF_WIDTH)
        self.animation.set_state(state)
        self.animation.update(dt)
