"""Boss rifleman: one warning, automatic fire, then a twenty-round reload."""

import config
from collision import same_floor
from projectiles import RifleBullet
from researcher import Researcher


class ARSoldier(Researcher):
    max_hp = config.AR_SOLDIER_MAX_HP
    image_name = config.AR_SOLDIER_IMAGE
    animations = config.AR_SOLDIER_ANIMATIONS
    magazine_size = config.AR_SOLDIER_MAGAZINE_SIZE
    reload_fps = config.AR_SOLDIER_RELOAD_FPS
    shoot_range = config.AR_SOLDIER_SHOOT_RANGE
    shoot_frame = config.AR_SOLDIER_SHOOT_FRAME
    aim_duration = config.AR_SOLDIER_AIM_DURATION
    muzzle_x = config.AR_SOLDIER_MUZZLE_X
    muzzle_height = config.AR_SOLDIER_MUZZLE_HEIGHT
    projectile_type = RifleBullet
    fire_interval = config.AR_SOLDIER_FIRE_INTERVAL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fire_remaining = 0.0
        self.burst_shots = 0

    @property
    def attack_damage(self):
        return config.AR_SOLDIER_DAMAGE

    def start_attack(self):
        self.fire_remaining = 0.0
        self.burst_shots = 0
        super().start_attack()

    def start_reload(self):
        self.fire_remaining = 0.0
        self.burst_shots = 0
        super().start_reload()

    def show_fire_pose(self):
        frames = config.AR_SOLDIER_FIRE_FRAMES
        frame = frames[max(0, self.burst_shots - 1) % len(frames)]
        self.animation.elapsed = (frame + 1e-9) / self.attack_fps

    def update_attack(self, dt):
        self.vx = self.ground_vy = 0.0
        if self.aim_remaining > 0:
            remaining = self.aim_remaining
            self.aim_remaining = max(0.0, remaining - dt)
            self.animation.elapsed = (self.shoot_frame - 1 + 1e-9) / self.attack_fps
            if self.aim_remaining > 1e-9:
                return
            self.aim_remaining = 0.0
            dt = max(0.0, dt - remaining)
        self.fire_remaining -= dt
        if self.ammo <= 0 and self.fire_remaining <= 1e-9:
            self.start_reload()
            return
        if self.fire_remaining <= 1e-9:
            self.has_hit = False
        # Stay on the original four firing poses, without replaying the warning
        # or finishing the single-shot animation between consecutive rounds.
        self.show_fire_pose()

    def take_projectile(self):
        if self.fire_remaining > 1e-9:
            return None
        bullet = super().take_projectile()
        if bullet is not None:
            self.burst_shots += 1
            self.fire_remaining = max(0.0, self.fire_remaining + self.fire_interval)
            self.show_fire_pose()
        return bullet

    def _update_ai(self, dt, player):
        # Leaving the lane/range or crossing behind cancels both the warning and
        # an active burst. Re-entering always starts a fresh, full warning.
        if self.alive and self.state == "ATTACK":
            dx = player.x - self.x
            if (not player.alive or not same_floor(self, player)
                    or abs(dx) > self.shoot_range
                    or abs(player.ground_y - self.ground_y) > config.ATTACK_DEPTH_TOLERANCE
                    or dx * self.facing < 0):
                self.stop()
        super()._update_ai(dt, player)
