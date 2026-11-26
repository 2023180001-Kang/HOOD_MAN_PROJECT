"""Final-stage sniper with a visible tracking reticle and single-shot recovery."""

from math import hypot

import config
from collision import same_floor
from projectiles import SniperBullet
from researcher import Researcher


class Sniper(Researcher):
    image_name = config.SNIPER_IMAGE
    animations = config.SNIPER_ANIMATIONS
    max_hp = config.SNIPER_MAX_HP
    magazine_size = config.SNIPER_MAGAZINE_SIZE
    reload_fps = 8 / config.SNIPER_RELOAD_TIME
    projectile_type = SniperBullet
    shoot_range = 1000.0
    shoot_frame = 3
    aim_duration = 0.0  # The moving reticle supplies the warning.
    muzzle_x, muzzle_height = 78.0, 76.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.reticle = None
        self.locked_target = None
        self.rest_remaining = 0.0

    @property
    def attack_damage(self):
        return config.SNIPER_DAMAGE

    @property
    def visible_target(self):
        if self.state in ("IDLE", "WALK", "RUN"):
            return self.reticle
        if self.state == "ATTACK" and self.rest_remaining > config.SNIPER_RECOVERY - config.SNIPER_LOCK_FLASH:
            return self.reticle
        return None

    def track_player(self, dt, player):
        self.locked_target = None
        height = player.jump_height + config.PLAYER_HEIGHT * 0.6
        x, y = player.x, player.ground_y + height
        side = 1 if self.x >= x else -1
        in_range = abs(self.x - x) <= self.shoot_range
        if self.reticle is None:
            self.reticle = (x + side * self.rng.uniform(120, 180), y + self.rng.uniform(90, 130))
        # While the shooter is approaching, hover above the target. Once in
        # range, converge on the torso, including movement in depth and jumps.
        target_x, target_y = (x, y) if in_range else (x + side * 120, y + 90)
        dx, dy = target_x - self.reticle[0], target_y - self.reticle[1]
        distance = hypot(dx, dy)
        step = config.SNIPER_TRACK_SPEED * dt
        if distance <= step:
            self.reticle = (target_x, target_y)
            if in_range:
                self.locked_target = (x, player.ground_y, height)
        else:
            self.reticle = (self.reticle[0] + dx * step / distance, self.reticle[1] + dy * step / distance)

    def pursuit_delta(self, dx, dy, player):
        if self.locked_target:
            return 0.0, 0.0
        return self.facing * max(0.0, abs(dx) - 380.0), dy

    def at_firing_position(self, dx, dy):
        return self.locked_target is not None

    def start_attack(self):
        super().start_attack()
        if self.state == "ATTACK":
            self.animation.elapsed = (self.shoot_frame + 1e-9) / self.attack_fps

    def take_projectile(self):
        if self.locked_target is None:
            return None
        shot = super().take_projectile()
        if shot is not None:
            shot.aim_at(*self.locked_target)
            self.rest_remaining = config.SNIPER_RECOVERY
        return shot

    def update_attack(self, dt):
        self.animation.update(dt)
        if self.has_hit and self.rest_remaining <= 1e-9:
            self.stop()
            if not self.ammo:
                self.start_reload()

    def stop(self):
        self.reticle = self.locked_target = None
        super().stop()

    def _update_ai(self, dt, player):
        self.rest_remaining = max(0.0, self.rest_remaining - dt)
        mobile = self.state in ("IDLE", "WALK", "RUN")
        if (mobile and self.alive and player.alive and same_floor(self, player)
                and not self.knockback_started and self.navigation_target is None):
            if self.rest_remaining > 1e-9:
                self.stop()
                return
            if self.ammo:
                self.track_player(dt, player)
        elif self.state != "ATTACK":
            self.reticle = self.locked_target = None
        super()._update_ai(dt, player)
